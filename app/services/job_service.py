from app.services.greenhouse_client import get_greenhouse_jobs


def get_jobs():
    data = get_greenhouse_jobs()
    jobs = []

    for job in data["jobs"][:10]:
        jobs.append({
            "id": job["id"],
            "title": job["title"],
            "company_name": job.get("company_name", "Stripe"),
            "location": job["location"]["name"],
            "absolute_url": job["absolute_url"],
            "first_published": job.get("first_published"),
            "updated_at": job.get("updated_at"),
            "language": job.get("language"),
            "application_deadline": job.get("application_deadline")
        })

    return jobs