import asyncio
from pathlib import Path

from rich.console import Console

from ..models.segment import Segment, SegmentStatus
from ..utils.ffmpeg_check import check_ffmpeg

console = Console()


class AssemblerService:
    def __init__(self) -> None:
        self._ffmpeg_path = check_ffmpeg()

    def is_available(self) -> bool:
        return self._ffmpeg_path is not None

    async def assemble(self, segments: list[Segment], output_path: Path) -> Path:
        if not self.is_available():
            raise RuntimeError("ffmpeg not found. Install it and make sure it is on PATH.")

        done = [
            s for s in segments
            if s.status == SegmentStatus.DONE and s.local_path is not None
        ]
        if not done:
            raise ValueError("No completed segments to assemble.")

        done.sort(key=lambda s: s.index)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        self._warn_gaps(segments, done)

        console.print(f"[cyan]Assembling {len(done)} segments → {output_path.name}[/cyan]")

        # Binary-concatenate all TS files into one before remuxing.
        # TS is a byte-stream container designed to be concatenated; doing this
        # before ffmpeg avoids timestamp discontinuities at every segment boundary
        # that cause audio/video glitches when using the concat demuxer.
        combined_ts = output_path.parent / f".{output_path.stem}_combined.ts"
        try:
            await asyncio.to_thread(self._concat_binary, done, combined_ts)
            await self._remux(combined_ts, output_path)
        finally:
            combined_ts.unlink(missing_ok=True)

        size_mb = output_path.stat().st_size / (1024 * 1024)
        console.print(f"[bold green]✓ Done:[/bold green] {output_path}  ({size_mb:.1f} MB)")
        return output_path

    # ── helpers ───────────────────────────────────────────────────────────────

    def _concat_binary(self, segments: list[Segment], dest: Path) -> None:
        with dest.open("wb") as out:
            for seg in segments:
                out.write(seg.local_path.read_bytes())

    async def _remux(self, source_ts: Path, output_path: Path) -> None:
        cmd = [
            self._ffmpeg_path,
            "-y",
            "-i", str(source_ts),
            "-c", "copy",
            # Convert ADTS-wrapped AAC (used in TS) to the ASC format required
            # by the MP4 container. Without this, audio glitches at every
            # segment boundary.
            "-bsf:a", "aac_adtstoasc",
            str(output_path),
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg exited {proc.returncode}:\n{stderr.decode()}")

    def _warn_gaps(self, all_segments: list[Segment], done: list[Segment]) -> None:
        failed = [s for s in all_segments if s.status == SegmentStatus.FAILED]
        if failed:
            indices = ", ".join(str(s.index) for s in failed[:10])
            if len(failed) > 10:
                indices += f" … (+{len(failed) - 10} more)"
            console.print(
                f"[yellow]⚠ {len(failed)} segment(s) failed to download "
                f"and will be missing from the video: {indices}[/yellow]"
            )

        # Check for index gaps (segments that were never attempted).
        if done:
            expected = set(range(done[0].index, done[-1].index + 1))
            present = {s.index for s in done}
            gaps = sorted(expected - present)
            if gaps:
                gap_str = ", ".join(str(g) for g in gaps[:10])
                if len(gaps) > 10:
                    gap_str += f" … (+{len(gaps) - 10} more)"
                console.print(
                    f"[yellow]⚠ {len(gaps)} gap(s) in segment sequence "
                    f"(indices {gap_str}) — these will appear as cuts.[/yellow]"
                )
