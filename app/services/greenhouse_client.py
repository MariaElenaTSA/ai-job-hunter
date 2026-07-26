import requests

GREENHOUSE_URL = "https://boards-api.greenhouse.io/v1/boards/stripe/jobs?content=true"


def get_greenhouse_jobs():
    response = requests.get(GREENHOUSE_URL, timeout=10)
    response.raise_for_status()
    return response.json()["jobs"]


def normalize_job(raw: dict) -> dict:
    """Map a raw Greenhouse job into the common cross-provider job format.

    Greenhouse has no structured remote/hybrid/onsite field, so workplace_type
    is left as None here -- scoring_service still derives remote/geo
    eligibility from location and content directly, unchanged.
    """
    source_job_id = str(raw["id"])
    application_url = raw["absolute_url"]

    return {
        "id": f"greenhouse:{source_job_id}",
        "source": "greenhouse",
        "source_job_id": source_job_id,
        "title": raw["title"],
        "company_name": raw.get("company_name", "Stripe"),
        "location": {"name": raw["location"]["name"]},
        "workplace_type": None,
        "content": raw.get("content", ""),
        "first_published": raw.get("first_published"),
        "updated_at": raw.get("updated_at"),
        "language": raw.get("language"),
        "application_deadline": raw.get("application_deadline"),
        "source_url": application_url,
        "application_url": application_url,
        # Compatibility alias for the pre-multi-provider API contract.
        # Remove once clients migrate to source_url / application_url.
        "absolute_url": application_url,
        "attribution": None,
    }


def get_normalized_jobs() -> list[dict]:
    return [normalize_job(raw) for raw in get_greenhouse_jobs()]