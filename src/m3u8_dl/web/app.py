import asyncio
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ..config import AppConfig
from ..services.browser import BrowserService
from ..services.capture import CaptureService
from ..services.title_scraper import TitleScraperService

app = FastAPI(title="m3u8-dl")

_HERE = Path(__file__).parent
app.mount("/static", StaticFiles(directory=_HERE / "static"), name="static")
_TEMPLATE = (_HERE / "templates" / "index.html").read_text()

_jobs: dict[str, dict[str, Any]] = {}
_scheduled_tasks: dict[str, asyncio.Task] = {}
_MAX_SCHEDULED = 10
_PROGRESS_RE = re.compile(r"\((\d+)%\)")


async def _run_job(
    job_id: str,
    url: str,
    output_name: str,
    mode: str,
    quality: str,
    parallel: int,
) -> None:
    _jobs[job_id]["status"] = "running"

    def _log(msg: str) -> None:
        _jobs[job_id]["logs"].append(msg)
        m = _PROGRESS_RE.search(msg)
        if m:
            _jobs[job_id]["progress"] = int(m.group(1))

    try:
        config = AppConfig(
            capture_mode=mode,
            preferred_quality=quality,
            max_parallel_downloads=parallel,
            headless=True,
        )
        service = CaptureService(config, log_fn=_log)
        output = await service.run(output_name=output_name, start_url=url)
        _jobs[job_id].update({"status": "done", "output": output.name})
    except Exception as exc:
        _jobs[job_id].update({"status": "error", "error": str(exc)})


async def _schedule_job(
    job_id: str,
    fire_at: datetime,
    url: str,
    output_name: str,
    mode: str,
    quality: str,
    parallel: int,
) -> None:
    try:
        delay = (fire_at - datetime.now()).total_seconds()
        if delay > 0:
            await asyncio.sleep(delay)
        # Only fire if this is still the active task for this job (guards against reschedule races)
        if (
            job_id in _jobs
            and _jobs[job_id].get("status") == "scheduled"
            and _scheduled_tasks.get(job_id) is asyncio.current_task()
        ):
            await _run_job(job_id, url, output_name, mode, quality, parallel)
    except asyncio.CancelledError:
        pass
    finally:
        if _scheduled_tasks.get(job_id) is asyncio.current_task():
            _scheduled_tasks.pop(job_id, None)


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return _TEMPLATE


@app.get("/suggest-names")
async def suggest_names(url: str) -> JSONResponse:
    scraper = TitleScraperService()

    async def _fetch() -> list[str]:
        browser_svc = BrowserService(headless=True)
        async with browser_svc.launch() as b:
            page = await b.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=15_000)
            candidates = await scraper.scrape_candidates(page)
            filenames = [scraper.to_filename(c) for c in candidates]
            filenames.sort(key=lambda f: 0 if re.search(r'(19|20)\d{2}', f) else 1)
            return filenames[:5]

    try:
        filenames = await asyncio.wait_for(_fetch(), timeout=25.0)
        return JSONResponse({"candidates": filenames})
    except Exception:
        return JSONResponse({"candidates": []})


@app.post("/capture")
async def start_capture(
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

    scheduled_at = scheduled_at or None  # normalise empty string
    fire_at: datetime | None = None

    if scheduled_at:
        try:
            fire_at = datetime.fromisoformat(scheduled_at)
        except ValueError:
            raise HTTPException(status_code=422, detail="invalid scheduled_at format")
        sched_count = sum(1 for j in _jobs.values() if j["status"] == "scheduled")
        if sched_count >= _MAX_SCHEDULED:
            raise HTTPException(status_code=429, detail=f"Scheduled job limit reached (max {_MAX_SCHEDULED})")

    job_id = uuid.uuid4().hex[:8]
    _jobs[job_id] = {
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
    }

    if fire_at:
        _scheduled_tasks[job_id] = asyncio.create_task(
            _schedule_job(job_id, fire_at, url, output_name, mode, quality, parallel)
        )
    else:
        background_tasks.add_task(_run_job, job_id, url, output_name, mode, quality, parallel)

    return JSONResponse({"job_id": job_id})


@app.get("/jobs")
async def list_jobs() -> dict:
    return _jobs


@app.get("/jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="job not found")
    return _jobs[job_id]


@app.delete("/jobs/{job_id}", status_code=204)
async def clear_job(job_id: str) -> None:
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="job not found")
    status = _jobs[job_id]["status"]
    if status == "scheduled":
        task = _scheduled_tasks.pop(job_id, None)
        if task:
            task.cancel()
        del _jobs[job_id]
    elif status == "error":
        del _jobs[job_id]
    else:
        raise HTTPException(status_code=409, detail="job cannot be deleted in its current state")


@app.post("/jobs/{job_id}/retry")
async def retry_job(job_id: str, background_tasks: BackgroundTasks) -> JSONResponse:
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="job not found")
    job = _jobs[job_id]
    if job["status"] != "error":
        raise HTTPException(status_code=409, detail="job is not in error state")

    _jobs[job_id].update({
        "status": "pending",
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "logs": [],
        "progress": None,
        "error": None,
        "output": None,
    })
    background_tasks.add_task(
        _run_job,
        job_id,
        job["url"],
        job["output_name"],
        job["mode"],
        job.get("quality", "best"),
        job.get("parallel", 4),
    )
    return JSONResponse({"job_id": job_id})


@app.patch("/jobs/{job_id}/reschedule")
async def reschedule_job(job_id: str, scheduled_at: str = Form(...)) -> JSONResponse:
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="job not found")
    if _jobs[job_id]["status"] != "scheduled":
        raise HTTPException(status_code=409, detail="job is not in scheduled state")
    try:
        fire_at = datetime.fromisoformat(scheduled_at)
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid scheduled_at format")

    old_task = _scheduled_tasks.pop(job_id, None)
    if old_task:
        old_task.cancel()

    _jobs[job_id]["scheduled_at"] = scheduled_at
    _scheduled_tasks[job_id] = asyncio.create_task(
        _schedule_job(job_id, fire_at, _jobs[job_id]["url"], _jobs[job_id]["output_name"],
                      _jobs[job_id]["mode"], _jobs[job_id]["quality"], _jobs[job_id]["parallel"])
    )
    return JSONResponse({"job_id": job_id})


def main() -> None:
    import uvicorn
    uvicorn.run("m3u8_dl.web.app:app", host="0.0.0.0", port=8080, reload=False)
