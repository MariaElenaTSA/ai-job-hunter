import csv
import io
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app import main
from app.config import MAX_BATCH_FILE_SIZE_BYTES, MAX_BATCH_ROWS
from app.services import manual_import_service
from app.services.manual_import_service import _generate_source_job_id

client = TestClient(main.app)


@pytest.fixture(autouse=True)
def _reset_manual_imports():
    manual_import_service._reset_imports()
    yield
    manual_import_service._reset_imports()


def _csv_bytes(rows, header=("title", "company_name", "location", "url", "description"), encoding="utf-8"):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    writer.writerows(rows)
    text = buffer.getvalue()
    return text.encode(encoding)


def _upload(content_bytes, filename="jobs.csv", content_type="text/csv"):
    return client.post("/jobs/import/batch", files={"file": (filename, content_bytes, content_type)})


# Real scoring (via the actual candidate profile, no mocking -- consistent
# with how POST /jobs/import is tested elsewhere in this suite):
#   HIGH_SCORE_ROW -> score 52, remote_eligibility=eligible, geo_eligibility=eligible
#   LOW_SCORE_NOT_ELIGIBLE_ROW -> score 0, remote_eligibility=eligible, geo_eligibility=not_eligible
HIGH_SCORE_ROW = [
    "Technical Account Manager",
    "Acme Inc",
    "Remote - Worldwide",
    "https://www.linkedin.com/jobs/view/1000000001",
    "SQL troubleshooting and root cause analysis using Zendesk and REST APIs, fully remote-first team.",
]

LOW_SCORE_NOT_ELIGIBLE_ROW = [
    "Marketing Intern",
    "Other Co",
    "Remote - US Only",
    "https://www.linkedin.com/jobs/view/1000000002",
    "General marketing tasks and social media scheduling.",
]


# --- Happy path: CSV parsing, header handling ---

def test_batch_import_valid_csv_multiple_rows_returns_all_imported():
    content = _csv_bytes([HIGH_SCORE_ROW, LOW_SCORE_NOT_ELIGIBLE_ROW])

    response = _upload(content)

    assert response.status_code == 200
    body = response.json()
    assert body["imported_count"] == 2
    assert len(body["jobs"]) == 2


def test_batch_import_accepts_csv_extension_regardless_of_content_type():
    # Chrome/Excel/Sheets send inconsistent Content-Types for CSV -- only the
    # .csv extension plus real content parsing are trusted, never the MIME type.
    content = _csv_bytes([HIGH_SCORE_ROW])

    response = _upload(content, content_type="application/octet-stream")

    assert response.status_code == 200


def test_batch_import_rejects_non_csv_extension():
    content = _csv_bytes([HIGH_SCORE_ROW])

    response = _upload(content, filename="jobs.xlsx", content_type="text/csv")

    assert response.status_code == 415


def test_batch_import_header_is_normalized_case_and_whitespace_insensitive():
    text = " Title , Company_Name , Location , URL , Description \n" + ",".join(
        f'"{cell}"' for cell in HIGH_SCORE_ROW
    ) + "\n"

    response = _upload(text.encode())

    assert response.status_code == 200
    assert response.json()["imported_count"] == 1


def test_batch_import_duplicate_header_columns_returns_422():
    content = "title,title,url,description\nA,B,https://example.com/1,some description\n".encode()

    response = _upload(content)

    assert response.status_code == 422


# --- BOM, quoting, embedded commas/newlines ---

def test_batch_import_handles_bom_commas_quotes_and_embedded_newlines():
    tricky_description = 'Line one, with a comma.\nLine two, with "quoted" text.'
    row = [
        "Technical Account Manager",
        "Acme, Inc.",
        "Remote - Worldwide",
        "https://www.linkedin.com/jobs/view/1000000003",
        tricky_description,
    ]
    content = _csv_bytes([row], encoding="utf-8-sig")

    response = _upload(content)

    assert response.status_code == 200
    body = response.json()
    assert body["jobs"][0]["description"] == tricky_description
    assert body["jobs"][0]["company_name"] == "Acme, Inc."


def test_batch_import_invalid_utf8_returns_422():
    content = b"title,company_name,location,url,description\n\xff\xfe garbage,,,,\n"

    response = _upload(content)

    assert response.status_code == 422


def test_batch_import_malformed_csv_returns_422():
    content = (
        'title,company_name,location,url,description\n'
        '"abc"def,Acme,Remote,https://www.linkedin.com/jobs/view/1,desc\n'
    ).encode()

    response = _upload(content)

    assert response.status_code == 422


# --- Column requirements and row bookkeeping ---

def test_batch_import_missing_required_column_returns_422():
    content = "title,company_name,location,description\nTAM,Acme,Remote,Some description\n".encode()

    response = _upload(content)

    assert response.status_code == 422
    assert "url" in response.json()["detail"].lower()


