import requests

GREENHOUSE_URL = "https://boards-api.greenhouse.io/v1/boards/stripe/jobs"


def get_greenhouse_jobs():
    response = requests.get(GREENHOUSE_URL, timeout=10)
    response.raise_for_status()
    return response.json()