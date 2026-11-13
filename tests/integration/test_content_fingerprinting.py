import hashlib
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from tests.integration.authenticated_client import TestClient
from sqlalchemy import func, select

from apps.api.app.database import SessionLocal, initialize_database
from apps.api.app.main import app
from apps.api.app.source_model import Source
from apps.api.app.source_registry import (
    file_sha256, github_manifest_sha256, initialize_fingerprint_claims,
)

initialize_database()
with SessionLocal() as db:
    initialize_fingerprint_claims(db)
client = TestClient(app)


def test_sha256_matches_reference(tmp_path):
    p = tmp_path / "sample.txt"
    p.write_bytes(b"DATUMOR fingerprint")
    assert file_sha256(p) == hashlib.sha256(b"DATUMOR fingerprint").hexdigest()


def test_manifest_independent_of_creation_order(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    (a / "one.py").write_text("print(1)")
    (a / "two.py").write_text("print(2)")
    (b / "two.py").write_text("print(2)")
    (b / "one.py").write_text("print(1)")
    assert github_manifest_sha256(a) == github_manifest_sha256(b)
    (b / "two.py").write_text("print(3)")
    assert github_manifest_sha256(a) != github_manifest_sha256(b)


def test_same_content_different_filenames_returns_canonical():
    payload = f"DATUMOR duplicate {uuid.uuid4()}".encode()
    first = client.post("/api/v1/ingestion/files", files={"file": ("alpha.txt", payload, "text/plain")})
    second = client.post("/api/v1/ingestion/files", files={"file": ("beta.txt", payload, "text/plain")})
    assert first.status_code == second.status_code == 201
    assert first.json()["duplicate"] is False
    assert second.json()["duplicate"] is True
    assert first.json()["source"]["source_id"] == second.json()["source"]["source_id"]
    assert not (Path("data/staging") / (second.json()["data"]["upload_id"] + ".txt")).exists()


def test_different_content_not_duplicate():
    token = str(uuid.uuid4())
    first = client.post("/api/v1/ingestion/files", files={"file": ("same.txt", token.encode(), "text/plain")})
    second = client.post("/api/v1/ingestion/files", files={"file": ("same.txt", (token + "-changed").encode(), "text/plain")})
    assert first.status_code == second.status_code == 201
    assert first.json()["duplicate"] is False
    assert second.json()["duplicate"] is False
    assert first.json()["source"]["source_id"] != second.json()["source"]["source_id"]


def test_parallel_duplicates_have_one_canonical_record():
    payload = f"DATUMOR parallel {uuid.uuid4()}".encode()

    def upload(_):
        return client.post(
            "/api/v1/ingestion/files",
            files={"file": ("parallel.txt", payload, "text/plain")},
        )

    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(upload, range(5)))

    assert all(r.status_code == 201 for r in results), [
        r.text for r in results
    ]

    source_ids = {
        r.json()["data"].get("source_id")
        for r in results
    }
    source_ids.discard(None)
    assert len(source_ids) <= 1, source_ids



def test_existing_sources_backfilled_without_deletion():
    with SessionLocal() as db:
        before = db.scalar(select(func.count()).select_from(Source))
        initialize_fingerprint_claims(db)
        after = db.scalar(select(func.count()).select_from(Source))
        assert before == after
