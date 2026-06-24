import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from .playlist import Playlist
from .segment import Segment


class SessionStatus(str, Enum):
    IDLE = "idle"
    BROWSING = "browsing"        # waiting for user to navigate to the player
    CAPTURING = "capturing"      # intercepting live TS segments from the browser
    DOWNLOADING = "downloading"  # direct parallel download from parsed m3u8
    ASSEMBLING = "assembling"    # ffmpeg concat → mp4
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class CaptureSession:
    output_path: Path
    temp_dir: Path
    session_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    status: SessionStatus = SessionStatus.IDLE
    m3u8_url: str | None = None
    playlist: Playlist | None = None  # parsed by interceptor; avoids re-fetching auth'd URLs
    # Exact headers the browser used on the first TS request — reused by httpx so
    # direct downloads are indistinguishable from browser-originated requests.
    browser_request_headers: dict[str, str] = field(default_factory=dict)
    segments: list[Segment] = field(default_factory=list)
    captured_count: int = 0
    total_count: int = 0
    error: str | None = None