from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app.services import job_service


def make_normalized_job(
    source_job_id,
    title="Solutions Engineer",
    location_name="Remote - LATAM",
    company_name="Stripe",
    content="",
    first_published=None,
    updated_at=None,
):
    source_job_id = str(source_job_id)
    url = f"https://example.com/{source_job_id}"

    return {
        "id": f"greenhouse:{source_job_id}",
        "source": "greenhouse",
        "source_job_id": source_job_id,
        "title": title,
        "company_name": company_name,
        "location": {"name": location_name},
        "workplace_type": None,
        "content": content,
        "first_published": first_published,
        "updated_at": updated_at,
        "language": None,
        "application_deadline": None,
        "source_url": url,
        "application_url": url,
        "absolute_url": url,
        "attribution": None,
    }


def patch_greenhouse(jobs):
    return patch.dict(job_service.PROVIDERS, {"greenhouse": lambda: jobs})


# A profile with no keyword overlap with our test titles/content, so score
# stays deterministically at 0 and only eligibility/date/description-length
# decide the ranking. "latam" makes "Remote - LATAM" geo-eligible.
FIXED_PROFILE = {
    "target_roles": [],
    "preferred_responsibilities": [],
    "skill_names": [],
    "tool_names": [],
    "geo_eligibility": {"acceptable_scopes": ["latam"]},
}


def patch_fixed_profile():
    return patch.object(job_service, "get_scoring_profile", return_value=FIXED_PROFILE)


FAKE_GREENHOUSE_JOBS = [
    make_normalized_job(1, title="Solutions Engineer", location_name="Remote - LATAM", company_name="Stripe"),
    make_normalized_job(2, title="Support Agent", location_name="New York", company_name="Acme"),
]

RECENT_ISO = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat().replace("+00:00", "Z")
OLD_ISO = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat().replace("+00:00", "Z")

FAKE_JOBS_WITH_AGE = [
    {**FAKE_GREENHOUSE_JOBS[0], "first_published": RECENT_ISO},
    {**FAKE_GREENHOUSE_JOBS[1], "first_published": OLD_ISO, "updated_at": RECENT_ISO},
]


def test_get_jobs_still_responds():
    with patch_greenhouse(FAKE_GREENHOUSE_JOBS):
        jobs = job_service.get_jobs(min_score=0)

    assert isinstance(jobs, list)
    assert len(jobs) > 0


def test_get_jobs_loads_candidate_profile_only_once_per_call():
    with patch_greenhouse(FAKE_GREENHOUSE_JOBS), \
         patch.object(job_service, "load_candidate_profile", wraps=job_service.load_candidate_profile) as mock_load:
        job_service.get_jobs(min_score=0)

    assert mock_load.call_count == 1


def test_get_job_returns_scored_job():
    with patch_greenhouse(FAKE_GREENHOUSE_JOBS):
        job = job_service.get_job("1")

    assert job is not None
    assert job["id"] == "greenhouse:1"
    assert job["score"] > 0


def test_get_job_includes_remote_and_geo_eligibility():
    with patch_greenhouse(FAKE_GREENHOUSE_JOBS):
        job = job_service.get_job("1")

    assert job["remote_eligibility"] in ("eligible", "not_eligible", "ambiguous")
    assert job["geo_eligibility"] in ("eligible", "not_eligible", "ambiguous")
    assert job["remote_eligibility"] == "eligible"  # location is "Remote - LATAM"
    assert job["geo_eligibility"] == "eligible"


def test_get_job_remote_eligibility_is_ambiguous_when_no_modality_signal_present():
    with patch_greenhouse(FAKE_GREENHOUSE_JOBS):
        job = job_service.get_job("2")  # location "New York", no remote or on-site signal

    assert job["remote_eligibility"] == "ambiguous"


def test_get_jobs_default_max_age_excludes_old_postings():
    with patch_greenhouse(FAKE_JOBS_WITH_AGE):
        jobs = job_service.get_jobs(min_score=0)

    ids = [job["source_job_id"] for job in jobs]
    assert "1" in ids
    assert "2" not in ids  # first_published is 60 days old, beyond the 14-day default


def test_get_jobs_max_age_days_zero_disables_age_filter():
    with patch_greenhouse(FAKE_JOBS_WITH_AGE):
        jobs = job_service.get_jobs(min_score=0, max_age_days=0)

    ids = [job["source_job_id"] for job in jobs]
    assert "1" in ids
    assert "2" in ids  # updated_at is recent, but age must be based on first_published, not updated_at


def test_get_jobs_missing_first_published_is_not_excluded():
    jobs_without_date = [{**FAKE_GREENHOUSE_JOBS[0], "first_published": None}]

    with patch_greenhouse(jobs_without_date):
        jobs = job_service.get_jobs(min_score=0, max_age_days=14)

    assert len(jobs) == 1


def test_get_jobs_invalid_first_published_is_not_excluded():
    jobs_with_invalid_date = [{**FAKE_GREENHOUSE_JOBS[0], "first_published": "not-a-date"}]

    with patch_greenhouse(jobs_with_invalid_date):
        jobs = job_service.get_jobs(min_score=0, max_age_days=14)

    assert len(jobs) == 1


