# DATUMOR API

From the project root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn apps.api.app.main:app --host 127.0.0.1 --port 8000 --reload
```

Health: http://127.0.0.1:8000/health
OpenAPI: http://127.0.0.1:8000/docs

File upload:
POST /api/v1/ingestion/files
multipart field: file

Maximum upload size: 50 MiB.
Supported formats: PDF, TXT, MD, Markdown, JSON, JSONL, CSV.

Uploads are temporarily staged under data/staging using generated identifiers.
Permanent object storage and source registration are implemented in later M1 steps.
