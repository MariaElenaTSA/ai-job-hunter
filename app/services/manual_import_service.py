"""Manual job import: turn a pasted job posting (e.g. from LinkedIn) into the
common cross-provider job format, without scraping, fetching, or logging into
anything.

URL handling: pydantic's HttpUrl may canonicalize the given URL (for example,
normalizing the host's case or adding a trailing slash to a bare domain) --
the exact string is not guaranteed to be preserved byte-for-byte. We convert
once with `str(payload.url)` and reuse that *same* normalized string for the
SHA-256 id, source_url, application_url, absolute_url, and storage, so the id
and the URLs returned to the caller are always consistent with each other.
Query parameters are preserved, but two URLs that point at the same posting
with different tracking parameters (e.g. "?refId=...") will still produce
different ids until general deduplication is implemented -- out of scope here.

Storage: an in-memory dict, guarded by a lock for concurrent access. This is
a single-instance, MVP-only mechanism: it is lost on every Uvicorn restart,
is never shared across multiple worker processes, and has no permanent
persistence. Acceptable for a single-user private beta; revisit before
multiple users or multiple workers are involved.
"""

import copy
import hashlib
import threading

from pydantic import BaseModel, Field, HttpUrl, field_validator

MAX_TITLE_LENGTH = 300
MAX_COMPANY_NAME_LENGTH = 300
MAX_LOCATION_LENGTH = 500
MAX_DESCRIPTION_LENGTH = 100_000


class ManualJobImport(BaseModel):
    url: HttpUrl
    title: str
    # validate_default=True: without it, pydantic skips the field validator
    # entirely when the field is omitted, so an omitted `location` would stay
    # None instead of being normalized to "" like an explicitly blank one.
    company_name: str | None = Field(default=None, validate_default=True)
    location: str | None = Field(default=None, validate_default=True)
    description: str

    @field_validator("title")
    @classmethod
    def _validate_title(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("title must not be blank")
        if len(value) > MAX_TITLE_LENGTH:
            raise ValueError(f"title must be at most {MAX_TITLE_LENGTH} characters")
        return value

    @field_validator("description")
    @classmethod
    def _validate_description(cls, value: str) -> str:
        # strip() is only used here to check for blankness -- the original
        # value (HTML or plain text, with its original whitespace) is what
        # gets returned and eventually stored, never the stripped version.
        if not value.strip():
            raise ValueError("description must not be blank")
        if len(value) > MAX_DESCRIPTION_LENGTH:
            raise ValueError(f"description must be at most {MAX_DESCRIPTION_LENGTH} characters")
        return value

    @field_validator("company_name")
    @classmethod
    def _validate_company_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if len(value) > MAX_COMPANY_NAME_LENGTH:
            raise ValueError(f"company_name must be at most {MAX_COMPANY_NAME_LENGTH} characters")
        return value.strip() or None

    @field_validator("location")
    @classmethod
    def _validate_location(cls, value: str | None) -> str:
        if value is None:
            return ""
        if len(value) > MAX_LOCATION_LENGTH:
            raise ValueError(f"location must be at most {MAX_LOCATION_LENGTH} characters")
        return value.strip()


_imports_lock = threading.Lock()
_imports: dict[str, dict] = {}


def _generate_source_job_id(normalized_url: str) -> str:
    """Deterministic id derived from the URL. Uses SHA-256 (not Python's
    built-in hash()) because hash() is randomized per-process via
    PYTHONHASHSEED and would produce a different id every restart."""
    return hashlib.sha256(normalized_url.encode("utf-8")).hexdigest()[:16]


def normalize_job(payload: ManualJobImport) -> dict:
    """Map a manually-pasted job posting into the common cross-provider job format.

    workplace_type is left as None, same as Greenhouse -- scoring_service still
    derives remote/geo eligibility from location and content directly.
    """
    normalized_url = str(payload.url)
    source_job_id = _generate_source_job_id(normalized_url)

    return {
        "id": f"manual_import:{source_job_id}",
        "source": "manual_import",
        "source_job_id": source_job_id,
        "title": payload.title,
        "company_name": payload.company_name,
        "location": {"name": payload.location or ""},
        "workplace_type": None,
        "content": payload.description,
        "first_published": None,
        "updated_at": None,
        "language": None,
        "application_deadline": None,
        "source_url": normalized_url,
        "application_url": normalized_url,
        "absolute_url": normalized_url,
        "attribution": "Manual import",
    }


def _store_job(job: dict) -> None:
    # Lock is held only for the dict write itself -- never across scoring or
    # AI analysis, which happen elsewhere, well after this returns.
    with _imports_lock:
        _imports[job["source_job_id"]] = job


def get_stored_job(source_job_id: str) -> dict | None:
    # Lock is held only long enough to read the reference out of the dict.
    with _imports_lock:
        job = _imports.get(source_job_id)

    if job is None:
        return None

    # Never hand back the stored dict itself -- a caller mutating the
    # returned job (or its nested "location" dict) must not corrupt storage.
    return copy.deepcopy(job)


def _reset_imports() -> None:
    """Test-only: clear the store so tests don't leak state into each other."""
    with _imports_lock:
        _imports.clear()


def build_normalized_job(payload: ManualJobImport) -> dict:
    """Normalize the payload and store it under its deterministic id.

    Re-importing the same URL replaces the previous entry for that id rather
    than accumulating duplicates.
    """
    job = normalize_job(payload)
    _store_job(job)
    return job
