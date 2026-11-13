import csv
import io
import json
import uuid
from pathlib import Path

from fastapi import UploadFile

from apps.api.app.config import (
    ALLOWED_EXTENSIONS,
    MAX_UPLOAD_BYTES,
    STAGING_DIR,
)


class UploadValidationError(Exception):
    pass


def validate_content(path: Path, extension: str) -> None:
    data = path.read_bytes()

    if not data:
        raise UploadValidationError("Empty files are not accepted.")

    if extension == ".pdf":
        if not data.startswith(b"%PDF-"):
            raise UploadValidationError("File does not contain a valid PDF signature.")
        return

    if b"\x00" in data:
        raise UploadValidationError("Binary content is not accepted for this file type.")

    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise UploadValidationError("File must contain valid UTF-8 text.") from exc

    if extension == ".json":
        try:
            json.loads(text)
        except json.JSONDecodeError as exc:
            raise UploadValidationError(f"Invalid JSON: {exc.msg}") from exc

    elif extension == ".jsonl":
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            raise UploadValidationError("JSONL must contain at least one JSON record.")
        for number, line in enumerate(lines, start=1):
            try:
                json.loads(line)
            except json.JSONDecodeError as exc:
                raise UploadValidationError(
                    f"Invalid JSONL record near line {number}: {exc.msg}"
                ) from exc

    elif extension == ".csv":
        try:
            reader = csv.reader(io.StringIO(text))
            header = next(reader, None)
            if not header or not any(cell.strip() for cell in header):
                raise UploadValidationError("CSV must contain a non-empty header.")
            if any(not cell.strip() for cell in header):
                raise UploadValidationError("CSV header contains an empty column name.")
            if len(set(header)) != len(header):
                raise UploadValidationError("CSV header contains duplicate column names.")
        except csv.Error as exc:
            raise UploadValidationError(f"Invalid CSV: {exc}") from exc

    elif extension in {".txt", ".md", ".markdown"}:
        if not text.strip():
            raise UploadValidationError("Text file contains no usable content.")


async def stage_upload(upload: UploadFile) -> dict:
    original_name = (upload.filename or "").replace("\\", "/").split("/")[-1]
    if not original_name or original_name in {".", ".."}:
        raise UploadValidationError("A valid filename is required.")

    extension = Path(original_name).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise UploadValidationError(
            f"Unsupported file extension '{extension or '(none)'}'."
        )

    upload_id = str(uuid.uuid4())
    STAGING_DIR.mkdir(parents=True, exist_ok=True)

    temporary_path = STAGING_DIR / f"{upload_id}.part"
    final_path = STAGING_DIR / f"{upload_id}{extension}"
    total = 0

    try:
        with temporary_path.open("wb") as destination:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break

                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    raise UploadValidationError(
                        f"File exceeds the {MAX_UPLOAD_BYTES}-byte upload limit."
                    )

                destination.write(chunk)

        validate_content(temporary_path, extension)
        temporary_path.replace(final_path)

        return {
            "upload_id": upload_id,
            "original_filename": original_name,
            "extension": extension,
            "size_bytes": total,
            "status": "staged",
        }

    except Exception:
        temporary_path.unlink(missing_ok=True)
        final_path.unlink(missing_ok=True)
        raise

    finally:
        await upload.close()
