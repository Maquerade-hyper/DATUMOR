import argparse

from apps.worker.celery_app import celery_app
from apps.worker.recovery import detect_stale_jobs
from apps.api.app.database import SessionLocal


TASK_NAME = "datumor.process_job"
DEFAULT_BATCH_SIZE = 25
MAX_BATCH_SIZE = 100


def dispatch_stale_jobs(dry_run=True, limit=DEFAULT_BATCH_SIZE, job_ids=None):
    if not 1 <= limit <= MAX_BATCH_SIZE:
        raise ValueError(f"limit must be between 1 and {MAX_BATCH_SIZE}")

    with SessionLocal() as db:
        stale_jobs = detect_stale_jobs(db)

    if job_ids is not None:
        allowed_ids = set(job_ids)
        stale_jobs = [
            item for item in stale_jobs
            if item["job_id"] in allowed_ids
        ]

    selected = stale_jobs[:limit]
    results = []

    for item in selected:
        job_id = item["job_id"]

        if dry_run:
            results.append({
                "job_id": job_id,
                "status": "would_dispatch",
                "reason": item["reason"],
            })
            continue

        try:
            async_result = celery_app.send_task(
                TASK_NAME,
                args=[job_id],
            )
            results.append({
                "job_id": job_id,
                "status": "dispatched",
                "celery_task_id": async_result.id,
                "reason": item["reason"],
            })
        except Exception as exc:
            results.append({
                "job_id": job_id,
                "status": "dispatch_failed",
                "error": f"{type(exc).__name__}: {exc}"[:1000],
                "reason": item["reason"],
            })

    return {
        "dry_run": dry_run,
        "stale_count": len(stale_jobs),
        "selected_count": len(selected),
        "remaining_count": max(0, len(stale_jobs) - len(selected)),
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(
        description="DATUMOR bounded stale-job recovery dispatcher"
    )
    parser.add_argument(
        "--dispatch",
        action="store_true",
        help="Actually enqueue stale jobs. Default is dry-run.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help="Maximum jobs to dispatch (1-100).",
    )
    args = parser.parse_args()

    result = dispatch_stale_jobs(
        dry_run=not args.dispatch,
        limit=args.limit,
    )

    print("DATUMOR RECOVERY DISPATCH")
    print("Mode:", "DISPATCH" if args.dispatch else "DRY RUN")
    print("Stale jobs:", result["stale_count"])
    print("Selected:", result["selected_count"])
    print("Remaining:", result["remaining_count"])

    for item in result["results"]:
        print(item)

    print("H6.3.3 DISPATCHER RUN COMPLETE")


if __name__ == "__main__":
    main()
