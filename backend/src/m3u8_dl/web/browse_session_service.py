import asyncio
import base64
import json
import logging
import random
import re
import uuid
from collections.abc import Callable, Coroutine
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.async_api import Page, Response

logger = logging.getLogger(__name__)

from ..config import AppConfig
from ..models.session import CaptureSession
from ..services.assembler import AssemblerService
from ..services.browser import BrowserService
from ..services.downloader import DownloaderService
from ..services.title_scraper import TitleScraperService
from ..utils.m3u8_parser import parse_playlist
from .browse_session_repository import BrowseSessionRepository

_title_scraper = TitleScraperService()
_OnDownload = Callable[[str, str, "str | None"], Coroutine[Any, Any, None]]

_M3U8_MIME = frozenset({
    "application/vnd.apple.mpegurl",
    "application/x-mpegurl",
    "audio/mpegurl",
})
_SCREENSHOT_INTERVAL = 0.6  # seconds
_PROFILE_PATH = Path.home() / ".m3u8-dl" / "browser_profile.json"
_WARMUP_SITES = [
    "https://www.google.com",
    "https://en.wikipedia.org",
    "https://www.youtube.com",
]
_PROGRESS_RE = re.compile(r'(\d+)/(\d+) segments \((\d+)%\)')


class SessionConflictError(Exception):
    pass


class SessionNotFoundError(Exception):
    def __init__(self, session_id: str) -> None:
        super().__init__(f"session {session_id!r} not found")


