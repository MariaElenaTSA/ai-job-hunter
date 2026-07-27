import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest

from app.services import job_service, remotive_client
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


def patch_providers(greenhouse=None, remoteok=None, remotive=None):
    """Patch all registered providers at once so no test call ever reaches a
    real provider API, even when a test only cares about one of them."""

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
            "remotive": make_getter(remotive),
        },
    )


def patch_greenhouse(jobs):
    return patch_providers(greenhouse=jobs)


def patch_remoteok(jobs):
    return patch_providers(remoteok=jobs)


def patch_remotive(jobs):
    return patch_providers(remotive=jobs)


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


# --- first_published without a timezone (e.g. Remotive's "publication_date") ---
# Regression: comparing a naive datetime against datetime.now(timezone.utc)
# raised an uncaught TypeError (not a ValueError), surfacing as a 500 on
# GET /jobs?sources=remotive&max_age_days=14. A naive timestamp must be
# treated as UTC by convention, the same as a "Z"-suffixed or offset one.

RECENT_NAIVE_ISO = (datetime.now(timezone.utc) - timedelta(days=3)).replace(tzinfo=None).isoformat()
OLD_NAIVE_ISO = (datetime.now(timezone.utc) - timedelta(days=60)).replace(tzinfo=None).isoformat()
RECENT_OFFSET_ISO = (
    (datetime.now(timezone.utc) - timedelta(days=3)).astimezone(timezone(timedelta(hours=-5))).isoformat()
)


def test_get_jobs_naive_recent_first_published_is_not_excluded():
    jobs_with_naive_date = [{**FAKE_GREENHOUSE_JOBS[0], "first_published": RECENT_NAIVE_ISO}]

    with patch_greenhouse(jobs_with_naive_date):
        jobs = job_service.get_jobs(min_score=0, max_age_days=14)

    assert len(jobs) == 1


def test_get_jobs_naive_old_first_published_is_excluded():
    jobs_with_naive_date = [{**FAKE_GREENHOUSE_JOBS[0], "first_published": OLD_NAIVE_ISO}]

    with patch_greenhouse(jobs_with_naive_date):
        jobs = job_service.get_jobs(min_score=0, max_age_days=14)

    assert jobs == []


def test_get_jobs_z_suffixed_first_published_still_works():
    jobs_with_z_date = [{**FAKE_GREENHOUSE_JOBS[0], "first_published": RECENT_ISO}]

    with patch_greenhouse(jobs_with_z_date):
        jobs = job_service.get_jobs(min_score=0, max_age_days=14)

    assert len(jobs) == 1


def test_get_jobs_offset_first_published_is_converted_to_utc_correctly():
    jobs_with_offset_date = [{**FAKE_GREENHOUSE_JOBS[0], "first_published": RECENT_OFFSET_ISO}]

    with patch_greenhouse(jobs_with_offset_date):
        jobs = job_service.get_jobs(min_score=0, max_age_days=14)

    assert len(jobs) == 1


def test_get_jobs_remotive_style_naive_date_does_not_raise_500():
    # The exact reported bug: GET /jobs?sources=remotive&max_age_days=14 raised
    # TypeError before the fix. This job mimics Remotive's raw publication_date
    # format (naive, no "Z"/offset) -- the assertion is simply that this
    # doesn't raise, regardless of how the age filter resolves it over time.
    remotive_job = make_normalized_job(
        301, source="remotive", workplace_type="remote",
        title="Backend Engineer IV", location_name="Worldwide",
        first_published=RECENT_NAIVE_ISO,
    )

    with patch_providers(remotive=[remotive_job]), patch_fixed_profile():
        jobs = job_service.get_jobs(min_score=0, max_age_days=14, sources="remotive")

    assert isinstance(jobs, list)
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


FAKE_REMOTIVE_JOBS = [
    make_normalized_job(
        201, source="remotive", workplace_type="remote",
        title="Backend Engineer IV", location_name="Worldwide", company_name="RemotiveCo",
    ),
]


def test_get_jobs_with_no_sources_includes_all_three_providers():
    with patch_providers(
        greenhouse=FAKE_GREENHOUSE_JOBS, remoteok=FAKE_REMOTEOK_JOBS, remotive=FAKE_REMOTIVE_JOBS
    ), patch_fixed_profile():
        result = job_service.get_jobs(min_score=0, max_age_days=0)

    ids = {job["source_job_id"] for job in result}
    assert {"1", "101", "201"} <= ids


def test_get_jobs_sources_remotive_only_excludes_the_others():
    with patch_providers(
        greenhouse=FAKE_GREENHOUSE_JOBS, remoteok=FAKE_REMOTEOK_JOBS, remotive=FAKE_REMOTIVE_JOBS
    ), patch_fixed_profile():
        result = job_service.get_jobs(min_score=0, max_age_days=0, sources="remotive")

    ids = {job["source_job_id"] for job in result}
    assert ids == {"201"}


def test_get_jobs_sources_all_three_combined_explicitly():
    with patch_providers(
        greenhouse=FAKE_GREENHOUSE_JOBS, remoteok=FAKE_REMOTEOK_JOBS, remotive=FAKE_REMOTIVE_JOBS
    ), patch_fixed_profile():
        result = job_service.get_jobs(
            min_score=0, max_age_days=0, sources="greenhouse,remoteok,remotive"
        )

    ids = {job["source_job_id"] for job in result}
    assert {"1", "101", "201"} <= ids


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
        remotive=ProviderFetchError("remotive down"),
    ):
        with pytest.raises(job_service.AllProvidersFailedError):
            job_service.get_jobs(min_score=0, max_age_days=0)


def test_get_jobs_all_providers_succeed_with_no_jobs_returns_empty_list():
    with patch_providers(greenhouse=[], remoteok=[], remotive=[]):
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


def test_get_job_remotive_id_only_queries_remotive_provider():
    greenhouse_mock = Mock(return_value=[])
    remoteok_mock = Mock(return_value=[])

    with patch.dict(job_service.PROVIDERS, {
        "greenhouse": greenhouse_mock,
        "remoteok": remoteok_mock,
        "remotive": lambda: FAKE_REMOTIVE_JOBS,
    }):
        job = job_service.get_job("remotive:201")

    assert job is not None
    assert job["source"] == "remotive"
    greenhouse_mock.assert_not_called()
    remoteok_mock.assert_not_called()


# --- Remotive cache: shared across /jobs and /jobs/{job_id} ---

def test_get_jobs_and_get_job_share_the_remotive_cache():
    remotive_client._reset_cache()

    fake_raw_job = {
        "id": 555,
        "title": "Remote Backend Engineer",
        "company_name": "RemotiveCo",
        "url": "https://remotive.com/remote-jobs/555",
        "candidate_required_location": "Worldwide",
        "description": "",
        "publication_date": RECENT_ISO,
    }
    fake_response = Mock()
    fake_response.json.return_value = {"jobs": [fake_raw_job]}

    try:
        with patch.object(remotive_client.requests, "get", return_value=fake_response) as mock_get:
            job_service.get_jobs(min_score=0, max_age_days=0, sources="remotive")
            job = job_service.get_job("remotive:555")
    finally:
        remotive_client._reset_cache()

    assert mock_get.call_count == 1  # both calls above were served by the same cached Remotive fetch
    assert job is not None
    assert job["source"] == "remotive"


def test_get_job_raises_provider_error_when_its_provider_is_down():
    with patch_providers(remoteok=ProviderFetchError("remoteok down")):
        with pytest.raises(ProviderFetchError):
            job_service.get_job("remoteok:1")
