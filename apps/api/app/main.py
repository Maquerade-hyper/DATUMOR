from apps.api.app.detection.format_detector import detect_format
from pathlib import Path
import shutil
import uuid
import traceback as _m95_traceback

from fastapi import FastAPI, File, HTTPException, UploadFile, Depends, Form
from pydantic import BaseModel, HttpUrl
from sqlalchemy.orm import Session

from apps.api.app.config import STAGING_DIR
from apps.api.app.database import get_db, initialize_database, SessionLocal
from apps.api.app.ingestion.file_upload import UploadValidationError, stage_upload
from apps.api.app.ingestion.github_ingestion import GitHubIngestionError, ingest_github_repository
from apps.api.app.source_registry import (
    file_sha256, github_manifest_sha256, register_source_with_duplicate_info,
    serialize_source, initialize_fingerprint_claims,
)
from apps.api.app.source_model import Source
from apps.api.app.auth.dependencies import get_current_user
from apps.api.app.projects.project_model import Project
from sqlalchemy import select
from apps.api.app.usage.models import UsageEvent, UsagePolicy
from apps.api.app.usage.routes import router as usage_router, admin_router as admin_usage_router
from apps.api.app.usage.service import record_usage, check_rate_limit

from apps.api.app.auth.routes import router as auth_router, admin_router
from apps.api.app.projects import Project, ProjectActivity  # noqa: F401
from apps.api.app.projects.routes import router as projects_router, admin_projects_router
from apps.api.app.jobs.routes import router as jobs_router, admin_router as admin_jobs_router

app = FastAPI(title="DATUMOR API", version="0.1.0",
              description="Universal Multimodal Data Intelligence and Preparation Engine")

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(projects_router)
app.include_router(admin_projects_router)
app.include_router(jobs_router)
app.include_router(admin_jobs_router)
app.include_router(usage_router)
app.include_router(admin_usage_router)

@app.on_event("startup")
def startup():
    initialize_database()
    with SessionLocal() as db:
        initialize_fingerprint_claims(db)


@app.get("/health")
def health():
    return {"status": "healthy", "service": "datumor-api", "version": "0.1.0"}


@app.post("/api/v1/ingestion/files", status_code=201)
async def upload_file(
    file: UploadFile = File(...),
    project_id: uuid.UUID = Form(...),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    project_query = select(Project).where(Project.project_id == project_id)
    if getattr(user, "role", "customer") not in ("admin", "superadmin"):
        project_query = project_query.where(Project.owner_user_id == user.user_id)
    project = db.scalar(project_query)
    if not project or getattr(project, "status", "active") != "active":
        raise HTTPException(status_code=404, detail="Project not found.")

    check_rate_limit(db, user.user_id, 'file_ingestion')
    media_type = file.content_type
    staged_path = None
    try:
        result = await stage_upload(file)
        staged_path = STAGING_DIR / f'{result["upload_id"]}{result["extension"]}'
        source, duplicate = register_source_with_duplicate_info(
            db, source_id=result["upload_id"], source_type="file",
            source_name=result["original_filename"],
            checksum_sha256=file_sha256(staged_path),
            uri=str(staged_path.resolve()), media_type=media_type,
            size_bytes=result["size_bytes"], project_id=project.project_id,
            metadata={
                "extension": result["extension"],
                "ingestion_status": "staged",
                "format_detection": detect_format(
                    staged_path,
                    original_filename=result["original_filename"],
                    declared_media_type=media_type,
                ),
            },
        )
        if duplicate:
            staged_path.unlink(missing_ok=True)
        if not duplicate:
            record_usage(db, user.user_id, "file_ingestion", 1)
            record_usage(db, user.user_id, "ingestion_bytes", result["size_bytes"])
        db.commit()
        result["duplicate"] = duplicate
        result["canonical_source_id"] = str(source.source_id)
        result["status"] = "duplicate" if duplicate else "staged"
        return {
            "success": True,
            "data": result,
            "source": serialize_source(source),
            "duplicate": duplicate,
            "canonical_source_id": str(source.source_id),
        }
    except UploadValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        if staged_path is not None:
            staged_path.unlink(missing_ok=True)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except HTTPException:
        db.rollback()
        if staged_path is not None:
            staged_path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        _m95_traceback.print_exc()
        db.rollback()
        if staged_path is not None:
            staged_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=500,
            detail="File ingestion or source registration failed.",
        ) from exc



