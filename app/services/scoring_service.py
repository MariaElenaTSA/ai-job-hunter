from app.config import REMOTE_KEYWORDS, TARGET_KEYWORDS


def calculate_score(job):
    score = 0
    title = job["title"].lower()
    location = job["location"]["name"].lower()

    for keyword, points in TARGET_KEYWORDS.items():
        if keyword in title:
            score += points

    if any(keyword in location for keyword in REMOTE_KEYWORDS):
        score += 30

    return min(score, 100)