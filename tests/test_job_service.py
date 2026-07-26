import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest

from app.services import job_service
from app.services.provider_errors import ProviderFetchError, ProviderResponseError


def make_normalized_job(
    source_job_id,
    title="Solutions Engineer",
    location_name="Remote - LATAM",
    company_name="Stripe",
    content="",
    first_published=None,
    updated_at=None,
    source="greenhouse",
    workplace_type=None,
):
    source_job_id = str(source_job_id)
    url = f"https://example.com/{source_job_id}"

    return {
        "id": f"{source}:{source_job_id}",
        "source": source,
        "source_job_id": source_job_id,
        "title": title,
        "company_name": company_name,
        "location": {"name": location_name},
        "workplace_type": workplace_type,
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


def patch_providers(greenhouse=None, remoteok=None):
    """Patch both providers at once so no test call ever reaches the real
    Greenhouse or Remote OK APIs, even when a test only cares about one of them."""

    def make_getter(jobs_or_error):
        if isinstance(jobs_or_error, Exception):
            def raise_error():
                raise jobs_or_error
            return raise_error
        jobs = jobs_or_error if jobs_or_error is not None else []
        return lambda: jobs

    return patch.dict(
        job_service.PROVIDERS,
        {
            "greenhouse": make_getter(greenhouse),
            "remoteok": make_getter(remoteok),
        },
    )


def patch_greenhouse(jobs):
    return patch_providers(greenhouse=jobs)


def patch_remoteok(jobs):
    return patch_providers(remoteok=jobs)


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


# --- Multi-provider: sources selection ---

FAKE_REMOTEOK_JOBS = [
    make_normalized_job(
        101, source="remoteok", workplace_type="remote",
        title="Backend Engineer IV", location_name="Worldwide", company_name="RemoteCo",
    ),
]


def test_get_jobs_with_no_sources_combines_all_providers():
    with patch_providers(greenhouse=FAKE_GREENHOUSE_JOBS, remoteok=FAKE_REMOTEOK_JOBS), patch_fixed_profile():
        result = job_service.get_jobs(min_score=0, max_age_days=0)

    ids = {job["source_job_id"] for job in result}
    assert "1" in ids  # greenhouse
    assert "101" in ids  # remoteok


def test_get_jobs_sources_greenhouse_only_excludes_remoteok():
    with patch_providers(greenhouse=FAKE_GREENHOUSE_JOBS, remoteok=FAKE_REMOTEOK_JOBS), patch_fixed_profile():
        result = job_service.get_jobs(min_score=0, max_age_days=0, sources="greenhouse")

    ids = {job["source_job_id"] for job in result}
    assert "101" not in ids


def test_get_jobs_sources_remoteok_only_excludes_greenhouse():
    with patch_providers(greenhouse=FAKE_GREENHOUSE_JOBS, remoteok=FAKE_REMOTEOK_JOBS), patch_fixed_profile():
        result = job_service.get_jobs(min_score=0, max_age_days=0, sources="remoteok")

    ids = {job["source_job_id"] for job in result}
    assert ids == {"101"}


def test_get_jobs_sources_combined_with_whitespace_and_duplicates():
    with patch_providers(greenhouse=FAKE_GREENHOUSE_JOBS, remoteok=FAKE_REMOTEOK_JOBS), patch_fixed_profile():
        result = job_service.get_jobs(min_score=0, max_age_days=0, sources=" Greenhouse ,remoteok, greenhouse")

    ids = {job["source_job_id"] for job in result}
    assert "1" in ids
    assert "101" in ids


def test_get_jobs_sources_empty_string_raises_unknown_source_error():
    with patch_providers(greenhouse=FAKE_GREENHOUSE_JOBS):
        with pytest.raises(job_service.UnknownSourceError):
            job_service.get_jobs(sources="")


def test_get_jobs_sources_only_commas_and_spaces_raises_unknown_source_error():
    with patch_providers(greenhouse=FAKE_GREENHOUSE_JOBS):
        with pytest.raises(job_service.UnknownSourceError):
            job_service.get_jobs(sources=" , , ")


def test_get_jobs_sources_unknown_name_raises_unknown_source_error():
    with patch_providers(greenhouse=FAKE_GREENHOUSE_JOBS):
        with pytest.raises(job_service.UnknownSourceError):
            job_service.get_jobs(sources="bogus")


# --- Multi-provider: partial and total failure ---

def test_get_jobs_partial_failure_returns_the_working_providers_results(caplog):
    with patch_providers(greenhouse=ProviderFetchError("greenhouse down"), remoteok=FAKE_REMOTEOK_JOBS), \
         patch_fixed_profile(), \
         caplog.at_level(logging.WARNING):
        result = job_service.get_jobs(min_score=0, max_age_days=0)

    ids = {job["source_job_id"] for job in result}
    assert ids == {"101"}
    assert any("greenhouse" in record.getMessage() for record in caplog.records)


def test_get_jobs_total_failure_raises_all_providers_failed_error():
    with patch_providers(
        greenhouse=ProviderFetchError("greenhouse down"),
        remoteok=ProviderResponseError("remoteok bad payload"),
    ):
        with pytest.raises(job_service.AllProvidersFailedError):
            job_service.get_jobs(min_score=0, max_age_days=0)


def test_get_jobs_all_providers_succeed_with_no_jobs_returns_empty_list():
    with patch_providers(greenhouse=[], remoteok=[]):
        result = job_service.get_jobs(min_score=0, max_age_days=0)

    assert result == []


def test_get_jobs_does_not_absorb_unexpected_programming_errors():
    def raise_type_error():
        raise TypeError("unexpected bug, not a provider outage")

    with patch.dict(job_service.PROVIDERS, {"greenhouse": raise_type_error, "remoteok": lambda: []}):
        with pytest.raises(TypeError):
            job_service.get_jobs(min_score=0, max_age_days=0)


# --- Multi-provider: top 20 applies after combining ---

def test_get_jobs_caps_at_20_after_combining_both_providers():
    now = datetime.now(timezone.utc)
    greenhouse_jobs = [
        make_normalized_job(
            i + 1, title="Backend Engineer IV", location_name="Remote - LATAM",
            first_published=(now - timedelta(days=i)).isoformat().replace("+00:00", "Z"),
        )
        for i in range(15)
    ]
    remoteok_jobs = [
        make_normalized_job(
            i + 1, source="remoteok", workplace_type="remote",
            title="Backend Engineer IV", location_name="Worldwide",
            first_published=(now - timedelta(days=i)).isoformat().replace("+00:00", "Z"),
        )
        for i in range(15)
    ]

    with patch_providers(greenhouse=greenhouse_jobs, remoteok=remoteok_jobs), patch_fixed_profile():
        result = job_service.get_jobs(min_score=0, max_age_days=0)

    assert len(result) == 20  # combined pool has 30 candidates, capped only after merging both providers


# --- get_job: provider isolation and failure propagation ---

def test_get_job_remoteok_id_only_queries_remoteok_provider():
    greenhouse_mock = Mock(return_value=[])

    with patch.dict(job_service.PROVIDERS, {"greenhouse": greenhouse_mock, "remoteok": lambda: FAKE_REMOTEOK_JOBS}):
        job = job_service.get_job("remoteok:101")

    assert job is not None
    assert job["source"] == "remoteok"
    greenhouse_mock.assert_not_called()


def test_get_job_raises_provider_error_when_its_provider_is_down():
    with patch_providers(remoteok=ProviderFetchError("remoteok down")):
        with pytest.raises(ProviderFetchError):
            job_service.get_job("remoteok:1")
