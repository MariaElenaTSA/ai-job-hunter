from types import SimpleNamespace
from unittest.mock import MagicMock

import openai
import pytest

from app.services.ai_service import (
    AIServiceConfigError,
    AIServiceIncompleteResponseError,
    AIServiceSchemaError,
    AIServiceUnavailableError,
    JobAnalysis,
    summarize_job,
)

FAKE_JOB = {
    "id": 123,
    "title": "Solutions Engineer",
    "company_name": "Stripe",
    "location": "US-Remote, US-San Francisco, US-Chicago, US-New York, US-Seattle, US-Texas",
    "description": "Help customers integrate our API.",
}

FAKE_CANDIDATE_CONTEXT = {"skills": [{"name": "SQL"}]}


def _fake_client(response):
    client = MagicMock()
    client.responses.parse.return_value = response
    return lambda: client


def test_summarize_job_missing_api_key_raises_config_error():
    def raising_factory():
        raise AIServiceConfigError("OPENAI_API_KEY is not set")

    with pytest.raises(AIServiceConfigError):
        summarize_job(FAKE_JOB, FAKE_CANDIDATE_CONTEXT, client_factory=raising_factory)


def test_summarize_job_returns_expected_shape_on_success():
    analysis = JobAnalysis(
        summary="Strong match.",
        required_skills=["SQL", "APIs"],
        why_it_matches=["Has SQL experience."],
        potential_gaps=["No formal SE title yet."],
    )
    response = SimpleNamespace(status="completed", output_parsed=analysis)

    result = summarize_job(FAKE_JOB, FAKE_CANDIDATE_CONTEXT, client_factory=_fake_client(response))

    assert result["job_id"] == 123
    assert result["title"] == "Solutions Engineer"
    assert result["summary"] == "Strong match."
    assert result["required_skills"] == ["SQL", "APIs"]
    assert result["why_it_matches"] == ["Has SQL experience."]
    assert result["potential_gaps"] == ["No formal SE title yet."]


def test_summarize_job_sends_title_company_and_location_as_metadata():
    analysis = JobAnalysis(
        summary="Strong match.",
        required_skills=["SQL", "APIs"],
        why_it_matches=["Has SQL experience."],
        potential_gaps=["No formal SE title yet."],
    )
    response = SimpleNamespace(status="completed", output_parsed=analysis)
    client = MagicMock()
    client.responses.parse.return_value = response

    summarize_job(FAKE_JOB, FAKE_CANDIDATE_CONTEXT, client_factory=lambda: client)

    _, kwargs = client.responses.parse.call_args
    user_message = next(m["content"] for m in kwargs["input"] if m["role"] == "user")

    assert '"title": "Solutions Engineer"' in user_message
    assert '"company_name": "Stripe"' in user_message
    assert FAKE_JOB["location"] in user_message


def test_summarize_job_wraps_api_error_as_unavailable():
    client = MagicMock()
    client.responses.parse.side_effect = openai.APIConnectionError(request=MagicMock())

    with pytest.raises(AIServiceUnavailableError):
        summarize_job(FAKE_JOB, FAKE_CANDIDATE_CONTEXT, client_factory=lambda: client)


def test_summarize_job_incomplete_status_raises_incomplete_error():
    response = SimpleNamespace(status="incomplete", output_parsed=None)

    with pytest.raises(AIServiceIncompleteResponseError):
        summarize_job(FAKE_JOB, FAKE_CANDIDATE_CONTEXT, client_factory=_fake_client(response))


def test_summarize_job_missing_output_parsed_raises_schema_error():
    response = SimpleNamespace(status="completed", output_parsed=None)

    with pytest.raises(AIServiceSchemaError):
        summarize_job(FAKE_JOB, FAKE_CANDIDATE_CONTEXT, client_factory=_fake_client(response))