def test_batch_import_invalid_row_returns_422_with_row_number_and_fields():
    blank_title_row = ["   ", "Acme", "Remote", "https://www.linkedin.com/jobs/view/1000000004", "desc"]
    content = _csv_bytes([HIGH_SCORE_ROW, blank_title_row])

    response = _upload(content)

    assert response.status_code == 422
    errors = response.json()["detail"]["errors"]
    assert errors[0]["rows"] == [3]  # header=row 1, HIGH_SCORE_ROW=row 2, this row=row 3
    assert errors[0]["fields"] == ["title"]


def test_batch_import_ignores_fully_blank_row():
    content = _csv_bytes([HIGH_SCORE_ROW, ["", "", "", "", ""]])

    response = _upload(content)

    assert response.status_code == 200
    assert response.json()["imported_count"] == 1


def test_batch_import_partially_blank_row_fails_validation():
    partial_row = ["", "Acme", "Remote", "https://www.linkedin.com/jobs/view/1000000099", "desc"]
    content = _csv_bytes([HIGH_SCORE_ROW, partial_row])

    response = _upload(content)

    assert response.status_code == 422
    assert response.json()["detail"]["errors"][0]["fields"] == ["title"]


# --- File-level limits ---

def test_batch_import_empty_file_returns_422():
    response = _upload(b"")

    assert response.status_code == 422


def test_batch_import_file_too_large_returns_413():
    content = b"a" * (MAX_BATCH_FILE_SIZE_BYTES + 1)

    response = _upload(content)

    assert response.status_code == 413


def test_batch_import_too_many_rows_returns_422():
    rows = [
        [
            f"Technical Account Manager {i}",
            "Acme",
            "Remote - Worldwide",
            f"https://www.linkedin.com/jobs/view/{2_000_000_000 + i}",
            "SQL troubleshooting and root cause analysis.",
        ]
        for i in range(MAX_BATCH_ROWS + 1)
    ]
    content = _csv_bytes(rows)

    response = _upload(content)

    assert response.status_code == 422


# --- Duplicate URLs, detected after normalization ---

def test_batch_import_rejects_duplicate_urls_after_normalization():
    # Different raw strings, same normalized URL (host case-folds), so they
    # must be caught even though the raw text differs row to row.
    row_a = ["Technical Account Manager", "Acme", "Remote", "https://EXAMPLE.com/job/1", "desc one"]
    row_b = ["Technical Account Manager", "Acme", "Remote", "https://example.com/job/1", "desc two"]
    content = _csv_bytes([row_a, row_b])

    response = _upload(content)

    assert response.status_code == 422
    errors = response.json()["detail"]["errors"]
    assert errors[0]["rows"] == [2, 3]


# --- Atomicity ---

def test_batch_import_atomicity_nothing_stored_when_one_row_invalid():
    bad_row = ["", "Acme", "Remote", "https://www.linkedin.com/jobs/view/1000000005", "desc"]
    content = _csv_bytes([HIGH_SCORE_ROW, bad_row])

    response = _upload(content)
    assert response.status_code == 422

    source_job_id = _generate_source_job_id(HIGH_SCORE_ROW[3])
    get_response = client.get(f"/jobs/manual_import:{source_job_id}")
    assert get_response.status_code == 404


def test_batch_import_atomicity_nothing_stored_when_urls_duplicated():
    content = _csv_bytes(
        [
            HIGH_SCORE_ROW,
            ["Technical Account Manager", "Acme", "Remote", "https://EXAMPLE.com/job/1", "desc"],
            ["Technical Account Manager", "Acme", "Remote", "https://example.com/job/1", "desc"],
        ]
    )

    response = _upload(content)
    assert response.status_code == 422

    source_job_id = _generate_source_job_id(HIGH_SCORE_ROW[3])
    get_response = client.get(f"/jobs/manual_import:{source_job_id}")
    assert get_response.status_code == 404


# --- Response ordering and visibility ---

def test_batch_import_response_is_sorted_and_keeps_not_eligible_visible():
    content = _csv_bytes([LOW_SCORE_NOT_ELIGIBLE_ROW, HIGH_SCORE_ROW])  # deliberately out of order

    response = _upload(content)

    assert response.status_code == 200
    jobs = response.json()["jobs"]
    assert [job["title"] for job in jobs] == ["Technical Account Manager", "Marketing Intern"]
    assert jobs[0]["score"] > jobs[1]["score"]
    assert jobs[1]["geo_eligibility"] == "not_eligible"  # still present, not silently dropped


# --- No OpenAI calls ---

def test_batch_import_never_calls_summarize_job():
    content = _csv_bytes([HIGH_SCORE_ROW])

    with patch.object(main, "summarize_job") as mock_summarize:
        response = _upload(content)

    assert response.status_code == 200
    mock_summarize.assert_not_called()


# --- Imported jobs are reachable via the existing single-job endpoint ---

def test_batch_import_result_ids_are_retrievable_via_get_job():
    content = _csv_bytes([HIGH_SCORE_ROW])

    response = _upload(content)
    job_id = response.json()["jobs"][0]["id"]

    get_response = client.get(f"/jobs/{job_id}")

    assert get_response.status_code == 200
    assert get_response.json()["id"] == job_id
