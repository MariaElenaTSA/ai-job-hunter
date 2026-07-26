from unittest.mock import patch

from app.services import greenhouse_client

RAW_JOB = {
    "id": 5148165,
    "title": "Solutions Engineer",
    "company_name": "Stripe",
    "location": {"name": "Remote - LATAM"},
    "absolute_url": "https://boards.greenhouse.io/stripe/jobs/5148165",
    "first_published": "2026-07-01T00:00:00Z",
    "updated_at": "2026-07-10T00:00:00Z",
    "language": "en",
    "application_deadline": None,
    "content": "<p>We use SQL and REST APIs daily.</p>",
}


def test_normalize_job_maps_common_fields():
    normalized = greenhouse_client.normalize_job(RAW_JOB)

    assert normalized["source"] == "greenhouse"
    assert normalized["source_job_id"] == "5148165"
    assert normalized["title"] == "Solutions Engineer"
    assert normalized["company_name"] == "Stripe"
    assert normalized["location"] == {"name": "Remote - LATAM"}
    assert normalized["content"] == "<p>We use SQL and REST APIs daily.</p>"
    assert normalized["first_published"] == "2026-07-01T00:00:00Z"
    assert normalized["updated_at"] == "2026-07-10T00:00:00Z"
    assert normalized["language"] == "en"
    assert normalized["application_deadline"] is None
    assert normalized["attribution"] is None


def test_normalize_job_uses_composite_id():
    normalized = greenhouse_client.normalize_job(RAW_JOB)

    assert normalized["id"] == "greenhouse:5148165"


def test_normalize_job_workplace_type_is_none():
    # Greenhouse has no structured modality field -- scoring_service still
    # derives remote/geo eligibility from location and content directly.
    normalized = greenhouse_client.normalize_job(RAW_JOB)

    assert normalized["workplace_type"] is None


def test_normalize_job_absolute_url_matches_application_url():
    normalized = greenhouse_client.normalize_job(RAW_JOB)

    assert normalized["source_url"] == RAW_JOB["absolute_url"]
    assert normalized["application_url"] == RAW_JOB["absolute_url"]
    assert normalized["absolute_url"] == normalized["application_url"]


def test_normalize_job_defaults_missing_content_and_company_name():
    minimal_job = {
        "id": 1,
        "title": "Support Engineer",
        "location": {"name": "Remote"},
        "absolute_url": "https://example.com/1",
    }

    normalized = greenhouse_client.normalize_job(minimal_job)

    assert normalized["content"] == ""
    assert normalized["company_name"] == "Stripe"


def test_get_normalized_jobs_normalizes_every_raw_job():
    with patch.object(greenhouse_client, "get_greenhouse_jobs", return_value=[RAW_JOB]):
        jobs = greenhouse_client.get_normalized_jobs()

    assert len(jobs) == 1
    assert jobs[0]["id"] == "greenhouse:5148165"
