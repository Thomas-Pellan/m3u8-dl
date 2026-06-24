import asyncio
import json
import re
import uuid
from collections.abc import Callable, Coroutine
from datetime import datetime, timezone
from typing import Any

from ..config import AppConfig
from ..services.capture import CaptureService
from .repository import JobRepository

_MAX_SCHEDULED = 10
_PROGRESS_RE = re.compile(r"\((\d+)%\)")

_OnDownload = Callable[[str, str, "str | None"], Coroutine[Any, Any, None]]


class JobService:
    def __init__(self, repo: JobRepository, on_download: _OnDownload | None = None) -> None:
        self._repo = repo
        self._on_download = on_download
        self._subscribers: list[asyncio.Queue[str]] = []
        self._scheduled_tasks: dict[str, asyncio.Task] = {}

    async def init(self) -> None:
        await self._repo.init()
        await self._repo.mark_interrupted()
        await self._restore_scheduled()

    async def cleanup(self) -> None:
        for task in list(self._scheduled_tasks.values()):
            task.cancel()

    # ── SSE ──────────────────────────────────────────────────────────────────

    def subscribe(self) -> asyncio.Queue[str]:
        q: asyncio.Queue[str] = asyncio.Queue()
        self._subscribers.append(q)
        return q

    def unsubscribe(self, queue: asyncio.Queue[str]) -> None:
        try:
            self._subscribers.remove(queue)
        except ValueError:
            pass

    async def broadcast(self) -> None:
        jobs = await self._repo.get_all()
        payload = json.dumps(jobs)
        for q in list(self._subscribers):
            q.put_nowait(payload)

    # ── job execution ─────────────────────────────────────────────────────────

    async def run_job(
        self,
        job_id: str,
        url: str,
        output_name: str,
        mode: str,
        quality: str,
        parallel: int,
    ) -> None:
        await self._repo.update(job_id, status="running")
        await self.broadcast()

        log_queue: asyncio.Queue[str | None] = asyncio.Queue()

        def _log(msg: str) -> None:
            log_queue.put_nowait(msg)

        async def _drain() -> None:
            logs: list[str] = []
            progress: int | None = None
            while True:
                msg = await log_queue.get()
                if msg is None:
                    break
                logs.append(msg)
                m = _PROGRESS_RE.search(msg)
                if m:
                    progress = int(m.group(1))
                updates: dict[str, Any] = {"logs": logs}
                if progress is not None:
                    updates["progress"] = progress
                await self._repo.update(job_id, **updates)
                await self.broadcast()

        drain_task = asyncio.create_task(_drain())
        try:
            config = AppConfig(
                capture_mode=mode,
                preferred_quality=quality,
                max_parallel_downloads=parallel,
                headless=True,
            )
            service = CaptureService(config, log_fn=_log)
            output = await service.run(output_name=output_name, start_url=url)
            await self._repo.update(job_id, status="done", output=output.name)
        except Exception as exc:
            await self._repo.update(job_id, status="error", error=str(exc))
        finally:
            log_queue.put_nowait(None)
            try:
                await drain_task
            except Exception:
                pass
            await self.broadcast()

    # ── scheduling ────────────────────────────────────────────────────────────

    async def _schedule_job(
        self,
        job_id: str,
        fire_at: datetime,
        url: str,
        output_name: str,
        mode: str,
        quality: str,
        parallel: int,
    ) -> None:
        try:
            delay = (fire_at - datetime.now(timezone.utc)).total_seconds()
            if delay > 0:
                await asyncio.sleep(delay)
            job = await self._repo.get(job_id)
            if job and job["status"] == "scheduled":
                await self.run_job(job_id, url, output_name, mode, quality, parallel)
        except asyncio.CancelledError:
            pass
        finally:
            self._scheduled_tasks.pop(job_id, None)

    async def _restore_scheduled(self) -> None:
        for job in await self._repo.get_all():
            if job["status"] != "scheduled" or not job.get("scheduled_at"):
                continue
            try:
                fire_at = _parse_fire_at(job["scheduled_at"])
                if fire_at > datetime.now(timezone.utc):
                    self._scheduled_tasks[job["id"]] = asyncio.create_task(
                        self._schedule_job(
                            job["id"], fire_at,
                            job["url"], job["output_name"],
                            job["mode"], job["quality"], job["parallel"],
                        )
                    )
                else:
                    await self._repo.update(
                        job["id"],
                        status="error",
                        error="Missed scheduled time (server was restarted)",
                    )
            except Exception:
                pass

    # ── public operations ─────────────────────────────────────────────────────

    async def get_all_jobs(self) -> list[dict[str, Any]]:
        return await self._repo.get_all()

    async def get_job(self, job_id: str) -> dict[str, Any] | None:
        return await self._repo.get(job_id)

    async def create_job(
        self,
        url: str,
        output_name: str,
        mode: str,
        quality: str,
        parallel: int,
        scheduled_at: str | None,
    ) -> tuple[str, datetime | None]:
        fire_at: datetime | None = None
        if scheduled_at:
            fire_at = _parse_fire_at(scheduled_at)
            sched_count = await self._repo.count_by_status("scheduled")
            if sched_count >= _MAX_SCHEDULED:
                raise ScheduledLimitError(_MAX_SCHEDULED)

        job_id = uuid.uuid4().hex[:8]
        job: dict[str, Any] = {
            "id": job_id,
            "status": "scheduled" if fire_at else "pending",
            "url": url,
            "output_name": output_name,
            "mode": mode,
            "quality": quality,
            "parallel": parallel,
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "scheduled_at": scheduled_at,
            "logs": [],
            "progress": None,
            "error": None,
            "output": None,
        }
        await self._repo.insert(job)
        await self.broadcast()

        if self._on_download:
            asyncio.create_task(self._on_download(url, "simple", None))

        if fire_at:
            self._scheduled_tasks[job_id] = asyncio.create_task(
                self._schedule_job(job_id, fire_at, url, output_name, mode, quality, parallel)
            )

        return job_id, fire_at

    async def delete_job(self, job_id: str) -> None:
        job = await self._repo.get(job_id)
        if job is None:
            raise JobNotFoundError(job_id)
        status = job["status"]
        if status == "scheduled":
            task = self._scheduled_tasks.pop(job_id, None)
            if task:
                task.cancel()
            await self._repo.delete(job_id)
        elif status in ("error", "done"):
            await self._repo.delete(job_id)
        else:
            raise JobConflictError("job cannot be deleted in its current state")
        await self.broadcast()

    async def retry_job(self, job_id: str) -> None:
        job = await self._repo.get(job_id)
        if job is None:
            raise JobNotFoundError(job_id)
        if job["status"] != "error":
            raise JobConflictError("job is not in error state")
        await self._repo.update(
            job_id,
            status="pending",
            started_at=datetime.now().isoformat(timespec="seconds"),
            logs=[],
            progress=None,
            error=None,
            output=None,
        )
        await self.broadcast()
        return job

    async def reschedule_job(self, job_id: str, scheduled_at: str) -> None:
        job = await self._repo.get(job_id)
        if job is None:
            raise JobNotFoundError(job_id)
        if job["status"] != "scheduled":
            raise JobConflictError("job is not in scheduled state")

        fire_at = _parse_fire_at(scheduled_at)
        old_task = self._scheduled_tasks.pop(job_id, None)
        if old_task:
            old_task.cancel()

        await self._repo.update(job_id, scheduled_at=scheduled_at)
        await self.broadcast()
        self._scheduled_tasks[job_id] = asyncio.create_task(
            self._schedule_job(
                job_id, fire_at,
                job["url"], job["output_name"],
                job["mode"], job["quality"], job["parallel"],
            )
        )


# ── domain errors ─────────────────────────────────────────────────────────────

class JobNotFoundError(Exception):
    def __init__(self, job_id: str) -> None:
        super().__init__(f"job {job_id!r} not found")


class JobConflictError(Exception):
    pass


class ScheduledLimitError(Exception):
    def __init__(self, limit: int) -> None:
        super().__init__(f"Scheduled job limit reached (max {limit})")
        self.limit = limit


# ── helpers ───────────────────────────────────────────────────────────────────

def _parse_fire_at(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt