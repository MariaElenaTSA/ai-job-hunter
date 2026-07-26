from datetime import datetime, timedelta, timezone

from app.config import DEFAULT_MAX_AGE_DAYS, MAX_RESULTS
from app.services import greenhouse_client
from app.services.candidate_service import get_scoring_profile, load_candidate_profile
from app.services.scoring_service import (
    calculate_geo_eligibility,
    calculate_remote_eligibility,
    calculate_score,
)
from app.profile import MIN_SCORE

# Single source of truth for which providers exist and how to reach them.
# Adding a provider means adding one entry here -- nothing else keeps its own
# list of source names.
PROVIDERS = {
    "greenhouse": greenhouse_client.get_normalized_jobs,
}

def format_job(job, profile):
    return {
        "id": job["id"],
        "source": job["source"],
        "source_job_id": job["source_job_id"],
        "title": job["title"],
        "company_name": job.get("company_name", "Stripe"),
        "location": job["location"]["name"],
        "workplace_type": job.get("workplace_type"),
        "source_url": job.get("source_url"),
        "application_url": job.get("application_url"),
        "absolute_url": job.get("absolute_url"),
        "attribution": job.get("attribution"),
        "first_published": job.get("first_published"),
        "updated_at": job.get("updated_at"),
        "language": job.get("language"),
        "application_deadline": job.get("application_deadline"),
        "description": job.get("content", ""),
        "description_length": len(job.get("content", "")),
        "has_description": bool(job.get("content")),
        "score": calculate_score(job, profile=profile),
        "remote_eligibility": calculate_remote_eligibility(job, profile=profile),
        "geo_eligibility": calculate_geo_eligibility(job, profile=profile),
    }

def _is_within_max_age(job: dict, max_age_days: int | None) -> bool:
    """0 or None means no age limit. A missing or unparseable first_published
    never excludes a job -- absence of data is not evidence of an old posting."""
    if not max_age_days:
        return True

    first_published = job.get("first_published")

    if not first_published:
        return True

    try:
        published_at = datetime.fromisoformat(first_published.replace("Z", "+00:00"))
    except ValueError:
        return True

    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    return published_at >= cutoff

def _first_published_epoch(job: dict) -> float:
    """Missing or unparseable dates rank as oldest, never breaking the sort."""
    first_published = job.get("first_published")

    if not first_published:
        return float("-inf")

    try:
        return datetime.fromisoformat(first_published.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return float("-inf")

def _ranking_key(job: dict):
    eligibility_confirmed = (
        job["remote_eligibility"] == "eligible" and job["geo_eligibility"] == "eligible"
    )
    return (
        -job["score"],
        0 if eligibility_confirmed else 1,  # confirmed eligible before ambiguous
        -_first_published_epoch(job),        # most recent first
        -job["description_length"],          # most complete description first
    )

def _parse_job_id(job_id: str) -> tuple[str, str]:
    if ":" in job_id:
        source, source_job_id = job_id.split(":", 1)
        return source, source_job_id

    # Backward compatibility: pre-multi-provider IDs had no source prefix.
    return "greenhouse", job_id

def get_jobs(min_score: int = MIN_SCORE, max_age_days: int | None = DEFAULT_MAX_AGE_DAYS):
    profile = get_scoring_profile(load_candidate_profile())

    normalized_jobs = []
    for get_provider_jobs in PROVIDERS.values():
        normalized_jobs.extend(get_provider_jobs())

    normalized_jobs = [job for job in normalized_jobs if _is_within_max_age(job, max_age_days)]

    jobs = [format_job(job, profile) for job in normalized_jobs]
    jobs = [job for job in jobs if job["score"] >= min_score]
    # Excluded only from this recommended list, not from direct get_job lookups.
    jobs = [job for job in jobs if job["remote_eligibility"] != "not_eligible"]
    jobs = [job for job in jobs if job["geo_eligibility"] != "not_eligible"]

    jobs.sort(key=_ranking_key)
    return jobs[:MAX_RESULTS]

def get_job(job_id: str):
    profile = get_scoring_profile(load_candidate_profile())
    source, source_job_id = _parse_job_id(job_id)
    get_provider_jobs = PROVIDERS.get(source)

    if get_provider_jobs is None:
        return None

    for job in get_provider_jobs():
        if job["source_job_id"] == source_job_id:
            return format_job(job, profile)

    return None