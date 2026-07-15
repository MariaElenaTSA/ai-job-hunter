from fastapi import FastAPI
from app.services.job_service import get_jobs, get_job
from app.services.ai_service import summarize_job

app = FastAPI(
    title="AI Job Hunter",
    version="0.1.0"
)

@app.get("/")
def home():
    return {"message": "AI Job Hunter API is running!"}

@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "AI Job Hunter",
        "version": "0.1.0"
    }

@app.get("/jobs")
def jobs(min_score: int = 70):
    return get_jobs(min_score)

@app.get("/jobs/{job_id}")
def read_job(job_id: int):
    job = get_job(job_id)

    if job is None:
        return {"error": "Job not found"}

    return job

@app.get("/jobs/{job_id}/summary")
def read_job_summary(job_id: int):
    job = get_job(job_id)

    if job is None:
        return {"error": "Job not found"}

    return summarize_job(job)