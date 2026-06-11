import asyncio
from pathlib import Path

import click
from rich.console import Console

from .config import AppConfig
from .services.capture import CaptureService

console = Console()


@click.group()
@click.version_option("0.1.0")
def cli() -> None:
    """m3u8-dl — intercept and download HLS streams to MP4."""


@cli.command()
@click.argument("output_name", required=False, default=None)
@click.option(
    "--output-dir", "-d",
    type=click.Path(path_type=Path),
    default=None,
    help="Output directory. Overrides VS_OUTPUT_DIR.",
)
@click.option(
    "--mode", "-m",
    type=click.Choice(["auto", "intercept", "direct"]),
    default=None,
    help="Capture mode. Overrides VS_CAPTURE_MODE. (auto / intercept / direct)",
)
@click.option(
    "--keep-segments/--no-keep-segments",
    default=None,
    help="Keep .ts segment files after assembly. Overrides VS_KEEP_SEGMENTS.",
)
@click.option(
    "--quality", "-q",
    default=None,
    help="Quality: best, worst, or a resolution string like 1920x1080. Overrides VS_PREFERRED_QUALITY.",
)
@click.option(
    "--parallel", "-p",
    default=None,
    type=int,
    help="Parallel segment downloads. Overrides VS_MAX_PARALLEL_DOWNLOADS.",
)
@click.option(
    "--headless/--no-headless",
    default=None,
    help="Run browser headlessly. Overrides VS_HEADLESS.",
)
@click.option(
    "--delay-min",
    default=None,
    type=float,
    help="Min random delay (seconds) per request. Overrides VS_REQUEST_DELAY_MIN.",
)
@click.option(
    "--delay-max",
    default=None,
    type=float,
    help="Max random delay (seconds) per request. Overrides VS_REQUEST_DELAY_MAX.",
)
def capture(
    output_name: str | None,
    output_dir: Path | None,
    mode: str | None,
    keep_segments: bool | None,
    quality: str | None,
    parallel: int | None,
    headless: bool | None,
    delay_min: float | None,
    delay_max: float | None,
) -> None:
    """
    Open a camoufox browser, let you navigate to the movie player,
    then capture and assemble it into OUTPUT_NAME.mp4.

    \b
    All options fall back to .env values, then to built-in defaults.
    CLI flags take highest priority.

    \b
    OUTPUT_NAME is optional. If omitted, the script scrapes the movie page
    for a title and asks you to confirm before the download starts.

    \b
    Examples:
      video-scraper capture
      video-scraper capture interstellar
      video-scraper capture --mode direct --quality 1920x1080
      video-scraper capture --keep-segments --output-dir /tmp
    """
    # Build overrides from only the options the user explicitly passed.
    # Omitted options are left to AppConfig to resolve from .env / defaults.
    overrides: dict = {k: v for k, v in {
        "output_dir": output_dir,
        "capture_mode": mode,
        "keep_segments": keep_segments,
        "preferred_quality": quality,
        "max_parallel_downloads": parallel,
        "headless": headless,
        "request_delay_min": delay_min,
        "request_delay_max": delay_max,
    }.items() if v is not None}

    config = AppConfig(**overrides)

    service = CaptureService(config)

    try:
        output = asyncio.run(service.run(output_name))
        console.print(f"\n[bold green]Saved:[/bold green] {output}")
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
        raise SystemExit(130)
    except Exception as exc:
        console.print(f"\n[bold red]Error:[/bold red] {exc}")
        raise SystemExit(1)


@cli.command()
@click.argument("segments_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.argument("output_file", type=click.Path(path_type=Path))
def assemble(segments_dir: Path, output_file: Path) -> None:
    """
    Assemble previously captured .ts segments into a single mp4.

    \b
    Useful for resuming after a failed run if --keep-segments was used.

    \b
    Example:
      video-scraper assemble ~/.video-scraper/temp/my-movie my-movie.mp4
    """
    from .models.segment import Segment, SegmentStatus
    from .services.assembler import AssemblerService

    ts_files = sorted(segments_dir.glob("segment_*.ts"))
    if not ts_files:
        console.print(f"[red]No segment_*.ts files found in {segments_dir}[/red]")
        raise SystemExit(1)

    segments = [
        Segment(
            index=i,
            url="",
            local_path=f,
            status=SegmentStatus.DONE,
            size_bytes=f.stat().st_size,
        )
        for i, f in enumerate(ts_files)
    ]

    assembler = AssemblerService()
    try:
        asyncio.run(assembler.assemble(segments, output_file))
    except Exception as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise SystemExit(1)
