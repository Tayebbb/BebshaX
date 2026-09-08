"""In-memory async job registry (dev-scale) — the interview batch-run
pattern generalized: a POST starts a background task and returns 202 with a
job id; the UI polls the matching GET. A server restart loses job STATUS,
never data — runners persist their real output (rows, reports) as they
complete, exactly like batch interviews persist conversations.

Not a queue on purpose (R10): no broker, no workers, no persistence layer —
`asyncio.create_task` with GC-safe strong refs on `app.state`.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

from bebshax.api.errors import APIError
from bebshax.utils.explicit_failures import ExplicitFailure

logger = logging.getLogger(__name__)

_MAX_JOBS = 50  # evict oldest beyond this — polling clients read fast
# Each running job is minutes of free-tier LLM spend; one caller may not queue
# up more than this many at once.
MAX_RUNNING_JOBS_PER_USER = 3


def _registry(app) -> dict[str, dict[str, Any]]:
    reg = getattr(app.state, "async_jobs", None)
    if reg is None:
        reg = {}
        app.state.async_jobs = reg
        app.state.async_job_tasks = set()
    return reg


def running_jobs_for_user(app, user_id: Optional[str]) -> int:
    if user_id is None:
        return 0
    return sum(
        1
        for job in _registry(app).values()
        if job["status"] == "running" and job.get("user_id") == user_id
    )


def start_job(
    app,
    *,
    kind: str,
    scope_id: str,
    runner: Callable[[dict[str, Any]], Awaitable[None]],
    user_id: Optional[str] = None,
    user_safe_exceptions: tuple[type[BaseException], ...] = (),
) -> dict[str, Any]:
    """Register a job and run `runner(job)` in the background.

    The runner mutates the job dict (typically setting `job["result"]`).
    Runner returns → status "completed"; runner raises → status "failed".
    `ValueError` and any type in `user_safe_exceptions` (the caller's honest
    domain failures, e.g. ContextWindowExceeded — R2/R6) pass their message
    through to `job["error"]`; anything else is redacted to the class name
    (full traceback goes to the log, never to the client).

    Raises ``APIError(429, error_code="too_many_jobs")`` when ``user_id``
    already has ``MAX_RUNNING_JOBS_PER_USER`` jobs running.
    """
    registry = _registry(app)
    if running_jobs_for_user(app, user_id) >= MAX_RUNNING_JOBS_PER_USER:
        raise APIError(
            429,
            f"You already have {MAX_RUNNING_JOBS_PER_USER} background jobs running — "
            "wait for one to finish before starting another.",
            error_code="too_many_jobs",
            extra={"max_running_jobs": MAX_RUNNING_JOBS_PER_USER},
        )
    job: dict[str, Any] = {
        "job_id": f"job_{uuid.uuid4().hex[:12]}",
        "kind": kind,
        "scope_id": scope_id,
        "user_id": user_id,
        "status": "running",
        "result": None,
        "error": None,
        "error_code": None,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
    }
    registry[job["job_id"]] = job
    # Evict terminated jobs first — a still-running job must stay pollable
    # (evicting it would 404 with a misleading "restart" hint while the task
    # keeps running). Oldest-running goes only when everything is running.
    while len(registry) > _MAX_JOBS:
        evictable = next(
            (jid for jid, j in registry.items() if j["status"] != "running"),
            next(iter(registry)),
        )
        registry.pop(evictable)

    async def _run() -> None:
        try:
            await runner(job)
            job["status"] = "completed"
        except asyncio.CancelledError:
            # Shutdown/cancellation — never leave a job claiming "running".
            job["status"] = "failed"
            job["error"] = "cancelled (server shutting down)"
            raise
        except ExplicitFailure as exc:
            # "The AI could not do this" (R2) — always user-facing, with its code.
            job["status"] = "failed"
            job["error"] = exc.detail
            job["error_code"] = exc.error_code
            logger.warning("%s job %s refused: %s", kind, job["job_id"], exc.error_code)
        except (ValueError, *user_safe_exceptions) as exc:
            # Input/state/domain problems are user-actionable — surface them.
            job["status"] = "failed"
            job["error"] = str(exc)
            logger.warning("%s job %s failed: %s", kind, job["job_id"], exc)
        except Exception as exc:
            job["status"] = "failed"
            job["error"] = f"{exc.__class__.__name__}: {kind} failed"
            logger.warning("%s job %s crashed", kind, job["job_id"], exc_info=True)
        finally:
            job["finished_at"] = datetime.now(timezone.utc).isoformat()

    task = asyncio.create_task(_run())
    app.state.async_job_tasks.add(task)
    task.add_done_callback(app.state.async_job_tasks.discard)
    return job


def get_job(app, job_id: str, *, kind: str, scope_id: str) -> Optional[dict[str, Any]]:
    """Look up a job, bound to its kind AND scope so a job id can never be
    read through another study's (or another feature's) poll endpoint."""
    job = _registry(app).get(job_id)
    if not job or job["kind"] != kind or job["scope_id"] != scope_id:
        return None
    return job
