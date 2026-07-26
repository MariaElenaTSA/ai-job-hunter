from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app import main
from app.services.ai_service import AIServiceConfigError

FAKE_JOB_NO_DESCRIPTION = {
    "id": 1,
    "title": "Solutions Engineer",
    "has_description": False,
}

FAKE_JOB_WITH_DESCRIPTION = {
    "id": 1,
    "title": "Solutions Engineer",
    "has_description": True,
    "description": "Some real description.",
}


def test_read_job_summary_missing_description_returns_400():
    with patch.object(main, "get_job", return_value=FAKE_JOB_NO_DESCRIPTION):
        with pytest.raises(HTTPException) as exc_info:
            main.read_job_summary(1)

    assert exc_info.value.status_code == 400


def test_read_job_summary_ai_config_error_returns_500():
    def raise_config_error(*args, **kwargs):
        raise AIServiceConfigError("OPENAI_API_KEY is not set")

    with patch.object(main, "get_job", return_value=FAKE_JOB_WITH_DESCRIPTION), \
         patch.object(main, "load_candidate_profile", return_value={}), \
         patch.object(main, "summarize_job", side_effect=raise_config_error):
        with pytest.raises(HTTPException) as exc_info:
            main.read_job_summary(1)

    assert exc_info.value.status_code == 500
