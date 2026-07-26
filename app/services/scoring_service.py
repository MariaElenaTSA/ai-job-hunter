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

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


def _normalize_description(raw: str) -> str:
    text = html.unescape(raw or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return text.lower()


def _tokenize(text: str) -> list:
    return _TOKEN_PATTERN.findall(text)


def _tokens_contain(tokens: list, subsequence: list) -> bool:
    """True if `subsequence` appears as a contiguous run inside `tokens`."""
    n = len(subsequence)
    if n == 0:
        return False
    return any(tokens[i:i + n] == subsequence for i in range(len(tokens) - n + 1))


def _term_matches(term: str, description_tokens: list) -> bool:
    """Boundary-aware match: `term` must appear as whole token(s), never as a
    substring inside a larger word (e.g. "git" must not match inside "github").
    """
    return _tokens_contain(description_tokens, _tokenize(term))


def _same_evidence(term_a: str, term_b: str) -> bool:
    """True if one term's tokens are a contiguous run inside the other's -- i.e.
    they describe the same underlying phrase (e.g. "root cause" is contained in
    "root cause analysis"), as opposed to terms that only share characters but
    never overlap at the token level (e.g. "git" and "github").
    """
    tokens_a, tokens_b = _tokenize(term_a), _tokenize(term_b)
    if not tokens_a or not tokens_b:
        return False
    return _tokens_contain(tokens_a, tokens_b) or _tokens_contain(tokens_b, tokens_a)


def _build_content_concepts(profile: dict) -> dict:
    """Map each scoring "concept" to the set of terms that count as evidence for it.

    A concept is either a synonym group from CONTENT_KEYWORD_SYNONYMS or a single
    term taken from the candidate's own profile (tools, skills, responsibilities).
    Concepts are not deduplicated here: two concepts whose matched terms turn out
    to be the same underlying evidence (e.g. a profile skill name that contains a
    synonym-group term) are merged later, in `_deduplicate_matched_concepts`, based
    on what actually matched in this job's description.
    """
    concepts = {key: {term.lower() for term in terms} for key, terms in CONTENT_KEYWORD_SYNONYMS.items()}

    profile_terms = (
        profile.get("tool_names", [])
        + profile.get("skill_names", [])
        + profile.get("preferred_responsibilities", [])
    )

    for term in profile_terms:
        normalized = term.lower().strip()
        if normalized:
            concepts.setdefault(f"profile:{normalized}", set()).add(normalized)

    return concepts


def _match_concepts(concepts: dict, description_tokens: list) -> dict:
    """Return only the concepts with at least one matching term, mapped to the
    terms that actually matched."""
    matched = {}
    for name, terms in concepts.items():
        hits = [term for term in terms if _term_matches(term, description_tokens)]
        if hits:
            matched[name] = hits
    return matched


def _deduplicate_matched_concepts(matched: dict) -> list:
    """Merge matched concepts that represent the same underlying evidence.

    Two matched concepts are merged when any of their matched terms overlap at
    the token level (e.g. "cross-functional" and "cross-functional collaboration"
    matching the same phrase), so that phrase is not counted twice. Concepts whose
    terms only share characters but not whole tokens (e.g. "git" and "github") are
    never merged -- boundary-aware matching already keeps them from firing off the
    same word in the first place.
    """
    names = list(matched.keys())
    parent = {name: name for name in names}

    def find(name):
        while parent[name] != name:
            parent[name] = parent[parent[name]]
            name = parent[name]
        return name

    def union(name_a, name_b):
        root_a, root_b = find(name_a), find(name_b)
        if root_a != root_b:
            parent[root_a] = root_b

    for i, name_a in enumerate(names):
        for name_b in names[i + 1:]:
            if any(_same_evidence(term_a, term_b) for term_a in matched[name_a] for term_b in matched[name_b]):
                union(name_a, name_b)

    groups = {}
    for name in names:
        groups.setdefault(find(name), []).append(name)

    deduplicated = []
    for members in groups.values():
        representative = sorted(members, key=lambda name: (name.startswith("profile:"), name))[0]
        matched_terms = [term for member in members for term in matched[member]]
        matched_term = max(matched_terms, key=len)
        deduplicated.append({"concept": representative, "matched_term": matched_term})

    return deduplicated


def _score_breakdown(job: dict, profile: dict = None) -> dict:
    if profile is None:
        profile = get_scoring_profile(load_candidate_profile())

    title = job["title"].lower()
    description_tokens = _tokenize(_normalize_description(job.get("content", "")))

    concepts = _build_content_concepts(profile)
    matched = _match_concepts(concepts, description_tokens)
    matched_concepts = _deduplicate_matched_concepts(matched)

    content_score = min(len(matched_concepts) * CONTENT_KEYWORD_POINTS, MAX_CONTENT_SCORE)

    title_tokens = _tokenize(title)
    title_terms = {role.lower() for role in profile.get("target_roles", [])} | set(TITLE_KEYWORD_SYNONYMS)
    title_match = next((term for term in title_terms if _term_matches(term, title_tokens)), None)
    title_score = TITLE_MATCH_SCORE if title_match else 0

    final_score = min(content_score + title_score, 100)

    return {
        "matched_concepts": [
            {"concept": entry["concept"], "matched_term": entry["matched_term"], "points": CONTENT_KEYWORD_POINTS}
            for entry in matched_concepts
        ],
        "content_score": content_score,
        "title_match": title_match,
        "title_score": title_score,
        "final_score": final_score,
    }


def calculate_score(job: dict, profile: dict = None) -> int:
    return _score_breakdown(job, profile)["final_score"]


def calculate_remote_eligibility(job: dict, profile: dict = None) -> str:
    location = job["location"]["name"].lower()
    description = _normalize_description(job.get("content", ""))

    remote_signal = (
        job.get("workplace_type") == "remote"
        or any(keyword in location for keyword in REMOTE_LOCATION_KEYWORDS)
        or any(phrase in description for phrase in REMOTE_DESCRIPTION_PHRASES)
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
