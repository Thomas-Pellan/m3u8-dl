import asyncio
import json
import re
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from ..services.browser import BrowserService
from ..services.title_scraper import TitleScraperService
from .service import JobConflictError, JobNotFoundError, JobService, ScheduledLimitError

router = APIRouter()


def _get_service(request: Request) -> JobService:
    return request.app.state.job_service


ServiceDep = Annotated[JobService, Depends(_get_service)]


# ── SSE ───────────────────────────────────────────────────────────────────────

@router.get("/events")
async def sse_events(request: Request, service: ServiceDep) -> EventSourceResponse:
    queue = service.subscribe()

    async def stream():
        try:
            jobs = await service.get_all_jobs()
            yield {"event": "jobs", "data": json.dumps(jobs)}
            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=25)
                    yield {"event": "jobs", "data": data}
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": ""}
        finally:
            service.unsubscribe(queue)

    return EventSourceResponse(stream())


# ── title scraping ────────────────────────────────────────────────────────────

@router.get("/suggest-names")
async def suggest_names(url: str) -> JSONResponse:
    scraper = TitleScraperService()

    async def _fetch() -> list[str]:
        browser_svc = BrowserService(headless=True)
        async with browser_svc.launch() as b:
            page = await b.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=15_000)
            candidates = await scraper.scrape_candidates(page)
            filenames = [scraper.to_filename(c) for c in candidates]
            filenames.sort(key=lambda f: 0 if re.search(r"(19|20)\d{2}", f) else 1)
            return filenames[:5]

    try:
        filenames = await asyncio.wait_for(_fetch(), timeout=25.0)
        return JSONResponse({"candidates": filenames})
    except Exception:
        return JSONResponse({"candidates": []})


# ── jobs ──────────────────────────────────────────────────────────────────────

@router.get("/jobs")
async def list_jobs(service: ServiceDep) -> JSONResponse:
    return JSONResponse(await service.get_all_jobs())


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, service: ServiceDep) -> JSONResponse:
    job = await service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return JSONResponse(job)


@router.post("/capture")
async def start_capture(
    service: ServiceDep,
    background_tasks: BackgroundTasks,
    url: str = Form(...),
    output_name: str = Form(...),
    mode: str = Form("auto"),
    quality: str = Form("best"),
    parallel: int = Form(4),
    scheduled_at: str | None = Form(None),
) -> JSONResponse:
    output_name = output_name.strip()
    if not output_name:
        raise HTTPException(status_code=422, detail="output_name is required")

    try:
        job_id, fire_at = await service.create_job(
            url=url,
            output_name=output_name,
            mode=mode,
            quality=quality,
            parallel=parallel,
            scheduled_at=scheduled_at or None,
        )
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid scheduled_at format")
    except ScheduledLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc))

    if not fire_at:
        background_tasks.add_task(
            service.run_job, job_id, url, output_name, mode, quality, parallel
        )

    return JSONResponse({"job_id": job_id})


@router.delete("/jobs/{job_id}", status_code=204)
async def delete_job(job_id: str, service: ServiceDep) -> None:
    try:
        await service.delete_job(job_id)
    except JobNotFoundError:
        raise HTTPException(status_code=404, detail="job not found")
    except JobConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/jobs/{job_id}/retry")
async def retry_job(
    job_id: str,
    service: ServiceDep,
    background_tasks: BackgroundTasks,
) -> JSONResponse:
    try:
        job = await service.retry_job(job_id)
    except JobNotFoundError:
        raise HTTPException(status_code=404, detail="job not found")
    except JobConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    background_tasks.add_task(
        service.run_job,
        job_id, job["url"], job["output_name"],
        job["mode"], job["quality"], job["parallel"],
    )
    return JSONResponse({"job_id": job_id})


@router.patch("/jobs/{job_id}/reschedule")
async def reschedule_job(
    job_id: str,
    service: ServiceDep,
    scheduled_at: str = Form(...),
) -> JSONResponse:
    try:
        await service.reschedule_job(job_id, scheduled_at)
    except JobNotFoundError:
        raise HTTPException(status_code=404, detail="job not found")
    except JobConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid scheduled_at format")

    return JSONResponse({"job_id": job_id})
