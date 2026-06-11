from dataclasses import dataclass, field

from .segment import Segment


@dataclass
class Variant:
    url: str
    bandwidth: int
    resolution: str | None = None
    codecs: str | None = None


@dataclass
class Playlist:
    url: str
    base_url: str
    segments: list[Segment] = field(default_factory=list)
    variants: list[Variant] = field(default_factory=list)
    is_master: bool = False