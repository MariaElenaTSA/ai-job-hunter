from unittest.mock import Mock, patch

import pytest
import requests

from app.services import remoteok_client
from app.services.provider_errors import ProviderFetchError, ProviderResponseError

LEGAL_METADATA = {"legal": "https://remoteok.com/legal", "api": "https://remoteok.com/api"}

RAW_JOB = {
    "id": "1234567",
    "position": "Backend Engineer",
    "company": "RemoteCo",
    "location": "Worldwide",
    "url": "https://remoteok.com/remote-jobs/1234567",
    "apply_url": "https://remoteco.example.com/apply/1234567",
    "description": "<p>Build our backend in Python.</p>",
    "date": "2026-07-01T00:00:00Z",
}


# --- normalize_job ---

def test_normalize_job_maps_common_fields():
    normalized = remoteok_client.normalize_job(RAW_JOB)

    assert normalized["source"] == "remoteok"
    assert normalized["source_job_id"] == "1234567"
    assert normalized["title"] == "Backend Engineer"
    assert normalized["company_name"] == "RemoteCo"
    assert normalized["location"] == {"name": "Worldwide"}
    assert normalized["content"] == "<p>Build our backend in Python.</p>"
    assert normalized["language"] is None
    assert normalized["application_deadline"] is None
    assert normalized["attribution"] == "Remote OK"


def test_normalize_job_uses_composite_id():
    normalized = remoteok_client.normalize_job(RAW_JOB)

    assert normalized["id"] == "remoteok:1234567"


def test_normalize_job_workplace_type_is_remote():
    normalized = remoteok_client.normalize_job(RAW_JOB)

    assert normalized["workplace_type"] == "remote"


def test_normalize_job_source_url_is_the_remoteok_url_verbatim():
    normalized = remoteok_client.normalize_job(RAW_JOB)

    assert normalized["source_url"] == RAW_JOB["url"]


def test_normalize_job_application_url_uses_apply_url_when_present():
    normalized = remoteok_client.normalize_job(RAW_JOB)

    assert normalized["application_url"] == RAW_JOB["apply_url"]
    assert normalized["absolute_url"] == normalized["application_url"]


def test_normalize_job_application_url_falls_back_to_source_url_without_apply_url():
    raw = {**RAW_JOB}
    del raw["apply_url"]

    normalized = remoteok_client.normalize_job(raw)

    assert normalized["application_url"] == RAW_JOB["url"]
    assert normalized["absolute_url"] == RAW_JOB["url"]


def test_normalize_job_does_not_invent_a_source_url():
    # source_url must come only from the raw "url" field -- never a guessed
    # "https://remoteok.com/remote-jobs/{id}" pattern.
    raw = {**RAW_JOB, "url": "https://remoteok.com/some-other-path/1234567"}

    normalized = remoteok_client.normalize_job(raw)

    assert normalized["source_url"] == "https://remoteok.com/some-other-path/1234567"


def test_normalize_job_maps_date_to_first_published_and_leaves_updated_at_none():
    normalized = remoteok_client.normalize_job(RAW_JOB)

    assert normalized["first_published"] == RAW_JOB["date"]
    assert normalized["updated_at"] is None


def test_normalize_job_defaults_missing_description():
    raw = {**RAW_JOB}
    del raw["description"]

    normalized = remoteok_client.normalize_job(raw)

    assert normalized["content"] == ""


def test_normalize_job_defaults_missing_location():
    raw = {**RAW_JOB}
    del raw["location"]

    normalized = remoteok_client.normalize_job(raw)

    assert normalized["location"] == {"name": ""}


# --- get_remoteok_jobs: metadata discarding and response validation ---

def test_get_remoteok_jobs_discards_the_legal_metadata_object():
    fake_response = Mock()
    fake_response.json.return_value = [LEGAL_METADATA, RAW_JOB]

    with patch.object(remoteok_client.requests, "get", return_value=fake_response):
        jobs = remoteok_client.get_remoteok_jobs()

    assert jobs == [RAW_JOB]


def test_get_remoteok_jobs_sends_explicit_user_agent_and_timeout():
    fake_response = Mock()
    fake_response.json.return_value = [LEGAL_METADATA, RAW_JOB]

    with patch.object(remoteok_client.requests, "get", return_value=fake_response) as mock_get:
        remoteok_client.get_remoteok_jobs()

    _, kwargs = mock_get.call_args
    assert kwargs["headers"]["User-Agent"] == remoteok_client.REMOTEOK_USER_AGENT
    assert kwargs["timeout"] == 10


def test_get_remoteok_jobs_raises_provider_response_error_when_payload_is_not_a_list():
    fake_response = Mock()
    fake_response.json.return_value = {"not": "a list"}

    with patch.object(remoteok_client.requests, "get", return_value=fake_response):
        with pytest.raises(ProviderResponseError):
            remoteok_client.get_remoteok_jobs()


def test_get_remoteok_jobs_wraps_request_exception_in_provider_fetch_error():
    with patch.object(remoteok_client.requests, "get", side_effect=requests.ConnectionError("boom")):
        with pytest.raises(ProviderFetchError) as exc_info:
            remoteok_client.get_remoteok_jobs()

    assert isinstance(exc_info.value.__cause__, requests.ConnectionError)


# --- get_normalized_jobs: incomplete listings are skipped, not fabricated ---

def test_get_normalized_jobs_normalizes_every_usable_raw_job():
    with patch.object(remoteok_client, "get_remoteok_jobs", return_value=[RAW_JOB]):
        jobs = remoteok_client.get_normalized_jobs()

    assert len(jobs) == 1
    assert jobs[0]["id"] == "remoteok:1234567"


def test_get_normalized_jobs_skips_job_without_id():
    raw = {**RAW_JOB}
    del raw["id"]

    with patch.object(remoteok_client, "get_remoteok_jobs", return_value=[raw]):
        jobs = remoteok_client.get_normalized_jobs()

    assert jobs == []


def test_get_normalized_jobs_skips_job_without_position():
    raw = {**RAW_JOB}
    del raw["position"]

    with patch.object(remoteok_client, "get_remoteok_jobs", return_value=[raw]):
        jobs = remoteok_client.get_normalized_jobs()

    assert jobs == []


def test_get_normalized_jobs_skips_job_without_company():
    raw = {**RAW_JOB}
    del raw["company"]

    with patch.object(remoteok_client, "get_remoteok_jobs", return_value=[raw]):
        jobs = remoteok_client.get_normalized_jobs()

    assert jobs == []


def test_get_normalized_jobs_skips_job_without_url():
    raw = {**RAW_JOB}
    del raw["url"]

    with patch.object(remoteok_client, "get_remoteok_jobs", return_value=[raw]):
        jobs = remoteok_client.get_normalized_jobs()

    assert jobs == []


def test_get_normalized_jobs_keeps_usable_jobs_and_drops_incomplete_ones():
    incomplete = {**RAW_JOB, "id": "999"}
    del incomplete["url"]

    with patch.object(remoteok_client, "get_remoteok_jobs", return_value=[RAW_JOB, incomplete]):
        jobs = remoteok_client.get_normalized_jobs()

    assert len(jobs) == 1
    assert jobs[0]["source_job_id"] == "1234567"
