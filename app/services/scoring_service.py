def calculate_score(job):
    score = 0

    title = job["title"].lower()

    if "solutions" in title:
        score += 30

    if "product" in title:
        score += 25

    if "operations" in title:
        score += 25

    if "support" in title:
        score += 20

    if "remote" in job["location"]["name"].lower():
        score += 30

    return score