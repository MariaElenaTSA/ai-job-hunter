import html
import re

from app.config import (
    CONTENT_KEYWORD_POINTS,
    CONTENT_KEYWORD_SYNONYMS,
    GEO_AMBIGUOUS_SCOPE_WORDS,
    GEO_ELIGIBLE_DESCRIPTION_PHRASES,
    GEO_US_ONLY_PHRASES,
    MAX_CONTENT_SCORE,
    ONSITE_DESCRIPTION_PHRASES,
    ONSITE_LOCATION_KEYWORDS,
    REMOTE_DESCRIPTION_PHRASES,
    REMOTE_LOCATION_KEYWORDS,
    TITLE_KEYWORD_SYNONYMS,
    TITLE_MATCH_SCORE,
)
from app.services.candidate_service import get_scoring_profile, load_candidate_profile


def _normalize_description(raw: str) -> str:
    text = html.unescape(raw or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return text.lower()


def _build_content_concepts(profile: dict) -> dict:
    """Map each scoring "concept" to the set of terms that count as evidence for it.

    A concept is either a synonym group from CONTENT_KEYWORD_SYNONYMS or a single
    term taken from the candidate's own profile (tools, skills, responsibilities).
    If a profile term is already covered by a synonym group (e.g. tool "SQL" vs
    the "data_analysis" group's "sql"), it is merged into that group instead of
    creating a second concept -- otherwise the same evidence in the description
    would be counted twice.
    """
    concepts = {key: {term.lower() for term in terms} for key, terms in CONTENT_KEYWORD_SYNONYMS.items()}
    already_covered = {term for terms in concepts.values() for term in terms}

    profile_terms = (
        profile.get("tool_names", [])
        + profile.get("skill_names", [])
        + profile.get("preferred_responsibilities", [])
    )

    for term in profile_terms:
        normalized = term.lower().strip()

        if normalized and normalized not in already_covered:
            concepts[f"profile:{normalized}"] = {normalized}
            already_covered.add(normalized)

    return concepts


def calculate_score(job: dict, profile: dict = None) -> int:
    if profile is None:
        profile = get_scoring_profile(load_candidate_profile())

    title = job["title"].lower()
    description = _normalize_description(job.get("content", ""))

    concepts = _build_content_concepts(profile)
    matched_concepts = sum(
        1 for terms in concepts.values() if any(term in description for term in terms)
    )
    content_score = min(matched_concepts * CONTENT_KEYWORD_POINTS, MAX_CONTENT_SCORE)

    title_terms = {role.lower() for role in profile.get("target_roles", [])} | set(TITLE_KEYWORD_SYNONYMS)
    title_score = TITLE_MATCH_SCORE if any(term in title for term in title_terms) else 0

    return min(content_score + title_score, 100)


def calculate_remote_eligibility(job: dict, profile: dict = None) -> str:
    location = job["location"]["name"].lower()
    description = _normalize_description(job.get("content", ""))

    remote_signal = any(keyword in location for keyword in REMOTE_LOCATION_KEYWORDS) or any(
        phrase in description for phrase in REMOTE_DESCRIPTION_PHRASES
    )
    onsite_signal = any(keyword in location for keyword in ONSITE_LOCATION_KEYWORDS) or any(
        phrase in description for phrase in ONSITE_DESCRIPTION_PHRASES
    )

    if remote_signal and onsite_signal:
        return "ambiguous"

    if remote_signal:
        return "eligible"

    if onsite_signal:
        return "not_eligible"

    return "ambiguous"


def calculate_geo_eligibility(job: dict, profile: dict = None) -> str:
    if profile is None:
        profile = get_scoring_profile(load_candidate_profile())

    location = job["location"]["name"].lower()
    description = _normalize_description(job.get("content", ""))
    location_segments = [segment.strip() for segment in location.split(",") if segment.strip()]
    acceptable_scopes = [
        scope.lower() for scope in profile.get("geo_eligibility", {}).get("acceptable_scopes", [])
    ]

    location_has_acceptable_scope = any(
        scope in segment for segment in location_segments for scope in acceptable_scopes
    )
    location_is_us_restricted = any("remote" in segment for segment in location_segments) and all(
        segment.startswith("us-") or segment.startswith("us ") or segment == "us"
        for segment in location_segments
    )
    location_has_us_only_phrase = any(phrase in location for phrase in GEO_US_ONLY_PHRASES)
    description_has_eligible_phrase = any(phrase in description for phrase in GEO_ELIGIBLE_DESCRIPTION_PHRASES)
    description_has_us_only_phrase = any(phrase in description for phrase in GEO_US_ONLY_PHRASES)
    mentions_ambiguous_scope = any(
        word in location or word in description for word in GEO_AMBIGUOUS_SCOPE_WORDS
    )

    eligible_signal = location_has_acceptable_scope or description_has_eligible_phrase
    not_eligible_signal = (
        location_is_us_restricted or location_has_us_only_phrase or description_has_us_only_phrase
    )

    if eligible_signal and not_eligible_signal:
        return "ambiguous"

    if eligible_signal:
        return "eligible"

    if not_eligible_signal:
        return "not_eligible"

    if mentions_ambiguous_scope:
        return "ambiguous"

    return "ambiguous"
