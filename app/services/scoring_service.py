from app.config import REMOTE_KEYWORDS, TARGET_KEYWORDS
from app.services.candidate_service import get_scoring_profile, load_candidate_profile


def calculate_score(job, profile=None):
    if profile is None:
        profile = get_scoring_profile(load_candidate_profile())

    score = 0
    title = job["title"].lower()
    location = job["location"]["name"].lower()

    for keyword, points in TARGET_KEYWORDS.items():
        if keyword in title:
            score += points

    if any(keyword in location for keyword in REMOTE_KEYWORDS):
        score += 30

    target_companies = profile.get("target_companies", [])

    if job.get("company_name") in target_companies:
        score += 20

    return min(score, 100)