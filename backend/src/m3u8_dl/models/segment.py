from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class SegmentStatus(str, Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    DONE = "done"
    FAILED = "failed"


@dataclass
class Segment:
    index: int
    url: str
    local_path: Path | None = None
    status: SegmentStatus = SegmentStatus.PENDING
    size_bytes: int = 0
    error: str | None = None