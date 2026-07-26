from unittest.mock import patch

from app.services import job_service

FAKE_GREENHOUSE_JOBS = [
    {
        "id": 1,
        "title": "Solutions Engineer",
        "company_name": "Stripe",
        "location": {"name": "Remote - LATAM"},
        "absolute_url": "https://example.com/1",
    },
    {
        "id": 2,
        "title": "Support Agent",
        "company_name": "Acme",
        "location": {"name": "New York"},
        "absolute_url": "https://example.com/2",
    },
]


def test_get_jobs_still_responds():
    with patch.object(job_service, "get_greenhouse_jobs", return_value=FAKE_GREENHOUSE_JOBS):
        jobs = job_service.get_jobs(min_score=0)

    assert isinstance(jobs, list)
    assert len(jobs) > 0


def test_get_jobs_loads_candidate_profile_only_once_per_call():
    with patch.object(job_service, "get_greenhouse_jobs", return_value=FAKE_GREENHOUSE_JOBS), \
         patch.object(job_service, "load_candidate_profile", wraps=job_service.load_candidate_profile) as mock_load:
        job_service.get_jobs(min_score=0)

    assert mock_load.call_count == 1


def test_get_job_returns_scored_job():
    with patch.object(job_service, "get_greenhouse_jobs", return_value=FAKE_GREENHOUSE_JOBS):
        job = job_service.get_job(1)

    assert job is not None
    assert job["id"] == 1
    assert job["score"] > 0
