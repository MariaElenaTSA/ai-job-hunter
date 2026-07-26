from datetime import datetime, timedelta, timezone
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

RECENT_ISO = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat().replace("+00:00", "Z")
OLD_ISO = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat().replace("+00:00", "Z")

FAKE_JOBS_WITH_AGE = [
    {**FAKE_GREENHOUSE_JOBS[0], "first_published": RECENT_ISO},
    {**FAKE_GREENHOUSE_JOBS[1], "first_published": OLD_ISO, "updated_at": RECENT_ISO},
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


def test_get_job_includes_remote_and_geo_eligibility():
    with patch.object(job_service, "get_greenhouse_jobs", return_value=FAKE_GREENHOUSE_JOBS):
        job = job_service.get_job(1)

    assert job["remote_eligibility"] in ("eligible", "not_eligible", "ambiguous")
    assert job["geo_eligibility"] in ("eligible", "not_eligible", "ambiguous")
    assert job["remote_eligibility"] == "eligible"  # location is "Remote - LATAM"
    assert job["geo_eligibility"] == "eligible"


def test_get_job_remote_eligibility_is_ambiguous_when_no_modality_signal_present():
    with patch.object(job_service, "get_greenhouse_jobs", return_value=FAKE_GREENHOUSE_JOBS):
        job = job_service.get_job(2)  # location "New York", no remote or on-site signal

    assert job["remote_eligibility"] == "ambiguous"


def test_get_jobs_default_max_age_excludes_old_postings():
    with patch.object(job_service, "get_greenhouse_jobs", return_value=FAKE_JOBS_WITH_AGE):
        jobs = job_service.get_jobs(min_score=0)

    ids = [job["id"] for job in jobs]
    assert 1 in ids
    assert 2 not in ids  # first_published is 60 days old, beyond the 14-day default


def test_get_jobs_max_age_days_zero_disables_age_filter():
    with patch.object(job_service, "get_greenhouse_jobs", return_value=FAKE_JOBS_WITH_AGE):
        jobs = job_service.get_jobs(min_score=0, max_age_days=0)

    ids = [job["id"] for job in jobs]
    assert 1 in ids
    assert 2 in ids  # updated_at is recent, but age must be based on first_published, not updated_at


def test_get_jobs_missing_first_published_is_not_excluded():
    jobs_without_date = [{**FAKE_GREENHOUSE_JOBS[0]}]  # no first_published key

    with patch.object(job_service, "get_greenhouse_jobs", return_value=jobs_without_date):
        jobs = job_service.get_jobs(min_score=0, max_age_days=14)

    assert len(jobs) == 1


def test_get_jobs_invalid_first_published_is_not_excluded():
    jobs_with_invalid_date = [{**FAKE_GREENHOUSE_JOBS[0], "first_published": "not-a-date"}]

    with patch.object(job_service, "get_greenhouse_jobs", return_value=jobs_with_invalid_date):
        jobs = job_service.get_jobs(min_score=0, max_age_days=14)

    assert len(jobs) == 1
