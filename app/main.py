from fastapi import FastAPI, HTTPException, Query
from app.config import DEFAULT_MAX_AGE_DAYS
from app.profile import MIN_SCORE
from app.services.job_service import AllProvidersFailedError, UnknownSourceError, get_jobs, get_job
from app.services.provider_errors import ProviderError
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
def jobs(
    min_score: int = MIN_SCORE,
    max_age_days: int = Query(default=DEFAULT_MAX_AGE_DAYS, ge=0),
    sources: str | None = Query(default=None),
):
    # Convention: 0 means "no age limit" (job_service treats 0 and None the same way).
    try:
        return get_jobs(min_score, max_age_days, sources)
    except UnknownSourceError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except AllProvidersFailedError as error:
        raise HTTPException(status_code=502, detail=str(error))

@app.get("/jobs/{job_id}")
def read_job(job_id: str):
    try:
        job = get_job(job_id)
    except ProviderError as error:
        raise HTTPException(status_code=502, detail=str(error))

    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return job

@app.get("/jobs/{job_id}/summary")
def read_job_summary(job_id: str):
    # NOTE: GET triggers a paid, uncached call to OpenAI. Fine for a single-user
    # private beta; must become POST (or gain caching) before more users share cost.
    try:
        job = get_job(job_id)
    except ProviderError as error:
        raise HTTPException(status_code=502, detail=str(error))

    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

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