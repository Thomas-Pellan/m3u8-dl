import asyncio
import json
from typing import Annotated, Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from .browse_session_service import (
    BrowseSessionService,
    SessionConflictError,
    SessionNotFoundError,
)
from .website_service import WebsiteService

router = APIRouter()


def _get_service(request: Request) -> BrowseSessionService:
    return request.app.state.browse_session_service


def _get_website_service(request: Request) -> WebsiteService:
    return request.app.state.website_service


SessionDep = Annotated[BrowseSessionService, Depends(_get_service)]
WebsiteServiceDep = Annotated[WebsiteService, Depends(_get_website_service)]


def _extract_origin(url: str) -> str | None:
    try:
        p = urlparse(url)
        if p.scheme and p.netloc:
            return f"{p.scheme}://{p.netloc}"
    except Exception:
        pass
    return None


# ── SSE: session list ─────────────────────────────────────────────────────────

@router.get("/session-events")
async def session_events(request: Request, service: SessionDep) -> EventSourceResponse:
    queue = service.subscribe_list()

    async def stream():
        try:
            sessions = await service.get_all_sessions()
            yield {"event": "sessions", "data": json.dumps(sessions)}
            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=25)
                    yield {"event": "sessions", "data": data}
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": ""}
        finally:
            service.unsubscribe_list(queue)

    return EventSourceResponse(stream())


# ── SSE: live screenshots ─────────────────────────────────────────────────────

@router.get("/sessions/{session_id}/screen")
async def session_screen(
    session_id: str, request: Request, service: SessionDep
) -> EventSourceResponse:
    queue = service.subscribe_screen(session_id)

    async def stream():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=5)
                    yield {"event": "screenshot", "data": data}
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": ""}
        finally:
            service.unsubscribe_screen(session_id, queue)

    return EventSourceResponse(stream())


# ── REST ──────────────────────────────────────────────────────────────────────

@router.get("/sessions")
async def list_sessions(service: SessionDep) -> JSONResponse:
    return JSONResponse(await service.get_all_sessions())


@router.post("/sessions", status_code=201)
async def create_session(
    service: SessionDep,
    url: str = Form(...),
) -> JSONResponse:
    try:
        session_id = await service.create_session(url)
    except SessionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return JSONResponse({"session_id": session_id})


@router.delete("/sessions/profile", status_code=204)
async def flush_profile(service: SessionDep) -> None:
    service.flush_profile()


@router.delete("/sessions/{session_id}", status_code=204)
async def close_session(session_id: str, service: SessionDep) -> None:
    try:
        await service.close_session(session_id)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail="session not found")


@router.delete("/sessions/{session_id}/force", status_code=204)
async def force_close_session(session_id: str, service: SessionDep) -> None:
    try:
        await service.force_close_session(session_id)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail="session not found")


@router.delete("/sessions/{session_id}/delete", status_code=204)
async def delete_session(session_id: str, service: SessionDep) -> None:
    try:
        await service.delete_session(session_id)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail="session not found")
    except SessionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.get("/sessions/{session_id}/page-titles")
async def get_page_titles(session_id: str, service: SessionDep) -> JSONResponse:
    try:
        titles = await service.get_page_titles(session_id)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail="session not found or not active")
    return JSONResponse({"titles": titles})


@router.delete("/sessions/{session_id}/candidates", status_code=204)
async def clear_candidates(session_id: str, service: SessionDep) -> None:
    try:
        await service.clear_candidates(session_id)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail="session not found")


@router.post("/sessions/{session_id}/download", status_code=202)
async def start_session_download(
    session_id: str, request: Request, service: SessionDep
) -> JSONResponse:
    body: dict[str, Any] = await request.json()
    candidate_url = body.get("url", "")
    output_name = body.get("output_name", "")
    if not candidate_url or not output_name:
        raise HTTPException(status_code=422, detail="url and output_name are required")
    try:
        dl_id = await service.start_download(
            session_id,
            candidate_url=candidate_url,
            output_name=output_name,
            quality=body.get("quality", "best"),
            parallel=int(body.get("parallel", 4)),
        )
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail="session not found or not active")
    return JSONResponse({"dl_id": dl_id})


@router.post("/sessions/{session_id}/action")
async def send_action(
    session_id: str, request: Request, service: SessionDep
) -> JSONResponse:
    body: dict[str, Any] = await request.json()
    try:
        await service.send_action(session_id, body)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail="session not found")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return JSONResponse({"ok": True})


class ConfirmBody(BaseModel):
    ok: bool
    delete_file: bool = False


@router.post("/sessions/{session_id}/downloads/{dl_id}/confirm")
async def confirm_download(
    session_id: str,
    dl_id: str,
    body: ConfirmBody,
    service: SessionDep,
    website_service: WebsiteServiceDep,
) -> JSONResponse:
    session = await service.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")

    download = next((d for d in session.get("downloads", []) if d["id"] == dl_id), None)
    if download is None:
        raise HTTPException(status_code=404, detail="download not found")

    if not body.ok:
        cdn_origin = _extract_origin(download.get("url", ""))
        website_origin = _extract_origin(session.get("url", ""))
        if cdn_origin and website_origin:
            await website_service.remove_cdn_for_website_origin(website_origin, cdn_origin)

        if body.delete_file:
            await service.delete_download_file(session_id, dl_id)

    return JSONResponse({"ok": True})
