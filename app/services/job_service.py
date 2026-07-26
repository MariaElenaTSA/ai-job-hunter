from datetime import datetime, timedelta, timezone

from app.config import DEFAULT_MAX_AGE_DAYS
from app.services.candidate_service import get_scoring_profile, load_candidate_profile
from app.services.greenhouse_client import get_greenhouse_jobs
from app.services.scoring_service import (
    calculate_geo_eligibility,
    calculate_remote_eligibility,
    calculate_score,
)
from app.profile import MIN_SCORE

def format_job(job, profile):
    return {
        "id": job["id"],
        "title": job["title"],
        "company_name": job.get("company_name", "Stripe"),
        "location": job["location"]["name"],
        "absolute_url": job["absolute_url"],
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

def get_jobs(min_score: int = MIN_SCORE, max_age_days: int | None = DEFAULT_MAX_AGE_DAYS):
    profile = get_scoring_profile(load_candidate_profile())
    data = get_greenhouse_jobs()
    jobs = []

    for job in data[:10]:
        jobs.append(format_job(job, profile))

    jobs = [job for job in jobs if job["score"] >= min_score]
    jobs = [job for job in jobs if _is_within_max_age(job, max_age_days)]
    jobs.sort(key=lambda job: job["score"], reverse=True)
    return jobs[:10]

def get_job(job_id: int):
    profile = get_scoring_profile(load_candidate_profile())
    data = get_greenhouse_jobs()

    for job in data:
        if job["id"] == job_id:
            return format_job(job, profile)

    return None