# --- Composite IDs ---

def test_get_jobs_results_use_composite_ids():
    with patch_greenhouse(FAKE_GREENHOUSE_JOBS):
        jobs = job_service.get_jobs(min_score=0)

    assert all(job["id"].startswith("greenhouse:") for job in jobs)


def test_get_job_accepts_composite_id():
    with patch_greenhouse(FAKE_GREENHOUSE_JOBS):
        job = job_service.get_job("greenhouse:1")

    assert job is not None
    assert job["source_job_id"] == "1"


def test_get_job_accepts_legacy_id_without_source_prefix():
    with patch_greenhouse(FAKE_GREENHOUSE_JOBS):
        job = job_service.get_job("1")

    assert job is not None
    assert job["source_job_id"] == "1"


def test_get_job_unknown_source_returns_none():
    with patch_greenhouse(FAKE_GREENHOUSE_JOBS):
        job = job_service.get_job("unknownsource:1")

    assert job is None


# --- Eligibility exclusion: only applied to get_jobs, not get_job ---

NOT_ELIGIBLE_REMOTE_JOB = make_normalized_job(
    3, title="Office Manager", location_name="On-site - New York", company_name="Acme"
)
NOT_ELIGIBLE_GEO_JOB = make_normalized_job(
    4, title="Support Engineer", location_name="Remote (US Only)", company_name="Acme"
)


def test_get_jobs_excludes_remote_not_eligible():
    with patch_greenhouse([NOT_ELIGIBLE_REMOTE_JOB]):
        jobs = job_service.get_jobs(min_score=0, max_age_days=0)

    assert jobs == []


def test_get_jobs_excludes_geo_not_eligible():
    with patch_greenhouse([NOT_ELIGIBLE_GEO_JOB]):
        jobs = job_service.get_jobs(min_score=0, max_age_days=0)

    assert jobs == []


def test_get_job_returns_not_eligible_job_directly():
    with patch_greenhouse([NOT_ELIGIBLE_REMOTE_JOB]):
        job = job_service.get_job("3")

    assert job is not None
    assert job["remote_eligibility"] == "not_eligible"


def test_get_job_returns_geo_not_eligible_job_directly():
    with patch_greenhouse([NOT_ELIGIBLE_GEO_JOB]):
        job = job_service.get_job("4")

    assert job is not None
    assert job["geo_eligibility"] == "not_eligible"


# --- Result cap and ranking ---

def test_get_jobs_caps_at_20_results():
    now = datetime.now(timezone.utc)
    jobs = [
        make_normalized_job(
            i + 1,
            title="Backend Engineer IV",
            location_name="Remote - LATAM",
            first_published=(now - timedelta(days=i)).isoformat().replace("+00:00", "Z"),
        )
        for i in range(25)
    ]

    with patch_greenhouse(jobs), patch_fixed_profile():
        result = job_service.get_jobs(min_score=0, max_age_days=0)

    assert len(result) == 20
    result_ids = {job["source_job_id"] for job in result}
    assert result_ids == {str(i) for i in range(1, 21)}  # the 20 most recently published


def test_get_jobs_tie_break_prefers_confirmed_eligibility_over_recency():
    older_but_eligible = make_normalized_job(
        1, title="Backend Engineer IV", location_name="Remote - LATAM", first_published=OLD_ISO
    )
    newer_but_ambiguous = make_normalized_job(
        2, title="Backend Engineer IV", location_name="New York", first_published=RECENT_ISO
    )

    with patch_greenhouse([newer_but_ambiguous, older_but_eligible]), patch_fixed_profile():
        result = job_service.get_jobs(min_score=0, max_age_days=0)

    assert [job["source_job_id"] for job in result] == ["1", "2"]


def test_get_jobs_tie_break_prefers_more_complete_description():
    short = make_normalized_job(
        1, title="Backend Engineer IV", location_name="Remote - LATAM",
        content="Lorem ipsum", first_published=RECENT_ISO,
    )
    long = make_normalized_job(
        2, title="Backend Engineer IV", location_name="Remote - LATAM",
        content="Lorem ipsum dolor sit amet consectetur adipiscing elit", first_published=RECENT_ISO,
    )

    with patch_greenhouse([short, long]), patch_fixed_profile():
        result = job_service.get_jobs(min_score=0, max_age_days=0)

    assert [job["source_job_id"] for job in result] == ["2", "1"]


def test_get_jobs_ranking_tolerates_missing_or_invalid_dates():
    valid = make_normalized_job(
        1, title="Backend Engineer IV", location_name="Remote - LATAM", first_published=RECENT_ISO
    )
    missing = make_normalized_job(
        2, title="Backend Engineer IV", location_name="Remote - LATAM", first_published=None
    )
    invalid = make_normalized_job(
        3, title="Backend Engineer IV", location_name="Remote - LATAM", first_published="not-a-date"
    )

    with patch_greenhouse([missing, invalid, valid]), patch_fixed_profile():
        result = job_service.get_jobs(min_score=0, max_age_days=0)

    assert len(result) == 3  # no exception raised, nothing dropped
    assert result[0]["source_job_id"] == "1"  # the valid, recent date ranks first among ties
