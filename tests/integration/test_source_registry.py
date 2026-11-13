import uuid

from tests.integration.authenticated_client import TestClient
from sqlalchemy import text

from apps.api.app.main import app
from apps.api.app.database import engine, initialize_database, SessionLocal
from apps.api.app.source_model import Source

initialize_database()
client = TestClient(app)


def test_postgres_connection():
    with engine.connect() as connection:
        assert connection.execute(text("SELECT 1")).scalar() == 1


def test_sources_table_exists():
    with engine.connect() as connection:
        result = connection.execute(text(
            "SELECT to_regclass('public.sources')"
        )).scalar()
    assert result == "sources"


def test_file_upload_registers_source():
    response = client.post(
        "/api/v1/ingestion/files",
        files={"file": ("registry-test.txt", (b"DATUMOR source registry test " + uuid.uuid4().hex.encode()), "text/plain")},
    )
    assert response.status_code == 201

    body = response.json()
    assert body["success"] is True
    assert body["source"]["source_type"] == "file"
    assert body["source"]["source_id"] == body["data"]["upload_id"]
    assert len(body["source"]["checksum_sha256"]) == 64

    source_id = body["source"]["source_id"]
    lookup = client.get(f"/api/v1/sources/{source_id}")
    assert lookup.status_code == 200
    assert lookup.json()["source_name"] == "registry-test.txt"


def test_source_list_contains_registered_file():
    response = client.get("/api/v1/sources?limit=100")
    assert response.status_code == 200
    sources = response.json()
    assert isinstance(sources, list)
    assert any(
        source.get("source_name") == "registry-test.txt"
        for source in sources
    )


def test_source_not_found():
    response = client.get(
        "/api/v1/sources/99999999-9999-4999-8999-999999999999"
    )
    assert response.status_code == 404


def test_invalid_source_id():
    response = client.get("/api/v1/sources/not-a-uuid")
    assert response.status_code == 422


def test_source_record_persists_in_postgres():
    response = client.post(
        "/api/v1/ingestion/files",
        files={"file": ("persistence.txt", (b"Persistent registry record " + uuid.uuid4().hex.encode()), "text/plain")},
    )
    assert response.status_code == 201

    source_id = uuid.UUID(response.json()["source"]["source_id"])

    with SessionLocal() as session:
        record = session.get(Source, source_id)
        assert record is not None
        assert record.source_name == "persistence.txt"
        assert record.status == "staged"
