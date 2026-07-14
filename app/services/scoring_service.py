from app.config import REMOTE_KEYWORDS, TARGET_KEYWORDS
from app.profile import TARGET_COMPANIES


def calculate_score(job):
    score = 0
    title = job["title"].lower()
    location = job["location"]["name"].lower()

    for keyword, points in TARGET_KEYWORDS.items():
        if keyword in title:
            score += points

    if any(keyword in location for keyword in REMOTE_KEYWORDS):
        score += 30
    
    if job.get("company_name") in TARGET_COMPANIES: score += 20
    
    return min(score, 100)