from pathlib import Path

import pytest

from app.services.candidate_service import (
    CandidateProfileError,
    build_candidate_context,
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


FAKE_CANDIDATE = {
    "identity": {
        "full_name": "Jane Doe",
        "email": "jane@example.com",
    },
    "professional_identity": {"mission": "Reduce technical uncertainty."},
    "career_preferences": {"target_roles": ["Solutions Engineer"]},
    "skills": [{"name": "SQL"}],
    "achievements": [
        {
            "title": "Public achievement",
            "claim_strength": {"publicly_defensible": True},
            "public_notes": ["internal note"],
        },
        {
            "title": "Private achievement",
            "claim_strength": {"publicly_defensible": False},
        },
    ],
    "experience": [
        {
            "company_group": "PayJoy",
            "employer_history": [{"legal_entity": "Adelantos Peru S.A.C."}],
            "roles": [
                {
                    "title": "Technical Support Partner",
                    "start_date": "2024-10",
                    "end_date": "2026-07",
                    "summary": "Investigated incidents.",
                    "core_responsibilities": ["Investigated bugs."],
                    "business_impact": ["Reduced uncertainty."],
                    "tools_and_methods": ["SQL"],
                    "legal_employer": "PayJoy Peru S.A.C.",
                }
            ],
        }
    ],
    "projects": [{"title": "Career Copilot"}],
    "languages": [{"language": "Spanish", "proficiency": "Native"}],
    "education": [{"institution": "USMP"}],
    "certifications": [
        {"name": "AI Agent Building", "credential_url": "https://example.com/secret"}
    ],
    "professional_stories": [{"title": "Should not appear"}],
    "interview_examples": ["Should not appear"],
}


def test_build_candidate_context_excludes_identity_and_employer_history():
    context = build_candidate_context(FAKE_CANDIDATE)

    assert "identity" not in context
    assert "professional_stories" not in context
    assert "interview_examples" not in context
    assert "employer_history" not in context["experience"][0]
    assert "legal_employer" not in context["experience"][0]["roles"][0]


def test_build_candidate_context_includes_languages_and_education():
    context = build_candidate_context(FAKE_CANDIDATE)

    assert context["languages"] == [{"language": "Spanish", "proficiency": "Native"}]
    assert context["education"] == [{"institution": "USMP"}]


def test_build_candidate_context_certifications_exclude_credential_url():
    context = build_candidate_context(FAKE_CANDIDATE)

    assert context["certifications"] == [{"name": "AI Agent Building"}]


def test_build_candidate_context_filters_non_public_achievements():
    context = build_candidate_context(FAKE_CANDIDATE)

    assert len(context["achievements"]) == 1
    assert context["achievements"][0]["title"] == "Public achievement"
    assert "claim_strength" not in context["achievements"][0]
    assert "public_notes" not in context["achievements"][0]