class GitHubIngestionRequest(BaseModel):
    repository_url: HttpUrl
    branch: str | None = None


@app.post("/api/v1/ingestion/github", status_code=201)
def ingest_github(request: GitHubIngestionRequest, project_id: uuid.UUID, user=Depends(get_current_user), db: Session = Depends(get_db)):
    project_query = select(Project).where(Project.project_id == project_id)
    if getattr(user, 'role', 'customer') not in ('admin', 'superadmin'):
        project_query = project_query.where(Project.owner_user_id == user.user_id)
    project = db.scalar(project_query)
    if project is None or getattr(project, 'status', 'active') != 'active':
        raise HTTPException(status_code=404, detail='Project not found.')
    check_rate_limit(db, user.user_id, 'github_ingestion')
    staging_path = None
    try:
        result = ingest_github_repository(str(request.repository_url), request.branch)
        staging_path = Path(result["staging_path"])
        checksum = github_manifest_sha256(staging_path)
        source, duplicate = register_source_with_duplicate_info(
            db, source_id=result["repository_id"], source_type="github",
            source_name=f'{result["owner"]}/{result["repository"]}',
            checksum_sha256=checksum, uri=str(staging_path.resolve()),
            media_type="application/x-directory", size_bytes=(result.get("total_bytes") or result.get("size_bytes") or result.get("file_size") or result.get("size") or 0),
            metadata={
                "repository_url": result["repository_url"], "branch": result["branch"],
                "default_branch": result["default_branch"], "commit_sha": result["commit_sha"],
                "description": result["description"], "stars": result["stars"],
                "license": result["license"], "file_count": result["file_count"],
                "skipped_file_count": result["skipped_file_count"],
            },
            project_id=project_id,
        )
        if duplicate:
            shutil.rmtree(staging_path)
        result["duplicate"] = duplicate
        result["canonical_source_id"] = str(source.source_id)
        result["status"] = "duplicate" if duplicate else "staged"
        if duplicate:
            result["staging_path"] = None
            result["files"] = []
        return {"success": True, "data": result, "source": serialize_source(source),
                "duplicate": duplicate, "canonical_source_id": str(source.source_id)}
    except GitHubIngestionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except HTTPException:
        db.rollback()
        if staging_path is not None:
            staging_path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        db.rollback()
        if staging_path is not None and staging_path.exists():
            shutil.rmtree(staging_path, ignore_errors=True)
        raise HTTPException(status_code=500, detail="GitHub ingestion or source registration failed.") from exc


