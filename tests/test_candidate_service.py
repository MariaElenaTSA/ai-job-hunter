from pathlib import Path

import pytest

from app.services.candidate_service import (
    CandidateProfileError,
    get_scoring_profile,
    load_candidate_profile,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def test_load_candidate_profile_returns_dict_with_expected_keys():
    candidate = load_candidate_profile()

    assert "career_preferences" in candidate
    assert "target_companies" in candidate["career_preferences"]


def test_load_candidate_profile_missing_file_raises():
    missing_path = FIXTURES_DIR / "does_not_exist.json"

    with pytest.raises(CandidateProfileError):
        load_candidate_profile(missing_path)


def test_load_candidate_profile_invalid_json_raises():
    invalid_path = FIXTURES_DIR / "invalid_profile.json"

    with pytest.raises(CandidateProfileError):
        load_candidate_profile(invalid_path)


def test_get_scoring_profile_reads_target_companies_from_career_preferences():
    candidate = {"career_preferences": {"target_companies": ["Stripe", "Brex"]}}

    profile = get_scoring_profile(candidate)

    assert profile["target_companies"] == ["Stripe", "Brex"]


def test_get_scoring_profile_handles_missing_career_preferences():
    profile = get_scoring_profile({})

    assert profile["target_companies"] == []
