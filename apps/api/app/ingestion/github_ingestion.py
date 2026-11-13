import io
import re
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

import requests

from apps.api.app.config import STAGING_DIR

MAX_ARCHIVE_BYTES = 100 * 1024 * 1024
MAX_EXTRACTED_BYTES = 250 * 1024 * 1024
MAX_FILES = 5000
MAX_SINGLE_FILE_BYTES = 50 * 1024 * 1024
TIMEOUT = (10, 60)

EXCLUDED_DIRS = {
    ".git", ".github", ".idea", ".vscode", "__pycache__",
    "node_modules", "vendor", ".venv", "venv",
    "dist", "build", "coverage"
}
EXCLUDED_FILES = {
    ".DS_Store", "Thumbs.db"
}
ALLOWED_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx",
    ".java", ".c", ".cpp", ".h", ".hpp",
    ".cs", ".go", ".rs", ".php", ".rb",
    ".swift", ".kt", ".scala", ".sh",
    ".sql", ".html", ".css", ".scss",
    ".json", ".jsonl", ".yaml", ".yml",
    ".toml", ".ini", ".cfg", ".xml",
    ".md", ".txt", ".rst", ".csv",
    ".ipynb", ".dockerfile", ".env.example"
}


class GitHubIngestionError(Exception):
    pass


def parse_repository_url(url: str) -> tuple[str, str]:
    parsed = urlparse(url.strip())

    if parsed.scheme != "https" or parsed.hostname != "github.com":
        raise GitHubIngestionError("Only HTTPS public github.com URLs are accepted.")

    if parsed.username or parsed.password or parsed.port:
        raise GitHubIngestionError("Credentials and custom ports are not allowed.")

    parts = [p for p in parsed.path.strip("/").split("/") if p]

    if len(parts) not in (2, 3) or (len(parts) == 3 and parts[2] != ""):
        raise GitHubIngestionError(
            "Provide a repository URL in the form https://github.com/owner/repository."
        )

    owner, repository = parts[:2]
    repository = repository.removesuffix(".git")

    pattern = r"^[A-Za-z0-9_.-]+$"
    if not re.fullmatch(pattern, owner) or not re.fullmatch(pattern, repository):
        raise GitHubIngestionError("Invalid GitHub owner or repository name.")

    if owner in {".", ".."} or repository in {".", ".."}:
        raise GitHubIngestionError("Invalid repository path.")

    return owner, repository


def _github_get(url: str, stream: bool = False):
    try:
        response = requests.get(
            url,
            headers={"Accept": "application/vnd.github+json", "User-Agent": "DATUMOR"},
            timeout=TIMEOUT,
            stream=stream,
            allow_redirects=True,
        )
    except requests.RequestException as exc:
        raise GitHubIngestionError("Unable to reach GitHub.") from exc

    if response.status_code == 404:
        raise GitHubIngestionError("GitHub repository or branch was not found.")
    if response.status_code == 403:
        raise GitHubIngestionError("GitHub rate limit or access restriction encountered.")
    if response.status_code >= 400:
        raise GitHubIngestionError(
            f"GitHub returned HTTP {response.status_code}."
        )

    if stream:
        final_host = urlparse(response.url).hostname
        if final_host not in {"codeload.github.com", "github.com"}:
            response.close()
            raise GitHubIngestionError("Unexpected archive download host.")

    return response


def _safe_archive_path(name: str) -> PurePosixPath | None:
    if "\\" in name or "\x00" in name:
        return None

    path = PurePosixPath(name)

    if path.is_absolute() or not path.parts:
        return None

    if any(part in {"", ".", ".."} for part in path.parts):
        return None

    if path.parts[0].startswith("/") or ":" in path.parts[0]:
        return None

    return path


def _included(path: PurePosixPath) -> bool:
    if any(part in EXCLUDED_DIRS for part in path.parts[:-1]):
        return False

    filename = path.name
    if filename in EXCLUDED_FILES:
        return False

    if filename.startswith(".") and filename not in {
        ".gitignore", ".dockerignore", ".editorconfig"
    }:
        return False

    suffix = Path(filename).suffix.lower()
    if filename.lower() == "dockerfile":
        return True

    return suffix in ALLOWED_EXTENSIONS