@app.get("/api/v1/sources")
def list_sources(
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    if limit < 1 or limit > 100 or offset < 0:
        raise HTTPException(status_code=422, detail="Invalid pagination.")

    statement = select(Source)
    if getattr(user, "role", "customer") not in ("admin", "superadmin"):
        visible_project_ids = select(Project.project_id).where(
            Project.owner_user_id == user.user_id
        )
        statement = statement.where(Source.project_id.in_(visible_project_ids))

    records = db.scalars(
        statement.order_by(Source.created_at.desc()).offset(offset).limit(limit)
    ).all()
    return [serialize_source(record) for record in records]

@app.get("/api/v1/sources/{source_id}")
def get_source(
    source_id: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    try:
        parsed_id = uuid.UUID(source_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid source ID.") from exc

    statement = select(Source).where(Source.source_id == parsed_id)
    if getattr(user, "role", "customer") not in ("admin", "superadmin"):
        visible_project_ids = select(Project.project_id).where(
            Project.owner_user_id == user.user_id
        )
        statement = statement.where(Source.project_id.in_(visible_project_ids))

    source = db.scalar(statement)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found.")
    return serialize_source(source)



# DATUMOR_M94_REPORT_MANAGEMENT
# Additive report, download, artifact and immutable snapshot API.
from pathlib import Path as _M94Path
from datetime import datetime as _M94DateTime, timezone as _M94Timezone
import hashlib as _M94Hashlib
import json as _M94Json
import shutil as _M94Shutil
import uuid as _M94Uuid

from fastapi import Depends as _M94Depends, HTTPException as _M94HTTPException
from fastapi.responses import FileResponse as _M94FileResponse
from sqlalchemy import select as _M94Select
from sqlalchemy.orm import Session as _M94Session
from apps.api.app.jobs.job_model import ProcessingJob as _M94ProcessingJob


def _m94_root():
    return _M94Path(__file__).resolve().parents[3]


def _m94_job_context(job_id, db, user):
    try:
        job_uuid = _M94Uuid.UUID(str(job_id))
    except (ValueError, TypeError):
        raise _M94HTTPException(status_code=404, detail="Report not found")

    job = db.scalar(
        _M94Select(_M94ProcessingJob).where(
            _M94ProcessingJob.job_id == str(job_uuid)
        )
    )
    if job is None:
        raise _M94HTTPException(status_code=404, detail="Report not found")

    project_id = getattr(job, "project_id", None)
    if project_id is None:
        raise _M94HTTPException(status_code=404, detail="Report not found")

    project = db.scalar(
        _M94Select(Project).where(Project.project_id == project_id)
    )
    if project is None:
        raise _M94HTTPException(status_code=404, detail="Report not found")

    if not getattr(user, "is_admin", False):
        if str(project.owner_user_id) != str(user.user_id):
            raise _M94HTTPException(status_code=404, detail="Report not found")

    job_dir = _m94_root() / "data" / "jobs" / str(job_uuid)
    report_dir = job_dir / "reports"
    report_json = report_dir / "extraction-report.json"
    report_md = report_dir / "extraction-report.md"
    return job, project, job_dir, report_json, report_md


def _m94_sha256(path):
    digest = _M94Hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()



@app.get("/api/v1/reports")
def m94_list_reports(
    project_id: str | None = None,
    status: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: _M94Session = _M94Depends(get_db),
    user= _M94Depends(get_current_user),
):
    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    statement = _M94Select(_M94ProcessingJob).order_by(
        _M94ProcessingJob.created_at.desc()
    )

    if project_id:
        try:
            project_uuid = _M94Uuid.UUID(project_id)
        except ValueError:
            raise _M94HTTPException(status_code=400, detail="Invalid project_id")

        project = db.scalar(
            _M94Select(Project).where(Project.project_id == project_uuid)
        )
        if project is None or (
            not getattr(user, "is_admin", False)
            and str(project.owner_user_id) != str(user.user_id)
        ):
            raise _M94HTTPException(status_code=404, detail="Project not found")

        statement = statement.where(
            _M94ProcessingJob.project_id == project_uuid
        )
    elif not getattr(user, "is_admin", False):
        visible_projects = _M94Select(Project.project_id).where(
            Project.owner_user_id == user.user_id
        )
        statement = statement.where(
            _M94ProcessingJob.project_id.in_(visible_projects)
        )

    if status:
        statement = statement.where(_M94ProcessingJob.status == status.strip())

    if search and search.strip():
        term = "%" + search.strip().replace("%", r"\%").replace("_", r"\_") + "%"
        statement = statement.where(
            _M94ProcessingJob.name.ilike(term, escape="\\")
        )

    jobs = list(db.scalars(statement).all())
    items = []

    for job in jobs:
        current_job_id = str(job.job_id)
        report_path = (
            _m94_root() / "data" / "jobs" / current_job_id
            / "reports" / "extraction-report.json"
        )
        if not report_path.is_file():
            continue

        markdown_path = report_path.with_suffix(".md")
        items.append({
            "job_id": current_job_id,
            "project_id": str(getattr(job, "project_id", "")),
            "name": str(getattr(job, "name", "")),
            "status": str(getattr(job, "status", "unknown")),
            "created_at": str(getattr(job, "created_at", "")),
            "report_available": True,
            "formats": ["json"] + (["markdown"] if markdown_path.is_file() else []),
        })

    total = len(items)
    return {
        "items": items[offset:offset + limit],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@app.get("/api/v1/reports/{job_id}")
def m94_get_report(
    job_id: str,
    db: _M94Session = _M94Depends(get_db),
    user= _M94Depends(get_current_user),
):
    job, project, job_dir, report_json, report_md = _m94_job_context(job_id, db, user)
    if not report_json.is_file():
        raise _M94HTTPException(status_code=404, detail="Report not available")
    try:
        report = _M94Json.loads(report_json.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise _M94HTTPException(status_code=500, detail="Stored report is unreadable")
    return {
        "job_id": str(job.job_id),
        "project_id": str(project.project_id),
        "job_status": str(getattr(job, "status", "unknown")),
        "report": report,
        "available_downloads": {
            "json": True,
            "markdown": report_md.is_file(),
        },
    }


@app.get("/api/v1/reports/{job_id}/download/{format}")
def m94_download_report(
    job_id: str,
    format: str,
    db: _M94Session = _M94Depends(get_db),
    user= _M94Depends(get_current_user),
):
    job, project, job_dir, report_json, report_md = _m94_job_context(job_id, db, user)
    if format == "json":
        path, media = report_json, "application/json"
    elif format in ("md", "markdown"):
        path, media = report_md, "text/markdown; charset=utf-8"
    else:
        raise _M94HTTPException(status_code=400, detail="Format must be json or markdown")
    if not path.is_file():
        raise _M94HTTPException(status_code=404, detail="Requested report format unavailable")
    return _M94FileResponse(
        path=str(path),
        media_type=media,
        filename=f"datumor-report-{job.job_id}.{ 'json' if format == 'json' else 'md' }",
    )


@app.get("/api/v1/reports/{job_id}/artifacts")
def m94_list_artifacts(
    job_id: str,
    db: _M94Session = _M94Depends(get_db),
    user= _M94Depends(get_current_user),
):
    job, project, job_dir, report_json, report_md = _m94_job_context(job_id, db, user)
    items = []
    for folder_name in ("exports", "artifacts"):
        folder = job_dir / folder_name
        if not folder.is_dir():
            continue
        for path in folder.rglob("*"):
            if path.is_file() and not path.is_symlink():
                items.append({
                    "name": path.name,
                    "relative_path": path.relative_to(job_dir).as_posix(),
                    "size_bytes": path.stat().st_size,
                    "sha256": _m94_sha256(path),
                })
    return {"job_id": str(job.job_id), "artifacts": items}


@app.get("/api/v1/reports/{job_id}/artifacts/download")
def m94_download_artifact(
    job_id: str,
    path: str,
    db: _M94Session = _M94Depends(get_db),
    user= _M94Depends(get_current_user),
):
    job, project, job_dir, report_json, report_md = _m94_job_context(job_id, db, user)
    relative = _M94Path(path)
    if relative.is_absolute() or ".." in relative.parts:
        raise _M94HTTPException(status_code=400, detail="Invalid artifact path")
    if not relative.parts or relative.parts[0] not in ("exports", "artifacts"):
        raise _M94HTTPException(status_code=400, detail="Only generated artifacts can be downloaded")
    candidate = job_dir / relative
    base_candidate = job_dir / relative.parts[0]

    # Reject symlinks in every existing path component before resolution.
    current = job_dir
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise _M94HTTPException(status_code=404, detail="Artifact not found")

    base = base_candidate.resolve()
    target = candidate.resolve()
    if (
        base not in target.parents
        or not target.is_file()
        or not target.is_relative_to(base)
    ):
        raise _M94HTTPException(status_code=404, detail="Artifact not found")
    return _M94FileResponse(path=str(target), filename=target.name)



@app.post("/api/v1/reports/{job_id}/versions", status_code=201)
def m94_create_version(
    job_id: str,
    db: _M94Session = _M94Depends(get_db),
    user= _M94Depends(get_current_user),
):
    job, project, job_dir, report_json, report_md = _m94_job_context(job_id, db, user)
    if not report_json.is_file():
        raise _M94HTTPException(status_code=404, detail="Report not available")

    versions_dir = job_dir / "versions"
    versions_dir.mkdir(parents=True, exist_ok=True)

    existing_numbers = []
    for folder in versions_dir.iterdir():
        if folder.is_dir() and re.fullmatch(r"v[0-9]{6}", folder.name):
            existing_numbers.append(int(folder.name[1:]))

    version_number = max(existing_numbers, default=0) + 1

    # mkdir is atomic. If another request wins the same number,
    # retry with the next number instead of overwriting its snapshot.
    while True:
        version_name = f"v{version_number:06d}"
        destination = versions_dir / version_name
        try:
            destination.mkdir()
            break
        except FileExistsError:
            version_number += 1

    try:
        files = []
        candidates = [report_json]
        if report_md.is_file():
            candidates.append(report_md)

        for folder_name in ("exports", "artifacts"):
            folder = job_dir / folder_name
            if folder.is_dir():
                candidates.extend(
                    p for p in folder.rglob("*")
                    if p.is_file() and not p.is_symlink()
                )

        for original in candidates:
            relative = original.relative_to(job_dir)
            copied = destination / relative
            copied.parent.mkdir(parents=True, exist_ok=True)
            _M94Shutil.copy2(original, copied)
            files.append({
                "path": relative.as_posix(),
                "size_bytes": copied.stat().st_size,
                "sha256": _m94_sha256(copied),
            })

        manifest = {
            "version": version_name,
            "version_number": version_number,
            "job_id": str(job.job_id),
            "project_id": str(project.project_id),
            "created_at": _M94DateTime.now(_M94Timezone.utc).isoformat(),
            "created_by": str(user.user_id),
            "files": files,
        }

        manifest_path = destination / "manifest.json"
        manifest_path.write_text(
            _M94Json.dumps(manifest, indent=2),
            encoding="utf-8",
        )

        return manifest

    except Exception:
        _M94Shutil.rmtree(destination, ignore_errors=True)
        raise


@app.get("/api/v1/reports/{job_id}/versions")
def m94_list_versions(
    job_id: str,
    db: _M94Session = _M94Depends(get_db),
    user= _M94Depends(get_current_user),
):
    job, project, job_dir, report_json, report_md = _m94_job_context(job_id, db, user)
    versions_dir = job_dir / "versions"
    result = []
    if versions_dir.is_dir():
        for folder in sorted(p for p in versions_dir.iterdir() if p.is_dir()):
            manifest_path = folder / "manifest.json"
            if manifest_path.is_file():
                try:
                    result.append(_M94Json.loads(manifest_path.read_text(encoding="utf-8")))
                except (OSError, ValueError):
                    continue
    return {"job_id": str(job.job_id), "versions": result}


@app.get("/api/v1/reports/{job_id}/versions/{version}/manifest")
def m94_get_version_manifest(
    job_id: str,
    version: str,
    db: _M94Session = _M94Depends(get_db),
    user= _M94Depends(get_current_user),
):
    job, project, job_dir, report_json, report_md = _m94_job_context(job_id, db, user)
    if not version.startswith("v") or not version[1:].isdigit():
        raise _M94HTTPException(status_code=400, detail="Invalid version")
    manifest = job_dir / "versions" / version / "manifest.json"
    if not manifest.is_file():
        raise _M94HTTPException(status_code=404, detail="Version not found")
    return _M94Json.loads(manifest.read_text(encoding="utf-8"))


@app.get("/api/v1/reports/{job_id}/versions/compare")
def m94_compare_versions(
    job_id: str,
    first: str,
    second: str,
    db: _M94Session = _M94Depends(get_db),
    user= _M94Depends(get_current_user),
):
    job, project, job_dir, report_json, report_md = _m94_job_context(job_id, db, user)
    versions_dir = job_dir / "versions"
    manifests = []
    for version in (first, second):
        if not version.startswith("v") or not version[1:].isdigit():
            raise _M94HTTPException(status_code=400, detail="Invalid version")
        path = versions_dir / version / "manifest.json"
        if not path.is_file():
            raise _M94HTTPException(status_code=404, detail=f"Version {version} not found")
        manifests.append(_M94Json.loads(path.read_text(encoding="utf-8")))
    left = {item["path"]: item for item in manifests[0]["files"]}
    right = {item["path"]: item for item in manifests[1]["files"]}
    names = sorted(set(left) | set(right))
    changes = []
    for name in names:
        if name not in left:
            status = "added"
        elif name not in right:
            status = "removed"
        elif left[name]["sha256"] != right[name]["sha256"]:
            status = "changed"
        else:
            status = "unchanged"
        changes.append({"path": name, "status": status})
    return {"job_id": str(job.job_id), "first": first, "second": second, "changes": changes}
