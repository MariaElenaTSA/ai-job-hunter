import html
import re

import requests

from app.services.provider_errors import ProviderFetchError, ProviderResponseError

REMOTEOK_URL = "https://remoteok.com/api"
REMOTEOK_USER_AGENT = "CareerCopilot/1.0 (job-matching research tool)"

# Fields a Remote OK listing must have to be usable. Anything missing one of
# these would force us to invent data (an empty title, a guessed URL) to
# satisfy the common job contract -- so such listings are skipped instead.
_REQUIRED_RAW_FIELDS = ("id", "position", "company", "url")

# A conservative check for feed entries where "position" is actually a URL,
# not a job title (a known Remote OK data-quality issue). Matches an explicit
# scheme ("http://", "https://"), or "http"/"https" followed by a domain-like
# token (letters/digits/hyphens, a dot, more letters/digits/hyphens) -- e.g.
# "https phase.community job_role...". Deliberately does NOT match on the bare
# word "http"/"https" alone, so legitimate titles like "HTTP Security Engineer"
# or "HTTPS Integration Specialist" are never filtered out.
_URL_LIKE_TITLE_PATTERN = re.compile(r"^https?://|^https?\s+[\w-]+\.[\w-]+", re.IGNORECASE)


def _looks_like_url(title: str) -> bool:
    return bool(_URL_LIKE_TITLE_PATTERN.match(title.strip()))


def get_remoteok_jobs() -> list:
    try:
        response = requests.get(REMOTEOK_URL, headers={"User-Agent": REMOTEOK_USER_AGENT}, timeout=10)
        response.raise_for_status()
    except requests.RequestException as error:
        raise ProviderFetchError(f"Remote OK request failed: {error}") from error

    payload = response.json()

    if not isinstance(payload, list):
        raise ProviderResponseError("Remote OK response is not a list")

    # The first element of the feed is a legal/metadata notice, not a job --
    # it has no "id". Filtering on that trait (rather than dropping index 0)
    # tolerates the metadata object moving or being removed entirely.
    return [item for item in payload if isinstance(item, dict) and "id" in item]


def _is_usable(raw: dict) -> bool:
    if not all(raw.get(field) for field in _REQUIRED_RAW_FIELDS):
        return False

    return not _looks_like_url(raw["position"])


def normalize_job(raw: dict) -> dict:
    """Map a raw Remote OK job into the common cross-provider job format.

    Remote OK is a remote-only board, so workplace_type is always "remote" --
    scoring_service still checks the description for an explicit on-site
    requirement and resolves the conflict to "ambiguous" rather than trusting
    this label blindly.

    Note: `raw` fields are HTML-unescaped (e.g. "Growth &amp; Marketing" ->
    "Growth & Marketing"), but genuine mojibake from the upstream feed (e.g.
    "SulAmÃ©rica") is left as-is -- there is no reliable way to repair a
    mis-decoded string without risking corruption of correctly-encoded text.
    """
    source_job_id = str(raw["id"])
    source_url = raw["url"]
    application_url = raw.get("apply_url") or source_url

    return {
        "id": f"remoteok:{source_job_id}",
        "source": "remoteok",
        "source_job_id": source_job_id,
        "title": html.unescape(raw["position"]),
        "company_name": html.unescape(raw["company"]),
        "location": {"name": raw.get("location") or ""},
        "workplace_type": "remote",
        "content": raw.get("description", ""),
        "first_published": raw.get("date"),
        # Remote OK does not distinguish "published" from "last updated" --
        # reusing `date` here would fabricate a distinct signal that doesn't exist.
        "updated_at": None,
        "language": None,
        "application_deadline": None,
        "source_url": source_url,
        "application_url": application_url,
        # Compatibility alias for the pre-multi-provider API contract.
        "absolute_url": application_url,
        "attribution": "Remote OK",
    }


def get_normalized_jobs() -> list:
    raw_jobs = get_remoteok_jobs()
    return [normalize_job(raw) for raw in raw_jobs if _is_usable(raw)]
