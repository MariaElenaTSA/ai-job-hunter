"""Remotive job board client.

Usage restrictions (https://github.com/remotive-io/remote-jobs-api):
- Display "Remotive" as the source and link back to source_url.
- Do not redistribute these jobs to LinkedIn, Google Jobs, or other aggregators.
- Do not gate them behind a signup whose purpose is to collect emails.
- Respect the recommended limit of at most 4 refreshes per day.
- Review Remotive's terms (or their private API) before commercializing or
  scaling this product.
"""

import threading
import time

import requests

from app.services.provider_errors import ProviderFetchError, ProviderResponseError

REMOTIVE_URL = "https://remotive.com/api/remote-jobs"
REMOTIVE_USER_AGENT = "CareerCopilot/1.0 (job-matching research tool)"

# Fields a Remotive listing must have to be usable. Anything missing one of
# these would force us to invent data (an empty title, a guessed URL) to
# satisfy the common job contract -- so such listings are skipped instead.
_REQUIRED_RAW_FIELDS = ("id", "title", "company_name", "url")

# A 6-hour TTL keeps normal interactive use comfortably under Remotive's
# recommended limit of ~4 requests/day.
#
# This is a single-instance, in-memory cache: it is not shared across
# processes/workers and is lost on restart. Acceptable for the current MVP,
# but it will need a real shared cache before running multiple instances.
_CACHE_TTL_SECONDS = 6 * 60 * 60

_cache_lock = threading.Lock()
_cache = {"jobs": None, "fetched_at": None}


def _cache_is_fresh() -> bool:
    return (
        _cache["jobs"] is not None
        and _cache["fetched_at"] is not None
        and (time.monotonic() - _cache["fetched_at"]) < _CACHE_TTL_SECONDS
    )


def _fetch_remotive_jobs() -> list:
    try:
        response = requests.get(REMOTIVE_URL, headers={"User-Agent": REMOTIVE_USER_AGENT}, timeout=10)
        response.raise_for_status()
    except requests.RequestException as error:
        raise ProviderFetchError(f"Remotive request failed: {error}") from error

    payload = response.json()

    if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
        raise ProviderResponseError("Remotive response is missing a 'jobs' list")

    return payload["jobs"]


def get_remotive_jobs() -> list:
    # Fast path: don't take the lock at all when the cache is already fresh.
    if _cache_is_fresh():
        return _cache["jobs"]

    with _cache_lock:
        # Double-check: another thread may have refilled the cache while this
        # one was waiting for the lock.
        if _cache_is_fresh():
            return _cache["jobs"]

        jobs = _fetch_remotive_jobs()

        # Only cache after a successful, validated response -- a failed
        # request must never be remembered as if it had succeeded.
        _cache["jobs"] = jobs
        _cache["fetched_at"] = time.monotonic()
        return jobs


def _reset_cache() -> None:
    """Test-only: clear the shared cache so tests don't leak state into each other."""
    with _cache_lock:
        _cache["jobs"] = None
        _cache["fetched_at"] = None


def _is_usable(raw: dict) -> bool:
    return all(raw.get(field) for field in _REQUIRED_RAW_FIELDS)


def normalize_job(raw: dict) -> dict:
    """Map a raw Remotive job into the common cross-provider job format.

    Remotive is a fully-remote job board, so workplace_type is always
    "remote". Remotive has no "apply" link distinct from its own job page, so
    source_url and application_url both use the same `url` field.

    Any UI that surfaces this job must show `attribution` and link to `source_url`.
    """
    source_job_id = str(raw["id"])
    url = raw["url"]

    return {
        "id": f"remotive:{source_job_id}",
        "source": "remotive",
        "source_job_id": source_job_id,
        "title": raw["title"],
        "company_name": raw["company_name"],
        "location": {"name": raw.get("candidate_required_location") or ""},
        "workplace_type": "remote",
        "content": raw.get("description", ""),
        "first_published": raw.get("publication_date"),
        # Remotive does not distinguish "published" from "last updated" --
        # reusing publication_date here would fabricate a signal that doesn't exist.
        "updated_at": None,
        "language": None,
        "application_deadline": None,
        "source_url": url,
        "application_url": url,
        # Compatibility alias for the pre-multi-provider API contract.
        "absolute_url": url,
        "attribution": "Remotive",
    }


def get_normalized_jobs() -> list:
    raw_jobs = get_remotive_jobs()
    return [normalize_job(raw) for raw in raw_jobs if _is_usable(raw)]