class BrowseSessionService:
    def __init__(self, repo: BrowseSessionRepository, on_download: _OnDownload | None = None) -> None:
        self._repo = repo
        self._on_download = on_download
        self._active_id: str | None = None
        self._page: Page | None = None
        self._close_event: asyncio.Event | None = None
        self._screenshot_task: asyncio.Task | None = None
        self._list_subscribers: list[asyncio.Queue[str]] = []
        self._screen_subscribers: dict[str, list[asyncio.Queue[str]]] = {}
        self._seen_urls: set[str] = set()
        self._download_tasks: dict[str, list[asyncio.Task]] = {}
        self._viewport: dict[str, int] = {"width": 1280, "height": 720}

    async def init(self) -> None:
        await self._repo.init()
        await self._repo.delete_all()

    async def cleanup(self) -> None:
        if self._close_event:
            self._close_event.set()
        if self._screenshot_task:
            self._screenshot_task.cancel()
        for tasks in self._download_tasks.values():
            for t in tasks:
                t.cancel()

    # ── SSE: session list ─────────────────────────────────────────────────────────

    def subscribe_list(self) -> asyncio.Queue[str]:
        q: asyncio.Queue[str] = asyncio.Queue()
        self._list_subscribers.append(q)
        return q

    def unsubscribe_list(self, queue: asyncio.Queue[str]) -> None:
        try:
            self._list_subscribers.remove(queue)
        except ValueError:
            pass

    async def broadcast_list(self) -> None:
        sessions = await self._repo.get_all()
        payload = json.dumps(sessions)
        for q in list(self._list_subscribers):
            q.put_nowait(payload)

    # ── SSE: screenshots ──────────────────────────────────────────────────────────

    def subscribe_screen(self, session_id: str) -> asyncio.Queue[str]:
        q: asyncio.Queue[str] = asyncio.Queue(maxsize=2)
        self._screen_subscribers.setdefault(session_id, []).append(q)
        return q

    def unsubscribe_screen(self, session_id: str, queue: asyncio.Queue[str]) -> None:
        try:
            self._screen_subscribers.get(session_id, []).remove(queue)
        except ValueError:
            pass

    def _push_screenshot(self, session_id: str, b64: str) -> None:
        for q in list(self._screen_subscribers.get(session_id, [])):
            if q.full():
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            q.put_nowait(b64)

    # ── session lifecycle ─────────────────────────────────────────────────────────

    async def get_all_sessions(self) -> list[dict[str, Any]]:
        return await self._repo.get_all()

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        return await self._repo.get(session_id)

    async def create_session(self, url: str) -> str:
        if await self._repo.get_active():
            raise SessionConflictError("A browser session is already active")

        session_id = uuid.uuid4().hex[:8]
        await self._repo.insert({
            "id": session_id,
            "status": "opening",
            "url": url,
            "created_at": _now(),
            "closed_at": None,
            "error": None,
            "candidates": [],
            "downloads": [],
            "close_when_done": False,
        })
        await self.broadcast_list()
        asyncio.create_task(self._run_session(session_id, url))
        return session_id

    async def close_session(self, session_id: str) -> None:
        session = await self._repo.get(session_id)
        if session is None:
            raise SessionNotFoundError(session_id)

        # If there are active downloads, defer the close
        active_dls = [d for d in session.get("downloads", []) if d["status"] in ("running", "assembling")]
        if active_dls and self._active_id == session_id:
            await self._repo.update(session_id, close_when_done=True)
            await self.broadcast_list()
            return

        # Otherwise close immediately
        if self._active_id == session_id and self._close_event:
            self._close_event.set()
        await self._repo.update(session_id, status="closed", closed_at=_now(), close_when_done=False)
        await self.broadcast_list()

    async def force_close_session(self, session_id: str) -> None:
        session = await self._repo.get(session_id)
        if session is None:
            raise SessionNotFoundError(session_id)

        # Cancel any running download tasks
        for task in list(self._download_tasks.get(session_id, [])):
            task.cancel()
        self._download_tasks.pop(session_id, None)

        if self._active_id == session_id and self._close_event:
            self._close_event.set()
        await self._repo.update(session_id, status="closed", closed_at=_now(), close_when_done=False)
        await self.broadcast_list()

    async def delete_session(self, session_id: str) -> None:
        session = await self._repo.get(session_id)
        if session is None:
            raise SessionNotFoundError(session_id)
        if session["status"] in ("opening", "active"):
            raise SessionConflictError("Close the session before deleting it")
        await self._repo.delete(session_id)
        await self.broadcast_list()

    # ── downloads ─────────────────────────────────────────────────────────────────

    async def start_download(
        self,
        session_id: str,
        candidate_url: str,
        output_name: str,
        quality: str = "best",
        parallel: int = 4,
    ) -> str:
        if self._active_id != session_id or self._page is None:
            raise SessionNotFoundError(session_id)

        dl_id = uuid.uuid4().hex[:8]
        download_record: dict[str, Any] = {
            "id": dl_id,
            "url": candidate_url,
            "output_name": output_name,
            "status": "running",
            "progress": 0,
            "done_segments": 0,
            "total_segments": 0,
            "logs": [f"Queued: {candidate_url}"],
            "error": None,
            "started_at": _now(),
            "finished_at": None,
        }

        session = await self._repo.get(session_id)
        downloads = list(session.get("downloads") or [])
        downloads.append(download_record)
        await self._repo.update(session_id, downloads=downloads)
        await self.broadcast_list()

        # Grab cookies and UA from the live browser page before starting the task.
        # The Playwright transport can drop (browser crash / Docker OOM) after the
        # None-check above passes, so catch any channel error and treat it as the
        # session no longer being available.
        try:
            cookies = {c["name"]: c["value"] for c in await self._page.context.cookies()}
            ua: str = await self._page.evaluate("navigator.userAgent")
        except Exception as exc:
            logger.warning("session %s: browser context unavailable for download: %s", session_id, exc)
            # Roll back the download record we just inserted so the UI stays clean
            session = await self._repo.get(session_id)
            if session:
                dls = [d for d in session.get("downloads", []) if d["id"] != dl_id]
                await self._repo.update(session_id, downloads=dls)
                await self.broadcast_list()
            raise SessionNotFoundError(session_id) from exc

        if self._on_download:
            session = await self._repo.get(session_id)
            if session:
                cdn_origin = _extract_cdn_origin(candidate_url)
                asyncio.create_task(self._on_download(session["url"], "captured", cdn_origin))

        task = asyncio.create_task(
            self._run_download(session_id, dl_id, candidate_url, output_name, quality, parallel, cookies, ua)
        )
        self._download_tasks.setdefault(session_id, []).append(task)
        return dl_id

    async def _run_download(
        self,
        session_id: str,
        dl_id: str,
        candidate_url: str,
        output_name: str,
        quality: str,
        parallel: int,
        cookies: dict[str, str],
        ua: str,
    ) -> None:
        config = AppConfig()
        temp_dir = config.temp_dir / f"session_{dl_id}"
        temp_dir.mkdir(parents=True, exist_ok=True)
        output_path = config.output_dir / f"{output_name}.mp4"

        async def _patch(**kwargs: Any) -> None:
            s = await self._repo.get(session_id)
            if not s:
                return
            dls = list(s.get("downloads") or [])
            for d in dls:
                if d["id"] == dl_id:
                    d.update(kwargs)
                    break
            await self._repo.update(session_id, downloads=dls)
            await self.broadcast_list()

        cap_session = CaptureSession(output_path=output_path, temp_dir=temp_dir)
        progress_q: asyncio.Queue = asyncio.Queue()
        logs: list[str] = [f"Fetching playlist: {candidate_url}"]

        def _log(msg: str) -> None:
            msg = msg.strip()
            if not msg:
                return
            logs.append(msg)
            m = _PROGRESS_RE.search(msg)
            if m:
                progress_q.put_nowait((int(m.group(1)), int(m.group(2)), int(m.group(3))))

        async def _drain() -> None:
            while True:
                item = await progress_q.get()
                if item is None:
                    break
                done_seg, total_seg, pct = item
                await _patch(progress=pct, done_segments=done_seg, total_segments=total_seg, logs=list(logs))

        drain_task = asyncio.create_task(_drain())
        try:
            downloader = DownloaderService(
                max_parallel=parallel,
                timeout=config.request_timeout,
                delay_min=config.request_delay_min,
                delay_max=config.request_delay_max,
                log_fn=_log,
            )
            await downloader.download_from_url(candidate_url, cap_session, cookies, ua, quality)

            logs.append("Assembling segments…")
            await _patch(status="assembling", progress=100, logs=list(logs))

            assembler = AssemblerService()
            await assembler.assemble(cap_session.segments, output_path)

            logs.append(f"Done → {output_path.name}")
            await _patch(status="done", finished_at=_now(), logs=list(logs))

            # Cleanup temp segments
            for seg in cap_session.segments:
                if seg.local_path and seg.local_path.exists():
                    seg.local_path.unlink()
            try:
                temp_dir.rmdir()
            except OSError:
                pass

        except asyncio.CancelledError:
            logs.append("Cancelled.")
            await _patch(status="cancelled", finished_at=_now(), logs=list(logs))
            raise
        except Exception as exc:
            logger.error("session %s download %s failed: %s", session_id, dl_id, exc, exc_info=True)
            logs.append(f"Error: {exc}")
            await _patch(status="error", error=str(exc), finished_at=_now(), logs=list(logs))
        finally:
            progress_q.put_nowait(None)
            try:
                await asyncio.wait_for(drain_task, timeout=3.0)
            except Exception:
                drain_task.cancel()

            # Remove this task from tracking
            current = asyncio.current_task()
            self._download_tasks[session_id] = [
                t for t in self._download_tasks.get(session_id, [])
                if t is not current and not t.done()
            ]

            # Trigger deferred close if all downloads are finished
            s = await self._repo.get(session_id)
            if s and s.get("close_when_done"):
                remaining = self._download_tasks.get(session_id, [])
                if not remaining:
                    if self._active_id == session_id and self._close_event:
                        self._close_event.set()
                    await self._repo.update(
                        session_id, status="closed", closed_at=_now(), close_when_done=False
                    )
                    await self.broadcast_list()

    # ── actions ───────────────────────────────────────────────────────────────────

    async def send_action(self, session_id: str, action: dict[str, Any]) -> None:
        if self._active_id != session_id or self._page is None:
            raise SessionNotFoundError(session_id)
        page = self._page
        kind = action.get("type")
        if kind == "click":
            vp = self._viewport
            await page.mouse.click(
                float(action["x"]) * vp["width"],
                float(action["y"]) * vp["height"],
            )
        elif kind == "scroll":
            delta = float(action.get("delta_y", 200))
            await page.evaluate(f"window.scrollBy(0, {delta})")
        elif kind == "navigate":
            target = str(action["url"])
            try:
                await page.goto(target, wait_until="domcontentloaded", timeout=30_000)
                await self._repo.update(session_id, error=None)
                await self.broadcast_list()
            except Exception as nav_exc:
                logger.warning("session %s: navigate to %s failed: %s", session_id, target, nav_exc)
                await self._repo.update(session_id, error=str(nav_exc))
                await self.broadcast_list()
        elif kind == "back":
            try:
                await page.evaluate("window.history.back()")
                await self._repo.update(session_id, error=None)
                await self.broadcast_list()
            except Exception as nav_exc:
                logger.warning("session %s: go_back failed: %s", session_id, nav_exc)
                await self._repo.update(session_id, error=str(nav_exc))
                await self.broadcast_list()
        elif kind == "resize":
            width = max(320, min(3840, int(action.get("width", 1280))))
            height = max(240, min(2160, int(action.get("height", 720))))
            self._viewport = {"width": width, "height": height}
            await page.set_viewport_size({"width": width, "height": height})
        else:
            raise ValueError(f"Unknown action type: {kind!r}")

    # ── browser profile ───────────────────────────────────────────────────────────

    def _load_profile(self) -> dict | None:
        try:
            return json.loads(_PROFILE_PATH.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def _save_profile(self, state: dict) -> None:
        try:
            _PROFILE_PATH.write_text(json.dumps(state))
        except Exception as exc:
            logger.warning("could not save browser profile: %s", exc)

    def flush_profile(self) -> None:
        try:
            _PROFILE_PATH.unlink(missing_ok=True)
            logger.info("browser profile flushed")
        except Exception as exc:
            logger.warning("could not flush browser profile: %s", exc)

    async def get_page_titles(self, session_id: str) -> list[dict[str, str]]:
        if self._active_id != session_id or self._page is None:
            raise SessionNotFoundError(session_id)
        titles = await _title_scraper.scrape_candidates(self._page)
        return [{"title": t, "filename": _title_scraper.to_filename(t)} for t in titles]

    async def clear_candidates(self, session_id: str) -> None:
        session = await self._repo.get(session_id)
        if session is None:
            raise SessionNotFoundError(session_id)
        self._seen_urls = set()
        await self._repo.update(session_id, candidates=[])
        await self.broadcast_list()

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        return await self._repo.get(session_id)

    async def delete_download_file(self, session_id: str, dl_id: str) -> None:
        session = await self._repo.get(session_id)
        if session is None:
            return
        download = next((d for d in session.get("downloads", []) if d["id"] == dl_id), None)
        if download is None:
            return
        output_name = download.get("output_name", "")
        if not output_name:
            return
        config = AppConfig()
        output_path = config.output_dir / f"{output_name}.mp4"
        try:
            output_path.unlink(missing_ok=True)
            logger.info("deleted output file: %s", output_path)
        except Exception as exc:
            logger.warning("could not delete output file %s: %s", output_path, exc)

    # ── internal session runner ───────────────────────────────────────────────────

    async def _run_session(self, session_id: str, url: str) -> None:
        self._active_id = session_id
        self._seen_urls = set()
        self._close_event = asyncio.Event()
        self._viewport = {"width": 1280, "height": 720}

        browser_svc = BrowserService(headless="virtual", humanize=True)
        try:
            async with browser_svc.launch() as b:
                profile = self._load_profile()
                context = await b.new_context(storage_state=profile)
                page = await context.new_page()
                self._page = page
                page.on(
                    "response",
                    lambda r: asyncio.create_task(self._on_response(session_id, r)),
                )
                await self._repo.update(session_id, status="active")
                await self.broadcast_list()

                if profile is None:
                    await self._warm_up(page, session_id)

                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                    await self._repo.update(session_id, error=None)
                except Exception as nav_exc:
                    logger.warning("session %s: navigation to %s failed: %s", session_id, url, nav_exc)
                    await self._repo.update(session_id, error=str(nav_exc))
                    await self.broadcast_list()

                self._screenshot_task = asyncio.create_task(
                    self._screenshot_loop(session_id)
                )
                await self._close_event.wait()

                try:
                    self._save_profile(await context.storage_state())
                except Exception as save_exc:
                    logger.warning("session %s: could not save profile: %s", session_id, save_exc)

        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error("browse session %s failed: %s", session_id, exc, exc_info=True)
            await self._repo.update(
                session_id, status="error", error=str(exc), closed_at=_now()
            )
            await self.broadcast_list()
        finally:
            self._page = None
            if self._active_id == session_id:
                self._active_id = None
            if self._screenshot_task:
                self._screenshot_task.cancel()
                self._screenshot_task = None

    # ── warmup (first run) ────────────────────────────────────────────────────────

    async def _warm_up(self, page: Page, session_id: str) -> None:
        logger.info("session %s: first run — warming up browser profile", session_id)
        await self._repo.update(
            session_id,
            error="First run: visiting a few sites to build a browser profile…",
        )
        await self.broadcast_list()
        for site in _WARMUP_SITES:
            try:
                await page.goto(site, wait_until="domcontentloaded", timeout=15_000)
                await asyncio.sleep(random.uniform(1.0, 2.5))
                for _ in range(random.randint(2, 4)):
                    await page.mouse.wheel(0, random.randint(200, 500))
                    await asyncio.sleep(random.uniform(0.4, 1.2))
            except Exception as exc:
                logger.warning("session %s: warmup site %s failed: %s", session_id, site, exc)
        await self._repo.update(session_id, error=None)
        await self.broadcast_list()
        logger.info("session %s: warmup complete", session_id)

    # ── screenshot loop ───────────────────────────────────────────────────────────

    async def _screenshot_loop(self, session_id: str) -> None:
        while self._active_id == session_id and self._page is not None:
            try:
                data = await self._page.screenshot(type="jpeg", quality=70)
                self._push_screenshot(session_id, base64.b64encode(data).decode())
            except Exception:
                pass
            await asyncio.sleep(_SCREENSHOT_INTERVAL)

    # ── HLS interception ──────────────────────────────────────────────────────────

    async def _on_response(self, session_id: str, response: Response) -> None:
        if response.status != 200:
            return
        url = response.url
        if url in self._seen_urls:
            return
        content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
        if content_type not in _M3U8_MIME and ".m3u8" not in url.lower():
            return
        self._seen_urls.add(url)
        try:
            body = await response.body()
            content = body.decode("utf-8", errors="replace")
            candidate = _parse_candidate(url, content)
            session = await self._repo.get(session_id)
            if session is None:
                return
            candidates: list[dict[str, Any]] = session["candidates"]
            if any(c["url"] == url for c in candidates):
                return
            candidates.append(candidate)
            await self._repo.update(session_id, candidates=candidates)
            await self.broadcast_list()
        except Exception:
            pass


# ── helpers ───────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _extract_cdn_origin(url: str) -> str | None:
    try:
        from urllib.parse import urlparse
        p = urlparse(url)
        if p.scheme and p.netloc:
            return f"{p.scheme}://{p.netloc}"
    except Exception:
        pass
    return None


def _parse_candidate(url: str, content: str) -> dict[str, Any]:
    try:
        import m3u8 as _m3u8
        parsed = _m3u8.loads(content)
    except Exception:
        return {
            "url": url,
            "type": "unknown",
            "duration_s": None,
            "streams": [],
            "audio_tracks": [],
            "subtitle_tracks": [],
            "intercepted_at": _now(),
        }

    if parsed.is_variant:
        streams = []
        for p in parsed.playlists:
            info = p.stream_info
            resolution = (
                f"{info.resolution[0]}x{info.resolution[1]}" if info.resolution else None
            )
            streams.append({
                "bandwidth": info.bandwidth,
                "resolution": resolution,
                "codecs": getattr(info, "codecs", None),
                "frame_rate": getattr(info, "frame_rate", None),
                "video_range": getattr(info, "video_range", None),
            })
        streams.sort(key=lambda s: s["bandwidth"], reverse=True)

        audio_tracks: list[dict[str, Any]] = []
        subtitle_tracks: list[dict[str, Any]] = []
        seen_audio: set[tuple] = set()
        seen_subs: set[tuple] = set()
        for media in (parsed.media or []):
            lang = getattr(media, "language", None)
            name = getattr(media, "name", None) or lang or "?"
            mtype = getattr(media, "type", "")
            default = getattr(media, "default", False)
            forced = getattr(media, "forced", False)
            # library may return "YES"/"NO" strings instead of bools
            if isinstance(default, str):
                default = default.upper() == "YES"
            if isinstance(forced, str):
                forced = forced.upper() == "YES"

            if mtype == "AUDIO":
                key = (lang, name)
                if key not in seen_audio:
                    seen_audio.add(key)
                    audio_tracks.append({"language": lang, "name": name, "default": default})
            elif mtype == "SUBTITLES":
                key = (lang, name)
                if key not in seen_subs:
                    seen_subs.add(key)
                    subtitle_tracks.append({"language": lang, "name": name, "forced": forced})

        return {
            "url": url,
            "type": "master",
            "duration_s": None,
            "streams": streams,
            "audio_tracks": audio_tracks,
            "subtitle_tracks": subtitle_tracks,
            "intercepted_at": _now(),
        }

    total = 0.0
    found = False
    for line in content.splitlines():
        if line.startswith("#EXTINF:"):
            try:
                total += float(line[8:].split(",")[0])
                found = True
            except ValueError:
                pass
    return {
        "url": url,
        "type": "media",
        "duration_s": round(total) if found else None,
        "streams": [],
        "audio_tracks": [],
        "subtitle_tracks": [],
        "intercepted_at": _now(),
    }
