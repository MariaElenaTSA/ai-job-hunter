import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CANDIDATE_PROFILE_PATH = PROJECT_ROOT / "data" / "candidates" / "maria_elena_paredes" / "profile.json"


class CandidateProfileError(Exception):
    """Raised when the candidate profile file is missing or invalid."""


def load_candidate_profile(path: Path = CANDIDATE_PROFILE_PATH) -> dict:
    if not path.exists():
        raise CandidateProfileError(f"Candidate profile not found at {path}")

    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise CandidateProfileError(f"Candidate profile at {path} is not valid JSON: {e}") from e


def get_scoring_profile(candidate: dict) -> dict:
    career_preferences = candidate.get("career_preferences", {})

    return {
        "target_roles": career_preferences.get("target_roles", []),
        "preferred_responsibilities": career_preferences.get("preferred_responsibilities", []),
        "skill_names": [skill["name"] for skill in candidate.get("skills", [])],
        "tool_names": [tool["name"] for tool in candidate.get("tools", [])],
        "remote_only": career_preferences.get("remote_only", False),
        "geo_eligibility": career_preferences.get("geo_eligibility", {}),
    }


ROLE_FIELDS = (
    "title",
    "start_date",
    "end_date",
    "summary",
    "core_responsibilities",
    "business_impact",
    "tools_and_methods",
)


def _filter_experience(experience: list) -> list:
    filtered = []

    for entry in experience:
        roles = [
            {field: role[field] for field in ROLE_FIELDS if field in role}
            for role in entry.get("roles", [])
        ]
        filtered.append({
            "company": entry.get("company_group"),
            "roles": roles,
        })

    return filtered


def _public_achievements(achievements: list) -> list:
    return [
        {k: v for k, v in achievement.items() if k not in ("claim_strength", "public_notes")}
        for achievement in achievements
        if achievement.get("claim_strength", {}).get("publicly_defensible") is True
    ]


def _strip_credential_urls(certifications: list) -> list:
    return [
        {k: v for k, v in certification.items() if k != "credential_url"}
        for certification in certifications
    ]


def build_candidate_context(candidate: dict) -> dict:
    return {
        "professional_identity": candidate.get("professional_identity", {}),
        "career_preferences": candidate.get("career_preferences", {}),
        "skills": candidate.get("skills", []),
        "achievements": _public_achievements(candidate.get("achievements", [])),
        "experience": _filter_experience(candidate.get("experience", [])),
        "projects": candidate.get("projects", []),
        "languages": candidate.get("languages", []),
        "education": candidate.get("education", []),
        "certifications": _strip_credential_urls(candidate.get("certifications", [])),
    }
