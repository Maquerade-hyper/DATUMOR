import io
import zipfile
from pathlib import PurePosixPath

import pytest

from apps.api.app.ingestion.github_ingestion import (
    GitHubIngestionError,
    parse_repository_url,
    _safe_archive_path,
    _included,
)


@pytest.mark.parametrize("url,expected", [
    ("https://github.com/pallets/flask", ("pallets", "flask")),
    ("https://github.com/psf/requests.git", ("psf", "requests")),
])
def test_parse_valid_repository_urls(url, expected):
    assert parse_repository_url(url) == expected


@pytest.mark.parametrize("url", [
    "http://github.com/pallets/flask",
    "https://evil.com/pallets/flask",
    "https://github.com/pallets",
    "https://github.com/pallets/flask/tree/main",
    "https://user:pass@github.com/pallets/flask",
    "https://github.com:8443/pallets/flask",
])
def test_reject_invalid_repository_urls(url):
    with pytest.raises(GitHubIngestionError):
        parse_repository_url(url)


@pytest.mark.parametrize("path", [
    "../outside.txt",
    "/absolute.txt",
    "folder/../../outside.txt",
    r"folder\..\outside.txt",
    "C:/outside.txt",
])
def test_reject_unsafe_archive_paths(path):
    assert _safe_archive_path(path) is None


def test_allow_safe_archive_path():
    assert _safe_archive_path("src/main.py") == PurePosixPath("src/main.py")


@pytest.mark.parametrize("path", [
    "src/main.py",
    "README.md",
    "data/records.jsonl",
    "Dockerfile",
])
def test_allow_supported_files(path):
    assert _included(PurePosixPath(path))


@pytest.mark.parametrize("path", [
    ".git/config",
    "node_modules/package/index.js",
    "venv/lib/python.py",
    "image.png",
    ".env",
])
def test_exclude_unsupported_or_sensitive_files(path):
    assert not _included(PurePosixPath(path))


def test_archive_path_validation_prevents_traversal():
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("repo-main/../outside.txt", "unsafe")
    archive.seek(0)
    with zipfile.ZipFile(archive) as z:
        member = z.infolist()[0]
        relative = member.filename.split("/", 1)[1]
        assert _safe_archive_path(relative) is None
