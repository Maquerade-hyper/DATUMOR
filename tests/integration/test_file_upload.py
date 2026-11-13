import uuid
import json

from tests.integration.authenticated_client import TestClient

from apps.api.app.main import app
from apps.api.app.config import STAGING_DIR

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_upload_valid_text_file():
    payload = b"DATUMOR real ingestion test " + uuid.uuid4().hex.encode()
    response = client.post(
        "/api/v1/ingestion/files",
        files={"file": ("sample.txt", payload, "text/plain")},
    )
    assert response.status_code == 201
    result = response.json()["data"]
    assert result["status"] == "staged"
    assert result["original_filename"] == "sample.txt"
    assert (STAGING_DIR / f'{result["upload_id"]}.txt').read_bytes() == (
        payload
    )


def test_upload_valid_pdf():
    content = b"%PDF-1.4\nDATUMOR PDF test " + uuid.uuid4().hex.encode() + b"\n%%EOF"
    response = client.post(
        "/api/v1/ingestion/files",
        files={"file": ("sample.pdf", content, "application/pdf")},
    )
    assert response.status_code == 201
    assert response.json()["data"]["extension"] == ".pdf"


def test_upload_valid_json():
    content = json.dumps({"name": "DATUMOR", "version": 1, "test_id": uuid.uuid4().hex}).encode()
    response = client.post(
        "/api/v1/ingestion/files",
        files={"file": ("sample.json", content, "application/json")},
    )
    assert response.status_code == 201


def test_upload_valid_jsonl():
    content = (
        '{"instruction":"Explain Python ' + uuid.uuid4().hex + '"}\n'
        '{"instruction":"Explain SQL"}\n'
    ).encode()
    response = client.post(
        "/api/v1/ingestion/files",
        files={"file": ("sample.jsonl", content, "application/jsonl")},
    )
    assert response.status_code == 201


def test_upload_valid_csv():
    content = ("name,language,test_id\nPython,programming," + uuid.uuid4().hex + "\n").encode()
    response = client.post(
        "/api/v1/ingestion/files",
        files={"file": ("sample.csv", content, "text/csv")},
    )
    assert response.status_code == 201


def test_upload_valid_markdown():
    response = client.post(
        "/api/v1/ingestion/files",
        files={"file": ("sample.md", ("# DATUMOR\nIngestion test " + uuid.uuid4().hex).encode(), "text/markdown")},
    )
    assert response.status_code == 201


def test_reject_unsupported_extension():
    response = client.post(
        "/api/v1/ingestion/files",
        files={"file": ("malware.exe", b"not allowed", "application/octet-stream")},
    )
    assert response.status_code == 422


def test_reject_invalid_json():
    response = client.post(
        "/api/v1/ingestion/files",
        files={"file": ("broken.json", b"{invalid json}", "application/json")},
    )
    assert response.status_code == 422


def test_reject_invalid_pdf_signature():
    response = client.post(
        "/api/v1/ingestion/files",
        files={"file": ("fake.pdf", b"not a pdf", "application/pdf")},
    )
    assert response.status_code == 422


def test_reject_empty_file():
    response = client.post(
        "/api/v1/ingestion/files",
        files={"file": ("empty.txt", b"", "text/plain")},
    )
    assert response.status_code == 422


def test_reject_invalid_jsonl():
    response = client.post(
        "/api/v1/ingestion/files",
        files={"file": ("broken.jsonl", b'{"ok":true}\nnot-json\n', "application/jsonl")},
    )
    assert response.status_code == 422


def test_reject_invalid_csv_header():
    response = client.post(
        "/api/v1/ingestion/files",
        files={"file": ("broken.csv", b"name,,age\nAlice,1,20", "text/csv")},
    )
    assert response.status_code == 422


def test_reject_path_traversal_filename():
    response = client.post(
        "/api/v1/ingestion/files",
        files={"file": ("../../outside.txt", (b"safe content " + uuid.uuid4().hex.encode()), "text/plain")},
    )
    assert response.status_code == 201
    result = response.json()["data"]
    assert result["original_filename"] == "outside.txt"
    assert (STAGING_DIR / f'{result["upload_id"]}.txt').exists()


def test_staged_file_uses_generated_name():
    response = client.post(
        "/api/v1/ingestion/files",
        files={"file": ("customer-name.txt", (b"private content " + uuid.uuid4().hex.encode()), "text/plain")},
    )
    result = response.json()["data"]
    assert result["upload_id"] in result["original_filename"] or (
        STAGING_DIR / f'{result["upload_id"]}.txt'
    ).exists()
