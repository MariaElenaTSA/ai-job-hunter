import threading
import time
from unittest.mock import Mock, patch

import pytest
import requests

from app.services import remotive_client
from app.services.provider_errors import ProviderFetchError, ProviderResponseError

RAW_JOB = {
    "id": 2091035,
    "title": "Mid/Senior AI Cinematic Video Editor",
    "company_name": "EverAI",
    "url": "https://remotive.com/remote-jobs/artificial-intelligence/mid-senior-ai-cinematic-video-editor-2091035",
    "candidate_required_location": "Worldwide",
    "description": "<p>Build our backend in Python.</p>",
    "publication_date": "2026-07-24T10:33:35",
}


@pytest.fixture(autouse=True)
def _reset_remotive_cache():
    remotive_client._reset_cache()
    yield
    remotive_client._reset_cache()


def _fake_response(payload):
    response = Mock()
    response.json.return_value = payload
    return response


# --- normalize_job ---

def test_normalize_job_maps_common_fields():
    normalized = remotive_client.normalize_job(RAW_JOB)

    assert normalized["source"] == "remotive"
    assert normalized["source_job_id"] == "2091035"
    assert normalized["title"] == "Mid/Senior AI Cinematic Video Editor"
    assert normalized["company_name"] == "EverAI"
    assert normalized["location"] == {"name": "Worldwide"}
    assert normalized["content"] == "<p>Build our backend in Python.</p>"
    assert normalized["language"] is None
    assert normalized["application_deadline"] is None
    assert normalized["attribution"] == "Remotive"


def test_normalize_job_uses_composite_id():
    normalized = remotive_client.normalize_job(RAW_JOB)

    assert normalized["id"] == "remotive:2091035"


def test_normalize_job_workplace_type_is_remote():
    normalized = remotive_client.normalize_job(RAW_JOB)

    assert normalized["workplace_type"] == "remote"


def test_normalize_job_source_url_application_url_and_absolute_url_share_the_same_url():
    normalized = remotive_client.normalize_job(RAW_JOB)

    assert normalized["source_url"] == RAW_JOB["url"]
    assert normalized["application_url"] == RAW_JOB["url"]
    assert normalized["absolute_url"] == RAW_JOB["url"]


def test_normalize_job_maps_publication_date_to_first_published_and_leaves_updated_at_none():
    normalized = remotive_client.normalize_job(RAW_JOB)

    assert normalized["first_published"] == RAW_JOB["publication_date"]
    assert normalized["updated_at"] is None


def test_normalize_job_defaults_missing_description():
    raw = {**RAW_JOB}
    del raw["description"]

    normalized = remotive_client.normalize_job(raw)

    assert normalized["content"] == ""


def test_normalize_job_defaults_missing_location():
    raw = {**RAW_JOB}
    del raw["candidate_required_location"]

    normalized = remotive_client.normalize_job(raw)

    assert normalized["location"] == {"name": ""}


# --- _fetch_remotive_jobs: response validation and error wrapping ---

def test_fetch_remotive_jobs_raises_provider_response_error_when_jobs_key_is_not_a_list():
    with patch.object(remotive_client.requests, "get", return_value=_fake_response({"jobs": "not-a-list"})):
        with pytest.raises(ProviderResponseError):
            remotive_client.get_remotive_jobs()


def test_fetch_remotive_jobs_raises_provider_response_error_when_payload_is_not_a_dict():
    with patch.object(remotive_client.requests, "get", return_value=_fake_response(["not", "a", "dict"])):
        with pytest.raises(ProviderResponseError):
            remotive_client.get_remotive_jobs()


def test_fetch_remotive_jobs_wraps_request_exception_in_provider_fetch_error():
    with patch.object(remotive_client.requests, "get", side_effect=requests.ConnectionError("boom")):
        with pytest.raises(ProviderFetchError) as exc_info:
            remotive_client.get_remotive_jobs()

    assert isinstance(exc_info.value.__cause__, requests.ConnectionError)


def test_get_remotive_jobs_sends_explicit_user_agent_and_timeout():
    with patch.object(remotive_client.requests, "get", return_value=_fake_response({"jobs": [RAW_JOB]})) as mock_get:
        remotive_client.get_remotive_jobs()

    _, kwargs = mock_get.call_args
    assert kwargs["headers"]["User-Agent"] == remotive_client.REMOTIVE_USER_AGENT
    assert kwargs["timeout"] == 10


