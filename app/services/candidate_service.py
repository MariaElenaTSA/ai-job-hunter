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
        "target_companies": career_preferences.get("target_companies", []),
    }
