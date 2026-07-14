from app.services.greenhouse_client import get_greenhouse_jobs

def get_jobs():
    data = get_greenhouse_jobs()
    return data["jobs"][:10]