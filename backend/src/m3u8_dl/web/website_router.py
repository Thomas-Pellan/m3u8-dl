import asyncio
import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from .browse_session_service import BrowseSessionService, SessionConflictError
from .website_service import WebsiteNotFoundError, WebsiteService

router = APIRouter()


def _get_service(request: Request) -> WebsiteService:
    return request.app.state.website_service


def _get_session_service(request: Request) -> BrowseSessionService:
    return request.app.state.browse_session_service


WebsiteDep = Annotated[WebsiteService, Depends(_get_service)]
SessionDep = Annotated[BrowseSessionService, Depends(_get_session_service)]


# ── SSE ───────────────────────────────────────────────────────────────────────

@router.get("/website-events")
async def website_events(request: Request, service: WebsiteDep) -> EventSourceResponse:
    queue = service.subscribe()

    async def stream():
        try:
            websites = await service.get_all()
            yield {"event": "websites", "data": json.dumps(websites)}
            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=25)
                    yield {"event": "websites", "data": data}
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": ""}
        finally:
            service.unsubscribe(queue)

    return EventSourceResponse(stream())


# ── REST ──────────────────────────────────────────────────────────────────────

@router.get("/websites")
async def list_websites(service: WebsiteDep) -> JSONResponse:
    return JSONResponse(await service.get_all())


class RatingBody(BaseModel):
    rating: int


class WorkingBody(BaseModel):
    working: bool


@router.delete("/websites/flush")
async def flush_not_working(service: WebsiteDep) -> JSONResponse:
    count = await service.flush_not_working()
    return JSONResponse({"deleted": count})


@router.patch("/websites/{website_id}/rating")
async def update_rating(
    website_id: int, body: RatingBody, service: WebsiteDep
) -> JSONResponse:
    if body.rating < 0 or body.rating > 5:
        raise HTTPException(status_code=422, detail="rating must be 0–5")
    try:
        await service.update_rating(website_id, body.rating)
    except WebsiteNotFoundError:
        raise HTTPException(status_code=404, detail="website not found")
    return JSONResponse({"ok": True})


@router.patch("/websites/{website_id}/working")
async def update_working(
    website_id: int, body: WorkingBody, service: WebsiteDep
) -> JSONResponse:
    try:
        await service.set_working(website_id, body.working)
    except WebsiteNotFoundError:
        raise HTTPException(status_code=404, detail="website not found")
    return JSONResponse({"ok": True})


@router.delete("/websites/{website_id}/cdns")
async def flush_website_cdns(website_id: int, service: WebsiteDep) -> JSONResponse:
    try:
        count = await service.flush_cdns(website_id)
    except WebsiteNotFoundError:
        raise HTTPException(status_code=404, detail="website not found")
    return JSONResponse({"flushed": count})


@router.delete("/websites/{website_id}", status_code=204)
async def delete_website(website_id: int, service: WebsiteDep) -> None:
    await service.delete(website_id)


@router.post("/websites/{website_id}/open-session")
async def open_captured_session(
    website_id: int,
    service: WebsiteDep,
    session_service: SessionDep,
) -> JSONResponse:
    website = await service.get(website_id)
    if website is None:
        raise HTTPException(status_code=404, detail="website not found")

    website_url = website["url"]
    active = await session_service._repo.get_active()

    if active is None:
        try:
            session_id = await session_service.create_session(website_url)
        except SessionConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        return JSONResponse({"action": "created", "session_id": session_id})

    active_dls: list[dict[str, Any]] = [
        d for d in active.get("downloads", [])
        if d["status"] in ("running", "assembling")
    ]

    if active_dls:
        await session_service.close_session(active["id"])
        return JSONResponse({
            "action": "deferred",
            "message": (
                "Downloads are still in progress — the current session will close "
                "automatically when they finish. Come back to start a new session then."
            ),
        })

    await session_service.force_close_session(active["id"])
    try:
        session_id = await session_service.create_session(website_url)
    except SessionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return JSONResponse({"action": "created", "session_id": session_id})
