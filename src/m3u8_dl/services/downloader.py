import asyncio
import random
from pathlib import Path

import httpx
from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TransferSpeedColumn,
)

from ..models.playlist import Playlist
from ..models.segment import Segment, SegmentStatus
from ..models.session import CaptureSession, SessionStatus
from ..utils.m3u8_parser import parse_playlist, select_variant

console = Console()


class DownloaderService:
    """Downloads all segments from a parsed m3u8 playlist in parallel."""

    def __init__(
        self,
        max_parallel: int = 8,
        timeout: int = 30,
        delay_min: float = 0.1,
        delay_max: float = 0.6,
    ) -> None:
        self._max_parallel = max_parallel
        self._timeout = timeout
        self._delay_min = delay_min
        self._delay_max = delay_max

    async def download_from_playlist(
        self,
        playlist: Playlist,
        session: CaptureSession,
        cookies: dict[str, str],
        user_agent: str,
    ) -> None:
        """Download using a Playlist already parsed by the interceptor.

        Avoids re-fetching the m3u8 URL, which often fails outside the browser
        session due to CDN auth tokens embedded in the URL or cookies.
        """
        session.status = SessionStatus.DOWNLOADING
        session.total_count = len(playlist.segments)
        session.segments = playlist.segments

        headers = self._build_headers(session, user_agent)
        console.print(
            f"[cyan]Downloading {len(playlist.segments)} segments "
            f"({self._max_parallel} parallel, delay {self._delay_min}–{self._delay_max}s)...[/cyan]"
        )

        async with httpx.AsyncClient(
            cookies=cookies,
            headers=headers,
            timeout=self._timeout,
            follow_redirects=True,
        ) as client:
            await self._run_workers(client, playlist.segments, session)

        session.segments = sorted(session.segments, key=lambda s: s.index)

    async def download_from_url(
        self,
        m3u8_url: str,
        session: CaptureSession,
        cookies: dict[str, str],
        user_agent: str,
        preferred_quality: str = "best",
    ) -> None:
        session.status = SessionStatus.DOWNLOADING

        headers = self._build_headers(session, user_agent)

        async with httpx.AsyncClient(
            cookies=cookies,
            headers=headers,
            timeout=self._timeout,
            follow_redirects=True,
        ) as client:
            playlist = await self._resolve_playlist(client, m3u8_url, preferred_quality)
            session.total_count = len(playlist.segments)
            session.segments = playlist.segments

            console.print(
                f"[cyan]Downloading {len(playlist.segments)} segments "
                f"({self._max_parallel} parallel, delay {self._delay_min}–{self._delay_max}s)...[/cyan]"
            )

            await self._run_workers(client, playlist.segments, session)

        session.segments = sorted(session.segments, key=lambda s: s.index)

    def _build_headers(self, session: CaptureSession, user_agent: str) -> dict[str, str]:
        if session.browser_request_headers:
            return session.browser_request_headers
        # Fallback when no browser headers were captured (e.g. intercept never saw a TS).
        return {
            "User-Agent": user_agent,
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Sec-Fetch-Dest": "video",
            "Sec-Fetch-Mode": "no-cors",
            "Sec-Fetch-Site": "cross-site",
        }

    async def _run_workers(
        self,
        client: httpx.AsyncClient,
        segments: list[Segment],
        session: CaptureSession,
    ) -> None:
        semaphore = asyncio.Semaphore(self._max_parallel)

        with Progress(
            SpinnerColumn(),
            "[progress.description]{task.description}",
            BarColumn(),
            "[progress.percentage]{task.percentage:>3.0f}%",
            DownloadColumn(),
            TransferSpeedColumn(),
            console=console,
        ) as progress:
            task_id: TaskID = progress.add_task("Downloading", total=len(segments))

            async def _worker(segment: Segment) -> None:
                async with semaphore:
                    await self._download_segment(client, segment, session.temp_dir)
                    session.captured_count += 1
                    progress.advance(task_id)

            await asyncio.gather(
                *[_worker(seg) for seg in segments],
                return_exceptions=False,
            )

    async def _resolve_playlist(
        self,
        client: httpx.AsyncClient,
        url: str,
        quality: str,
    ) -> Playlist:
        response = await client.get(url)
        response.raise_for_status()
        playlist = parse_playlist(url, response.text)

        if playlist.is_master:
            variant = select_variant(playlist, quality)
            if variant:
                console.print(
                    f"[cyan]Selected variant:[/cyan] "
                    f"{variant.resolution or 'unknown'} "
                    f"({variant.bandwidth // 1000} kbps)"
                )
                response = await client.get(variant.url)
                response.raise_for_status()
                playlist = parse_playlist(variant.url, response.text)

        return playlist

    async def _download_segment(
        self,
        client: httpx.AsyncClient,
        segment: Segment,
        temp_dir: Path,
        max_retries: int = 4,
    ) -> None:
        await asyncio.sleep(random.uniform(self._delay_min, self._delay_max))

        segment.status = SegmentStatus.DOWNLOADING
        dest = temp_dir / f"segment_{segment.index:05d}.ts"

        for attempt in range(max_retries):
            try:
                response = await client.get(segment.url)

                if response.status_code in (429, 503):
                    # Rate-limited — exponential backoff with jitter.
                    wait = (2 ** attempt) * 3 + random.uniform(0, 2)
                    console.print(
                        f"\n[yellow]Rate limited (HTTP {response.status_code}) "
                        f"on segment {segment.index} — waiting {wait:.1f}s[/yellow]"
                    )
                    await asyncio.sleep(wait)
                    continue

                response.raise_for_status()

                if len(response.content) < 1024:
                    # Server returned an error page instead of a real TS segment.
                    wait = (2 ** attempt) * 2 + random.uniform(0, 2)
                    console.print(
                        f"\n[yellow]Suspiciously small response ({len(response.content)} bytes) "
                        f"for segment {segment.index} (HTTP {response.status_code}) "
                        f"— retry in {wait:.1f}s[/yellow]"
                    )
                    await asyncio.sleep(wait)
                    continue

                dest.write_bytes(response.content)
                segment.local_path = dest
                segment.size_bytes = len(response.content)
                segment.status = SegmentStatus.DONE
                return

            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                wait = (2 ** attempt) * 2 + random.uniform(0, 2)
                console.print(
                    f"\n[yellow]Network error on segment {segment.index} "
                    f"({exc.__class__.__name__}) — retry in {wait:.1f}s[/yellow]"
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(wait)
                else:
                    segment.status = SegmentStatus.FAILED
                    segment.error = str(exc)
                    raise

            except Exception as exc:
                segment.status = SegmentStatus.FAILED
                segment.error = str(exc)
                raise

        segment.status = SegmentStatus.FAILED
        segment.error = f"Failed after {max_retries} attempts"
        raise RuntimeError(segment.error)