def ingest_github_repository(
    repository_url: str,
    branch: str | None = None,
) -> dict:
    owner, repository = parse_repository_url(repository_url)

    api_base = f"https://api.github.com/repos/{owner}/{repository}"
    metadata_response = _github_get(api_base)
    metadata = metadata_response.json()

    if metadata.get("private") is True:
        raise GitHubIngestionError("Private repositories are not supported.")

    default_branch = metadata.get("default_branch")
    if not isinstance(default_branch, str) or not default_branch:
        raise GitHubIngestionError("GitHub did not provide a valid default branch.")

    selected_branch = branch.strip() if branch and branch.strip() else default_branch

    if len(selected_branch) > 255 or selected_branch.startswith("-"):
        raise GitHubIngestionError("Invalid branch name.")

    branch_response = _github_get(
        f"{api_base}/branches/{requests.utils.quote(selected_branch, safe='')}"
    )
    branch_data = branch_response.json()

    commit_sha = branch_data.get("commit", {}).get("sha")
    if not commit_sha:
        raise GitHubIngestionError("Unable to verify selected branch commit.")

    archive_url = (
        f"https://codeload.github.com/{owner}/{repository}"
        f"/zip/refs/heads/{requests.utils.quote(selected_branch, safe='/')}"
    )

    response = _github_get(archive_url, stream=True)
    archive_bytes = bytearray()

    try:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if not chunk:
                continue
            archive_bytes.extend(chunk)
            if len(archive_bytes) > MAX_ARCHIVE_BYTES:
                raise GitHubIngestionError("Repository archive exceeds 100 MiB.")
    finally:
        response.close()

    if not archive_bytes:
        raise GitHubIngestionError("GitHub returned an empty archive.")

    upload_id = str(uuid.uuid4())
    destination = STAGING_DIR / f"github-{upload_id}"
    destination.mkdir(parents=True, exist_ok=False)

    extracted_files = []
    skipped_files = 0
    total_bytes = 0

    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            members = archive.infolist()

            if len(members) > MAX_FILES * 4:
                raise GitHubIngestionError("Repository archive contains too many entries.")

            root_prefix = members[0].filename.split("/", 1)[0] + "/"

            for member in members:
                if member.is_dir():
                    continue

                raw_name = member.filename
                if not raw_name.startswith(root_prefix):
                    skipped_files += 1
                    continue

                relative_name = raw_name[len(root_prefix):]
                safe_path = _safe_archive_path(relative_name)

                if safe_path is None:
                    skipped_files += 1
                    continue

                # Reject symlinks and special Unix file types.
                unix_mode = member.external_attr >> 16
                file_type = unix_mode & 0o170000
                if file_type not in (0, 0o100000):
                    skipped_files += 1
                    continue

                if not _included(safe_path):
                    skipped_files += 1
                    continue

                if member.file_size > MAX_SINGLE_FILE_BYTES:
                    skipped_files += 1
                    continue

                if member.file_size < 0 or member.file_size > MAX_EXTRACTED_BYTES:
                    skipped_files += 1
                    continue

                if total_bytes + member.file_size > MAX_EXTRACTED_BYTES:
                    skipped_files += 1
                    continue

                if len(extracted_files) >= MAX_FILES:
                    skipped_files += 1
                    continue

                target = destination.joinpath(*safe_path.parts)
                target.parent.mkdir(parents=True, exist_ok=True)

                data = archive.read(member)
                if len(data) != member.file_size:
                    raise GitHubIngestionError("Archive entry size mismatch.")

                target.write_bytes(data)
                total_bytes += len(data)
                extracted_files.append({
                    "path": safe_path.as_posix(),
                    "size_bytes": len(data),
                })

        if not extracted_files:
            raise GitHubIngestionError("Repository contained no supported files.")

        return {
            "repository_id": upload_id,
            "owner": owner,
            "repository": repository,
            "repository_url": f"https://github.com/{owner}/{repository}",
            "branch": selected_branch,
            "default_branch": default_branch,
            "commit_sha": commit_sha,
            "description": metadata.get("description"),
            "stars": metadata.get("stargazers_count", 0),
            "license": (metadata.get("license") or {}).get("spdx_id"),
            "file_count": len(extracted_files),
            "skipped_file_count": skipped_files,
            "total_bytes": total_bytes,
            "status": "staged",
            "staging_path": str(destination),
            "files": extracted_files,
        }

    except Exception:
        import shutil
        shutil.rmtree(destination, ignore_errors=True)
        raise
