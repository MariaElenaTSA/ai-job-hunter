from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import main
from app.services.ai_service import AIServiceConfigError

client = TestClient(main.app)

FAKE_JOB_NO_DESCRIPTION = {
    "id": "greenhouse:1",
    "title": "Solutions Engineer",
    "has_description": False,
}

FAKE_JOB_WITH_DESCRIPTION = {
    "id": "greenhouse:1",
    "title": "Solutions Engineer",
    "has_description": True,
    "description": "Some real description.",
}


def test_read_job_summary_missing_description_returns_400():
    with patch.object(main, "get_job", return_value=FAKE_JOB_NO_DESCRIPTION):
        with pytest.raises(HTTPException) as exc_info:
            main.read_job_summary("greenhouse:1")

    assert exc_info.value.status_code == 400


def test_read_job_summary_ai_config_error_returns_500():
    def raise_config_error(*args, **kwargs):
        raise AIServiceConfigError("OPENAI_API_KEY is not set")

    with patch.object(main, "get_job", return_value=FAKE_JOB_WITH_DESCRIPTION), \
         patch.object(main, "load_candidate_profile", return_value={}), \
         patch.object(main, "summarize_job", side_effect=raise_config_error):
        with pytest.raises(HTTPException) as exc_info:
            main.read_job_summary("greenhouse:1")

    assert exc_info.value.status_code == 500


def test_read_job_endpoint_accepts_composite_id():
    fake_job = {"id": "greenhouse:1", "title": "Solutions Engineer"}

    with patch.object(main, "get_job", return_value=fake_job) as mock_get_job:
        response = client.get("/jobs/greenhouse:1")

    assert response.status_code == 200
    assert response.json() == fake_job
    mock_get_job.assert_called_once_with("greenhouse:1")


def test_read_job_endpoint_unknown_job_returns_404():
    with patch.object(main, "get_job", return_value=None):
        response = client.get("/jobs/unknownsource:1")

    assert response.status_code == 404


def test_read_job_summary_endpoint_reaches_mocked_service():
    fake_summary = {
        "job_id": "greenhouse:1",
        "title": "Solutions Engineer",
        "summary": "Great fit.",
        "required_skills": [],
        "why_it_matches": [],
        "potential_gaps": [],
    }

    with patch.object(main, "get_job", return_value=FAKE_JOB_WITH_DESCRIPTION), \
         patch.object(main, "load_candidate_profile", return_value={}), \
         patch.object(main, "summarize_job", return_value=fake_summary) as mock_summarize:
        response = client.get("/jobs/greenhouse:1/summary")

    assert response.status_code == 200
    assert response.json() == fake_summary
    mock_summarize.assert_called_once()


def test_jobs_endpoint_uses_default_max_age_of_14_days():
    with patch.object(main, "get_jobs") as mock_get_jobs:
        mock_get_jobs.return_value = []
        client.get("/jobs")

    mock_get_jobs.assert_called_once_with(70, 14)


def test_jobs_endpoint_max_age_days_zero_means_no_limit():
    with patch.object(main, "get_jobs") as mock_get_jobs:
        mock_get_jobs.return_value = []
        client.get("/jobs?max_age_days=0")

    mock_get_jobs.assert_called_once_with(70, 0)


def test_jobs_endpoint_negative_max_age_days_returns_422():
    response = client.get("/jobs?max_age_days=-1")

    assert response.status_code == 422
