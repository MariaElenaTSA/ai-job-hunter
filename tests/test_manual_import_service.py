import hashlib
import threading

import pytest
from pydantic import ValidationError

from app.services import manual_import_service
from app.services.manual_import_service import ManualJobImport


@pytest.fixture(autouse=True)
def _reset_store():
    manual_import_service._reset_imports()
    yield
    manual_import_service._reset_imports()


def make_payload(**overrides):
    fields = {
        "url": "https://www.linkedin.com/jobs/view/1234567890",
        "title": "Technical Account Manager",
        "company_name": "Example Company",
        "location": "Remote - LATAM",
        "description": "Full job description with real content.",
    }
    fields.update(overrides)
    return ManualJobImport(**fields)


# --- URL scheme validation ---

@pytest.mark.parametrize("bad_url", [
    "file:///etc/passwd",
    "javascript:alert(1)",
    "data:text/plain,hello",
    "ftp://example.com/job",
])
def test_rejects_disallowed_url_schemes(bad_url):
    with pytest.raises(ValidationError):
        make_payload(url=bad_url)


def test_accepts_http_and_https():
    make_payload(url="http://example.com/job/1")
    make_payload(url="https://example.com/job/1")


# --- Text validation: blank and length limits ---

def test_title_whitespace_only_is_rejected():
    with pytest.raises(ValidationError):
        make_payload(title="    ")


def test_description_whitespace_only_is_rejected():
    with pytest.raises(ValidationError):
        make_payload(description="\n\t   ")


def test_title_over_max_length_is_rejected():
    with pytest.raises(ValidationError):
        make_payload(title="x" * (manual_import_service.MAX_TITLE_LENGTH + 1))


def test_company_name_over_max_length_is_rejected():
    with pytest.raises(ValidationError):
        make_payload(company_name="x" * (manual_import_service.MAX_COMPANY_NAME_LENGTH + 1))


def test_location_over_max_length_is_rejected():
    with pytest.raises(ValidationError):
        make_payload(location="x" * (manual_import_service.MAX_LOCATION_LENGTH + 1))


def test_description_over_max_length_is_rejected():
    with pytest.raises(ValidationError):
        make_payload(description="x" * (manual_import_service.MAX_DESCRIPTION_LENGTH + 1))


def test_title_at_exactly_max_length_is_accepted():
    payload = make_payload(title="x" * manual_import_service.MAX_TITLE_LENGTH)
    assert len(payload.title) == manual_import_service.MAX_TITLE_LENGTH


def test_description_at_exactly_max_length_is_accepted():
    payload = make_payload(description="x" * manual_import_service.MAX_DESCRIPTION_LENGTH)
    assert len(payload.description) == manual_import_service.MAX_DESCRIPTION_LENGTH


def test_company_name_whitespace_only_normalizes_to_none():
    payload = make_payload(company_name="   ")
    assert payload.company_name is None


def test_location_whitespace_only_normalizes_to_empty_string():
    payload = make_payload(location="   ")
    assert payload.location == ""


def test_company_name_and_location_missing_default_to_none_and_empty():
    payload = ManualJobImport(
        url="https://www.linkedin.com/jobs/view/1234567890",
        title="Technical Account Manager",
        description="Full job description.",
    )
    assert payload.company_name is None
    assert payload.location == ""


def test_description_html_is_preserved_verbatim():
    html_description = "<p>Full   description</p>\n\twith <b>whitespace</b> preserved."
    payload = make_payload(description=html_description)

    assert payload.description == html_description


# --- URL canonicalization: same normalized string used everywhere ---

def test_normalize_job_uses_the_same_normalized_url_for_id_and_all_url_fields():
    payload = make_payload(url="https://www.linkedin.com/jobs/view/1234567890")
    job = manual_import_service.normalize_job(payload)

    normalized_url = str(payload.url)
    expected_id = hashlib.sha256(normalized_url.encode("utf-8")).hexdigest()[:16]

    assert job["source_job_id"] == expected_id
    assert job["id"] == f"manual_import:{expected_id}"
    assert job["source_url"] == normalized_url
    assert job["application_url"] == normalized_url
    assert job["absolute_url"] == normalized_url


def test_normalize_job_maps_common_fields():
    payload = make_payload()
    job = manual_import_service.normalize_job(payload)

    assert job["source"] == "manual_import"
    assert job["title"] == "Technical Account Manager"
    assert job["company_name"] == "Example Company"
    assert job["location"] == {"name": "Remote - LATAM"}
    assert job["workplace_type"] is None
    assert job["content"] == payload.description
    assert job["first_published"] is None
    assert job["updated_at"] is None
    assert job["language"] is None
    assert job["application_deadline"] is None
    assert job["attribution"] == "Manual import"


# --- Storage: determinism, replacement, isolation, no mutable leaks ---

def test_two_imports_of_the_same_url_produce_the_same_id_and_replace_each_other():
    first_payload = make_payload(title="First Title")
    second_payload = make_payload(title="Second Title")

    first_job = manual_import_service.build_normalized_job(first_payload)
    second_job = manual_import_service.build_normalized_job(second_payload)

    assert first_job["id"] == second_job["id"]

    stored = manual_import_service.get_stored_job(second_job["source_job_id"])
    assert stored["title"] == "Second Title"  # the first entry was replaced, not duplicated


def test_get_stored_job_returns_none_for_unknown_id():
    assert manual_import_service.get_stored_job("does-not-exist") is None


def test_get_stored_job_does_not_expose_the_stored_reference():
    payload = make_payload()
    job = manual_import_service.build_normalized_job(payload)

    retrieved = manual_import_service.get_stored_job(job["source_job_id"])
    retrieved["title"] = "Mutated"
    retrieved["location"]["name"] = "Mutated Location"

    retrieved_again = manual_import_service.get_stored_job(job["source_job_id"])
    assert retrieved_again["title"] == payload.title
    assert retrieved_again["location"]["name"] == payload.location


def test_reset_imports_keeps_tests_independent():
    payload = make_payload()
    job = manual_import_service.build_normalized_job(payload)

    manual_import_service._reset_imports()

    assert manual_import_service.get_stored_job(job["source_job_id"]) is None


def test_concurrent_imports_do_not_corrupt_the_store():
    urls = [f"https://www.linkedin.com/jobs/view/{i}" for i in range(20)]

    def worker(url):
        manual_import_service.build_normalized_job(make_payload(url=url))

    threads = [threading.Thread(target=worker, args=(url,)) for url in urls]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    for url in urls:
        source_job_id = manual_import_service._generate_source_job_id(url)
        assert manual_import_service.get_stored_job(source_job_id) is not None
