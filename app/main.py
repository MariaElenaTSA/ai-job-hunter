from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from app.config import DEFAULT_MAX_AGE_DAYS
from app.profile import MIN_SCORE
from app.services import batch_import_service, manual_import_service
from app.services.job_service import (
    AllProvidersFailedError,
    UnknownSourceError,
    format_job,
    get_jobs,
    get_job,
)
from app.services.provider_errors import ProviderError
from app.services.ai_service import (
    AIServiceConfigError,
    AIServiceIncompleteResponseError,
    AIServiceSchemaError,
    AIServiceUnavailableError,
    summarize_job,
)
from app.services.candidate_service import build_candidate_context, get_scoring_profile, load_candidate_profile

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

@app.post("/jobs/import")
def import_job(payload: manual_import_service.ManualJobImport):
    # Registered before the dynamic "/jobs/{job_id}" GET route as a defensive
    # convention. Methods differ (POST vs. GET) so there is no real routing
    # collision, but static routes are kept ahead of dynamic ones on principle.
    job = manual_import_service.build_normalized_job(payload)
    profile = get_scoring_profile(load_candidate_profile())
    return format_job(job, profile)

@app.post("/jobs/import/batch")
async def import_jobs_batch(file: UploadFile = File(...)):
    # No summarize_job here: batch import is scoring-only by design, so
    # importing 50 rows never triggers 50 paid OpenAI calls. The user
    # requests summaries individually afterwards via GET /jobs/{id}/summary.
    raw_bytes = await file.read()
    profile = get_scoring_profile(load_candidate_profile())

    try:
        return batch_import_service.import_batch(file.filename, raw_bytes, profile)
    except batch_import_service.BatchFileError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message)
    except batch_import_service.BatchRowErrors as error:
        raise HTTPException(
            status_code=422,
            detail={"message": "One or more rows are invalid", "errors": error.errors},
        )

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