# --- get_normalized_jobs: incomplete listings are skipped, not fabricated ---

def test_get_normalized_jobs_normalizes_every_usable_raw_job():
    with patch.object(remotive_client, "get_remotive_jobs", return_value=[RAW_JOB]):
        jobs = remotive_client.get_normalized_jobs()

    assert len(jobs) == 1
    assert jobs[0]["id"] == "remotive:2091035"


def test_get_normalized_jobs_skips_job_without_id():
    raw = {**RAW_JOB}
    del raw["id"]

    with patch.object(remotive_client, "get_remotive_jobs", return_value=[raw]):
        jobs = remotive_client.get_normalized_jobs()

    assert jobs == []


def test_get_normalized_jobs_skips_job_without_title():
    raw = {**RAW_JOB}
    del raw["title"]

    with patch.object(remotive_client, "get_remotive_jobs", return_value=[raw]):
        jobs = remotive_client.get_normalized_jobs()

    assert jobs == []


def test_get_normalized_jobs_skips_job_without_company_name():
    raw = {**RAW_JOB}
    del raw["company_name"]

    with patch.object(remotive_client, "get_remotive_jobs", return_value=[raw]):
        jobs = remotive_client.get_normalized_jobs()

    assert jobs == []


def test_get_normalized_jobs_skips_job_without_url():
    raw = {**RAW_JOB}
    del raw["url"]

    with patch.object(remotive_client, "get_remotive_jobs", return_value=[raw]):
        jobs = remotive_client.get_normalized_jobs()

    assert jobs == []


def test_get_normalized_jobs_keeps_usable_jobs_and_drops_incomplete_ones():
    incomplete = {**RAW_JOB, "id": 999}
    del incomplete["url"]

    with patch.object(remotive_client, "get_remotive_jobs", return_value=[RAW_JOB, incomplete]):
        jobs = remotive_client.get_normalized_jobs()

    assert len(jobs) == 1
    assert jobs[0]["source_job_id"] == "2091035"


# --- Cache: TTL, reuse, failure isolation, and thread-safety ---

def test_get_remotive_jobs_reuses_cache_for_consecutive_calls():
    with patch.object(remotive_client.requests, "get", return_value=_fake_response({"jobs": [RAW_JOB]})) as mock_get:
        first = remotive_client.get_remotive_jobs()
        second = remotive_client.get_remotive_jobs()

    assert mock_get.call_count == 1
    assert first == second == [RAW_JOB]


def test_get_remotive_jobs_refetches_after_ttl_expires():
    fake_now = {"t": 1_000.0}

    def fake_monotonic():
        return fake_now["t"]

    with patch.object(remotive_client.time, "monotonic", side_effect=fake_monotonic), \
         patch.object(remotive_client.requests, "get", return_value=_fake_response({"jobs": [RAW_JOB]})) as mock_get:
        remotive_client.get_remotive_jobs()
        fake_now["t"] += remotive_client._CACHE_TTL_SECONDS + 1
        remotive_client.get_remotive_jobs()

    assert mock_get.call_count == 2


def test_get_remotive_jobs_does_not_cache_a_failed_response():
    with patch.object(remotive_client.requests, "get", side_effect=requests.ConnectionError("boom")):
        with pytest.raises(ProviderFetchError):
            remotive_client.get_remotive_jobs()

    with patch.object(remotive_client.requests, "get", return_value=_fake_response({"jobs": [RAW_JOB]})) as mock_get:
        jobs = remotive_client.get_remotive_jobs()

    assert mock_get.call_count == 1  # the failed attempt above was never cached, so this call had to hit the network
    assert jobs == [RAW_JOB]


def test_get_remotive_jobs_concurrent_calls_against_an_empty_cache_produce_a_single_request():
    call_count = {"n": 0}
    count_lock = threading.Lock()

    def slow_get(*args, **kwargs):
        with count_lock:
            call_count["n"] += 1
        # A small, deliberate delay widens the window in which a second
        # thread could race past a buggy (non-double-checked) cache and fire
        # its own request. No real network or long sleep is involved.
        time.sleep(0.05)
        return _fake_response({"jobs": [RAW_JOB]})

    results = [None, None]

    def worker(index):
        results[index] = remotive_client.get_remotive_jobs()

    with patch.object(remotive_client.requests, "get", side_effect=slow_get):
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

    assert call_count["n"] == 1
    assert results[0] == [RAW_JOB]
    assert results[1] == [RAW_JOB]
