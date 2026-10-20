"""Batch import of manually-curated job postings from a CSV file.

Reuses ManualJobImport (schema + validation), normalize_job (URL/id
normalization), format_job (score/eligibility), and
manual_import_service.store_jobs_batch (storage) -- this module owns only
the CSV-specific concerns: parsing, header validation, row bookkeeping, and
orchestrating "validate everything before storing anything" atomicity.

No scraping, no fetching, no OpenAI calls: rows only ever come from the
uploaded file's own columns.
"""

import csv
import io

from pydantic import ValidationError

from app.config import MAX_BATCH_FILE_SIZE_BYTES, MAX_BATCH_ROWS, OPTIONAL_BATCH_COLUMNS, REQUIRED_BATCH_COLUMNS
from app.services import manual_import_service
from app.services.job_service import format_job, sort_jobs_for_recommendation
from app.services.manual_import_service import ManualJobImport, normalize_job

ALLOWED_BATCH_COLUMNS = REQUIRED_BATCH_COLUMNS | OPTIONAL_BATCH_COLUMNS


class BatchFileError(Exception):
    """A problem with the file as a whole: wrong extension, too large, bad
    encoding, malformed CSV, or a bad/missing header. Caught in main.py and
    turned into the matching HTTP status code."""

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class BatchRowErrors(Exception):
    """One or more rows failed validation or duplicate-detection. Carries
    every error found (not just the first) so the caller can fix the source
    file in a single pass. Always maps to HTTP 422."""

    def __init__(self, errors: list[dict]):
        super().__init__(f"{len(errors)} invalid row(s)")
        self.errors = errors


def _check_extension(filename: str | None) -> None:
    # Extension is the only trustworthy signal here: browsers, Excel, and
    # Google Sheets send wildly inconsistent Content-Types for CSV
    # (text/csv, application/csv, application/vnd.ms-excel, text/plain,
    # application/octet-stream, or nothing at all). MIME type is never
    # treated as proof of content -- the real validation is that the bytes
    # decode as UTF-8 and parse as CSV with the expected header, below.
    if not filename or not filename.lower().endswith(".csv"):
        raise BatchFileError(415, "Only .csv files are supported")


def _decode(raw_bytes: bytes) -> str:
    if not raw_bytes:
        raise BatchFileError(422, "File is empty")
    try:
        # utf-8-sig transparently strips a leading UTF-8 BOM (common from
        # Excel exports) and behaves exactly like utf-8 when there is none.
        return raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise BatchFileError(422, "File must be UTF-8 encoded") from None


def _normalize_header(header_row: list[str]) -> list[str]:
    normalized = [cell.strip().lower() for cell in header_row]

    seen = set()
    duplicates = set()
    for name in normalized:
        if name in seen:
            duplicates.add(name)
        seen.add(name)
    if duplicates:
        raise BatchFileError(422, f"Duplicate column(s) in header: {', '.join(sorted(duplicates))}")

    missing = REQUIRED_BATCH_COLUMNS - seen
    if missing:
        raise BatchFileError(422, f"Missing required column(s): {', '.join(sorted(missing))}")

    return normalized


def _is_blank_row(row: dict) -> bool:
    return all(not (row.get(name) or "").strip() for name in ALLOWED_BATCH_COLUMNS)


def _parse_rows(text: str) -> list[tuple[int, dict]]:
    buffer = io.StringIO(text)
    reader = csv.reader(buffer, strict=True)

    try:
        header_row = next(reader)
    except StopIteration:
        raise BatchFileError(422, "File has no header row") from None
    except csv.Error as error:
        raise BatchFileError(422, f"Malformed CSV: {error}") from None

    header = _normalize_header(header_row)

    rows = []
    try:
        # Header is row 1, so the first data row is row 2 -- DictReader
        # yields one dict per logical record (it already merges embedded
        # newlines inside quoted fields into a single row), so this count
        # matches what the user sees when they open the file.
        for row_number, row in enumerate(csv.DictReader(buffer, fieldnames=header, strict=True), start=2):
            if _is_blank_row(row):
                continue
            rows.append((row_number, row))
    except csv.Error as error:
        raise BatchFileError(422, f"Malformed CSV: {error}") from None

    if not rows:
        raise BatchFileError(422, "File has no data rows")
    if len(rows) > MAX_BATCH_ROWS:
        raise BatchFileError(422, f"Too many rows: max {MAX_BATCH_ROWS}")

    return rows


def _build_payloads(rows: list[tuple[int, dict]]) -> list[tuple[int, ManualJobImport]]:
    payloads = []
    errors = []

    for row_number, row in rows:
        fields = {name: row.get(name) for name in ALLOWED_BATCH_COLUMNS}
        try:
            payloads.append((row_number, ManualJobImport(**fields)))
        except ValidationError as error:
            affected = sorted({str(err["loc"][0]) for err in error.errors()})
            errors.append(
                {
                    "rows": [row_number],
                    "fields": affected,
                    # pydantic's msg strings here are metadata ("title must
                    # not be blank", "at most 300 characters") -- never the
                    # submitted value, so the description is never echoed.
                    "message": "; ".join(err["msg"] for err in error.errors()),
                }
            )

    if errors:
        raise BatchRowErrors(errors)

    return payloads


def _normalize_all(payloads: list[tuple[int, ManualJobImport]]) -> list[tuple[int, dict]]:
    return [(row_number, normalize_job(payload)) for row_number, payload in payloads]


def _detect_duplicates(normalized: list[tuple[int, dict]]) -> None:
    # Duplicates are detected on the *normalized* id, not the raw URL, so
    # that pydantic-equivalent variants (e.g. a trailing slash HttpUrl
    # collapses) are caught too.
    first_seen_at: dict[str, int] = {}
    errors = []

    for row_number, job in normalized:
        source_job_id = job["source_job_id"]
        if source_job_id in first_seen_at:
            errors.append(
                {
                    "rows": [first_seen_at[source_job_id], row_number],
                    "fields": ["url"],
                    "message": "Duplicate job: same normalized URL as another row",
                }
            )
        else:
            first_seen_at[source_job_id] = row_number

    if errors:
        raise BatchRowErrors(errors)


def import_batch(filename: str | None, raw_bytes: bytes, profile) -> dict:
    """Validate and import every row of a CSV file atomically: nothing is
    stored unless every row parses, validates, and normalizes cleanly with
    no duplicate URLs."""
    _check_extension(filename)

    if len(raw_bytes) > MAX_BATCH_FILE_SIZE_BYTES:
        raise BatchFileError(413, f"File exceeds the {MAX_BATCH_FILE_SIZE_BYTES} byte limit")

    text = _decode(raw_bytes)
    rows = _parse_rows(text)
    payloads = _build_payloads(rows)
    normalized = _normalize_all(payloads)
    _detect_duplicates(normalized)

    jobs = [job for _, job in normalized]
    formatted_jobs = sort_jobs_for_recommendation([format_job(job, profile) for job in jobs])

    # Only now, after every row has validated, normalized, scored, and
    # sorted without error, do we touch the store -- and in one lock
    # acquisition, so a failure anywhere above leaves zero partial imports.
    manual_import_service.store_jobs_batch(jobs)

    return {"imported_count": len(formatted_jobs), "jobs": formatted_jobs}
