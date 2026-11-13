from pathlib import Path
import os

PROJECT_ROOT = Path(__file__).resolve().parents[3]
STAGING_DIR = Path(os.getenv("DATUMOR_STAGING_DIR", PROJECT_ROOT / "data" / "staging"))
MAX_UPLOAD_BYTES = int(os.getenv("DATUMOR_MAX_UPLOAD_BYTES", str(50 * 1024 * 1024)))

ALLOWED_EXTENSIONS = {
    ".pdf", ".txt", ".md", ".markdown",
    ".json", ".jsonl", ".csv"
}
