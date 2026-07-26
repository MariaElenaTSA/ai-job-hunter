from app.services.candidate_service import get_scoring_profile, load_candidate_profile
from app.services.greenhouse_client import get_greenhouse_jobs
from app.services.scoring_service import calculate_score
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
        "description_length": len(job.get("content", "")),
        "has_description": bool(job.get("content")),
        "score": calculate_score(job, profile=profile),
    }

def get_jobs(min_score: int = MIN_SCORE):
    profile = get_scoring_profile(load_candidate_profile())
    data = get_greenhouse_jobs()
    jobs = []

    for job in data[:10]:
        jobs.append(format_job(job, profile))

    jobs = [job for job in jobs if job["score"] >= min_score]
    jobs.sort(key=lambda job: job["score"], reverse=True)
    return jobs[:10]

def get_job(job_id: int):
    profile = get_scoring_profile(load_candidate_profile())
    data = get_greenhouse_jobs()

    for job in data:
        if job["id"] == job_id:
            return format_job(job, profile)

    return None