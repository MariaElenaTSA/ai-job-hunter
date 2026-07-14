from fastapi import FastAPI
from app.services.job_service import get_jobs

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
def jobs():
    return get_jobs()