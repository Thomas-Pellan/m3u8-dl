import asyncio
from pathlib import Path

from rich.console import Console
from rich.prompt import Prompt

from ..config import AppConfig
from ..models.session import CaptureSession, SessionStatus
from ..services.assembler import AssemblerService
from ..services.browser import BrowserService
from ..services.downloader import DownloaderService
from ..services.interceptor import InterceptorService
from ..services.title_scraper import TitleScraperService

console = Console()

_M3U8_DETECTION_TIMEOUT = 30


class CaptureService:
    """
    Orchestrates the full capture workflow:
      1. Opens camoufox browser
      2. Attaches response interceptor
      3. Waits for user to navigate to the movie player
      4. Scrapes the page for title suggestions, prompts user to pick one
      5. Runs the chosen capture mode (auto / intercept / direct)
      6. Assembles segments into an mp4 via ffmpeg
    """

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._browser = BrowserService(headless=config.headless)
        self._assembler = AssemblerService()
        self._downloader = DownloaderService(
            max_parallel=config.max_parallel_downloads,
            timeout=config.request_timeout,
            delay_min=config.request_delay_min,
            delay_max=config.request_delay_max,
        )
        self._title_scraper = TitleScraperService()

    async def run(self, output_name: str | None = None) -> Path:
        if not self._assembler.is_available():
            raise RuntimeError("ffmpeg not found. Install it and ensure it is on PATH.")

        # output_path is resolved after the user picks a title; use a
        # session-id-based temp dir in the meantime.
        session = CaptureSession(
            output_path=Path("__pending__"),
            temp_dir=self._config.temp_dir / "__pending__",
        )
        session.temp_dir.mkdir(parents=True, exist_ok=True)

        async with self._browser.launch():
            chosen_name = await self._run_capture(session, output_name)

        output_path = self._config.output_dir / chosen_name
        if not output_path.suffix:
            output_path = output_path.with_suffix(".mp4")
        return output_path

    # ── capture flow ─────────────────────────────────────────────────────────

    async def _run_capture(self, session: CaptureSession, forced_name: str | None) -> str:
        page = await self._browser.new_page()

        interceptor = InterceptorService(
            session=session,
            preferred_quality=self._config.preferred_quality,
        )
        interceptor.attach(page)

        session.status = SessionStatus.BROWSING
        if self._config.headless:
            url = await asyncio.get_running_loop().run_in_executor(
                None, lambda: Prompt.ask("[bold]Movie URL[/bold]")
            )
            await page.goto(url)
        else:
            console.print(
                "\n[bold]Browser is open.[/bold]  "
                "Navigate to the movie player, start the video, "
                "then press [bold cyan]Enter[/bold cyan] here.\n"
            )
            await asyncio.get_running_loop().run_in_executor(None, input)

        # Scrape title from the current page, then ask user to confirm.
        # This happens before the download so the output path is known.
        if forced_name:
            output_stem = self._title_scraper.to_filename(forced_name)
        else:
            candidates = await self._title_scraper.scrape_candidates(page)
            output_stem = await asyncio.get_running_loop().run_in_executor(
                None, lambda: self._title_scraper.prompt_user(candidates)
            )

        # Promote the pending temp dir to its final name. Any TS segments already
        # captured by the interceptor move with it; their local_path refs are updated.
        # Falls back to mkdir if rename fails (e.g. target already exists from a
        # prior failed run), leaving old_temp to be swept up by the OS on next boot.
        output_path = self._config.output_dir / f"{output_stem}.mp4"
        old_temp = session.temp_dir
        new_temp = self._config.temp_dir / output_stem
        try:
            old_temp.rename(new_temp)
            for seg in session.segments:
                if seg.local_path is not None:
                    seg.local_path = new_temp / seg.local_path.name
        except OSError:
            new_temp.mkdir(parents=True, exist_ok=True)
        session.output_path = output_path
        session.temp_dir = new_temp

        mode = self._config.capture_mode
        if mode == "intercept":
            await self._intercept_mode(session)
        elif mode == "direct":
            await self._direct_mode(session, page)
        else:
            await self._auto_mode(session, page)

        await self._assemble(session)
        return output_stem

    async def _intercept_mode(self, session: CaptureSession) -> None:
        session.status = SessionStatus.CAPTURING
        console.print(
            "[cyan]Intercept mode:[/cyan] let the video play to the end, "
            "then press [bold cyan]Enter[/bold cyan].\n"
        )
        await asyncio.get_running_loop().run_in_executor(None, input)
        console.print(f"\n[green]{session.captured_count} segments captured.[/green]")

    async def _direct_mode(self, session: CaptureSession, page) -> None:
        if not session.playlist:
            console.print(
                f"[yellow]No playlist detected yet. "
                f"Waiting up to {_M3U8_DETECTION_TIMEOUT}s...[/yellow]"
            )
            await self._wait_for_playlist(session)

        console.print(
            f"[dim]direct mode — "
            f"m3u8_url={session.m3u8_url or 'None'}  "
            f"playlist={'set (' + str(len(session.playlist.segments)) + ' segments)' if session.playlist else 'None'}[/dim]"
        )

        cookies = await self._browser.get_cookies(page)
        ua = await self._browser.get_user_agent(page)

        if session.playlist:
            await self._downloader.download_from_playlist(session.playlist, session, cookies, ua)
        elif session.m3u8_url:
            console.print("[yellow]Playlist content not cached — re-fetching URL via httpx.[/yellow]")
            await self._downloader.download_from_url(
                session.m3u8_url, session, cookies, ua, self._config.preferred_quality
            )
        else:
            url = Prompt.ask("[yellow]Could not auto-detect m3u8. Paste URL manually[/yellow]")
            await self._downloader.download_from_url(
                url, session, cookies, ua, self._config.preferred_quality
            )

    async def _auto_mode(self, session: CaptureSession, page) -> None:
        console.print(
            f"[cyan]Auto mode:[/cyan] waiting up to {_M3U8_DETECTION_TIMEOUT}s "
            "for m3u8 playlist..."
        )
        await self._wait_for_playlist(session)

        console.print(
            f"[dim]auto mode — "
            f"m3u8_url={session.m3u8_url or 'None'}  "
            f"playlist={'set (' + str(len(session.playlist.segments)) + ' segments)' if session.playlist else 'None'}[/dim]"
        )

        if session.playlist:
            console.print(
                f"[green]Playlist ready[/green] ({len(session.playlist.segments)} segments) "
                "— starting parallel download."
            )
            # Discard any TS files the interceptor wrote before we had the full
            # playlist — direct mode will download all segments cleanly.
            for seg in session.segments:
                if seg.local_path and seg.local_path.exists():
                    seg.local_path.unlink()
            session.segments.clear()
            session.captured_count = 0

            cookies = await self._browser.get_cookies(page)
            ua = await self._browser.get_user_agent(page)
            await self._downloader.download_from_playlist(session.playlist, session, cookies, ua)
        else:
            console.print(
                "[yellow]No playlist found after timeout — falling back to intercept mode.[/yellow]\n"
                "[dim]Hint: make sure the video has started playing before pressing Enter.[/dim]"
            )
            await self._intercept_mode(session)

    # ── helpers ───────────────────────────────────────────────────────────────

    async def _wait_for_playlist(self, session: CaptureSession) -> None:
        for i in range(_M3U8_DETECTION_TIMEOUT):
            if session.playlist:
                return
            if i % 5 == 0 and i > 0:
                console.print(
                    f"[dim]  waiting... {i}s  "
                    f"m3u8_url={session.m3u8_url or 'not yet'}  "
                    f"playlist={'ready' if session.playlist else 'not yet'}[/dim]"
                )
            await asyncio.sleep(1)

    async def _assemble(self, session: CaptureSession) -> None:
        if not session.segments:
            raise ValueError(
                "No segments captured. "
                "Make sure the video started playing before pressing Enter."
            )
        session.status = SessionStatus.ASSEMBLING
        await self._assembler.assemble(session.segments, session.output_path)
        session.status = SessionStatus.COMPLETE

        if not self._config.keep_segments:
            self._cleanup(session)

    def _cleanup(self, session: CaptureSession) -> None:
        for seg in session.segments:
            if seg.local_path and seg.local_path.exists():
                seg.local_path.unlink()
        try:
            session.temp_dir.rmdir()
        except OSError:
            pass
