from urllib.parse import urljoin

import m3u8

from ..models.playlist import Playlist, Variant
from ..models.segment import Segment


def parse_playlist(url: str, content: str) -> Playlist:
    parsed = m3u8.loads(content)
    base_url = url.rsplit("/", 1)[0] + "/"
    playlist = Playlist(url=url, base_url=base_url)

    if parsed.is_variant:
        playlist.is_master = True
        for p in parsed.playlists:
            info = p.stream_info
            resolution = (
                f"{info.resolution[0]}x{info.resolution[1]}"
                if info.resolution
                else None
            )
            playlist.variants.append(
                Variant(
                    url=urljoin(base_url, p.uri),
                    bandwidth=info.bandwidth,
                    resolution=resolution,
                    codecs=info.codecs,
                )
            )
    else:
        for i, seg in enumerate(parsed.segments):
            playlist.segments.append(
                Segment(index=i, url=urljoin(base_url, seg.uri))
            )

    return playlist


def select_variant(playlist: Playlist, quality: str) -> Variant | None:
    if not playlist.variants:
        return None

    if quality == "best":
        return max(playlist.variants, key=lambda v: v.bandwidth)
    if quality == "worst":
        return min(playlist.variants, key=lambda v: v.bandwidth)

    # Try to match by resolution string (e.g. "1920x1080")
    for v in playlist.variants:
        if v.resolution and quality in v.resolution:
            return v

    return max(playlist.variants, key=lambda v: v.bandwidth)
