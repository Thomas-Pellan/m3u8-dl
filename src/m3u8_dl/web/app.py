import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ..config import AppConfig
from ..services.capture import CaptureService

app = FastAPI(title="m3u8-dl")

_HERE = Path(__file__).parent
app.mount("/static", StaticFiles(directory=_HERE / "static"), name="static")
_TEMPLATE = (_HERE / "templates" / "index.html").read_text()

_jobs: dict[str, dict[str, Any]] = {}
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


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return _TEMPLATE


@app.post("/capture")
async def start_capture(
    background_tasks: BackgroundTasks,
    url: str = Form(...),
    output_name: str = Form(...),
    mode: str = Form("auto"),
    quality: str = Form("best"),
    parallel: int = Form(4),
) -> JSONResponse:
    output_name = output_name.strip()
    if not output_name:
        raise HTTPException(status_code=422, detail="output_name is required")

    job_id = uuid.uuid4().hex[:8]
    _jobs[job_id] = {
        "id": job_id,
        "status": "pending",
        "url": url,
        "output_name": output_name,
        "mode": mode,
        "quality": quality,
        "parallel": parallel,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "logs": [],
        "progress": None,
    }
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
    if _jobs[job_id]["status"] != "error":
        raise HTTPException(status_code=409, detail="job is not in error state")
    del _jobs[job_id]


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


def main() -> None:
    import uvicorn
    uvicorn.run("m3u8_dl.web.app:app", host="0.0.0.0", port=8080, reload=False)
