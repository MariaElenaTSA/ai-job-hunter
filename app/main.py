from fastapi import FastAPI, HTTPException
from app.services.job_service import get_jobs, get_job
from app.services.ai_service import (
    AIServiceConfigError,
    AIServiceIncompleteResponseError,
    AIServiceSchemaError,
    AIServiceUnavailableError,
    summarize_job,
)
from app.services.candidate_service import build_candidate_context, load_candidate_profile

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
    # NOTE: GET triggers a paid, uncached call to OpenAI. Fine for a single-user
    # private beta; must become POST (or gain caching) before more users share cost.
    job = get_job(job_id)

    if job is None:
        return {"error": "Job not found"}

    if not job["has_description"]:
        raise HTTPException(status_code=400, detail="Job has no description to analyze")

    candidate = load_candidate_profile()
    candidate_context = build_candidate_context(candidate)

    try:
        return summarize_job(job, candidate_context)
    except AIServiceConfigError:
        raise HTTPException(status_code=500, detail="AI service is not configured")
    except AIServiceUnavailableError:
        raise HTTPException(status_code=502, detail="AI provider is currently unavailable")
    except (AIServiceIncompleteResponseError, AIServiceSchemaError):
        raise HTTPException(status_code=502, detail="AI provider returned an invalid response")