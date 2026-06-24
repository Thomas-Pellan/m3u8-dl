import asyncio
import re

from playwright.async_api import Page, Response
from rich.console import Console

from ..models.segment import Segment, SegmentStatus
from ..models.session import CaptureSession, SessionStatus
from ..utils.m3u8_parser import parse_playlist, select_variant

console = Console()

_M3U8_MIME = frozenset({
    "application/vnd.apple.mpegurl",
    "application/x-mpegurl",
    "audio/mpegurl",
})
_TS_MIME = frozenset({
    "video/mp2t",
    "video/mpeg",
    # some CDNs serve segments as octet-stream; we fall back to URL matching
})

_RE_M3U8 = re.compile(r"\.m3u8", re.IGNORECASE)
_RE_TS = re.compile(r"\.ts(\?|$|/)", re.IGNORECASE)


class InterceptorService:
    """
    Listens to every browser response via the Playwright 'response' event.
    Saves .ts segments to disk and records the m3u8 playlist URL so that
    DownloaderService can take over if the caller chooses direct mode.
    """

    def __init__(self, session: CaptureSession, preferred_quality: str = "best") -> None:
        self._session = session
        self._preferred_quality = preferred_quality
        self._seen_urls: set[str] = set()
        self._segment_index = 0
        self._lock = asyncio.Lock()

    def attach(self, page: Page) -> None:
        page.on(
            "response",
            lambda r: asyncio.ensure_future(self._on_response(r)),
        )

    async def _on_response(self, response: Response) -> None:
        if self._session.status not in (SessionStatus.BROWSING, SessionStatus.CAPTURING):
            return

        url = response.url
        if url in self._seen_urls:
            return

        content_type = (
            response.headers.get("content-type", "").split(";")[0].strip().lower()
        )

        try:
            if self._is_m3u8(url, content_type):
                await self._handle_m3u8(url, response)
            elif self._is_ts(url, content_type):
                await self._handle_ts(url, response)
        except Exception as exc:
            # Never let interceptor errors crash the browser session.
            console.print(f"[yellow]interceptor warning:[/yellow] {exc}")

    # ── helpers ──────────────────────────────────────────────────────────────

    def _is_m3u8(self, url: str, content_type: str) -> bool:
        return content_type in _M3U8_MIME or bool(_RE_M3U8.search(url))

    def _is_ts(self, url: str, content_type: str) -> bool:
        return content_type in _TS_MIME or bool(_RE_TS.search(url))

    async def _handle_m3u8(self, url: str, response: Response) -> None:
        async with self._lock:
            if url in self._seen_urls:
                return
            self._seen_urls.add(url)

        body = await response.body()
        content = body.decode("utf-8", errors="replace")
        playlist = parse_playlist(url, content)

        console.print(f"[dim]m3u8 intercepted:[/dim] {url}")
        console.print(
            f"[dim]  → is_master={playlist.is_master}  "
            f"segments={len(playlist.segments)}  "
            f"variants={len(playlist.variants)}[/dim]"
        )

        if playlist.is_master:
            variant = select_variant(playlist, self._preferred_quality)
            if variant:
                console.print(
                    f"[cyan]Master playlist:[/cyan] selected variant "
                    f"{variant.resolution or 'unknown'} "
                    f"({variant.bandwidth // 1000} kbps)  →  {variant.url}"
                )
                self._session.m3u8_url = variant.url
            else:
                console.print("[cyan]Master playlist:[/cyan] no variants found, using master URL directly.")
                self._session.m3u8_url = url
                self._session.playlist = playlist
        else:
            if not self._session.m3u8_url:
                # First non-master playlist seen — use it directly.
                self._session.m3u8_url = url
                self._session.playlist = playlist
                console.print(
                    f"[cyan]Playlist ready:[/cyan] "
                    f"{len(playlist.segments)} segments  →  {url}"
                )
            elif url == self._session.m3u8_url and self._session.playlist is None:
                # Variant playlist selected from a master has now loaded in the browser.
                self._session.playlist = playlist
                console.print(
                    f"[cyan]Variant playlist ready:[/cyan] "
                    f"{len(playlist.segments)} segments  →  {url}"
                )
            else:
                console.print(
                    f"[dim]Skipping playlist (already have one or URL mismatch):[/dim] {url}"
                )

    async def _handle_ts(self, url: str, response: Response) -> None:
        async with self._lock:
            if url in self._seen_urls:
                return
            self._seen_urls.add(url)
            index = self._segment_index
            self._segment_index += 1

        if self._session.status == SessionStatus.BROWSING:
            self._session.status = SessionStatus.CAPTURING
            console.print(
                "[green]Capture started[/green] — TS segments are being saved."
            )

        # Snapshot the exact headers the browser sent on this request so the
        # downloader can replay them via httpx — Referer, Sec-Fetch-*, etc.
        if not self._session.browser_request_headers:
            raw = dict(response.request.headers)
            # Drop headers httpx or the cookie jar will manage itself.
            for key in ("host", "content-length", "content-type", "cookie", ":authority", ":method", ":path", ":scheme"):
                raw.pop(key, None)
            self._session.browser_request_headers = raw
            console.print(f"[dim]Captured {len(raw)} browser request headers for direct download.[/dim]")

        body = await response.body()
        dest = self._session.temp_dir / f"segment_{index:05d}.ts"
        dest.write_bytes(body)

        segment = Segment(
            index=index,
            url=url,
            local_path=dest,
            status=SegmentStatus.DONE,
            size_bytes=len(body),
        )
        self._session.segments.append(segment)
        self._session.captured_count += 1

        console.print(
            f"[green]  +[/green] segment {index:05d}  "
            f"({len(body) / 1024:.1f} KB)  total={self._session.captured_count}",
            end="\r",
        )
