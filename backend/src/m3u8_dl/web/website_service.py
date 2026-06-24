import asyncio
import json
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from .website_repository import WebsiteRepository


class WebsiteNotFoundError(Exception):
    def __init__(self, website_id: int) -> None:
        super().__init__(f"website {website_id!r} not found")


class WebsiteService:
    def __init__(self, repo: WebsiteRepository) -> None:
        self._repo = repo
        self._subscribers: list[asyncio.Queue[str]] = []

    async def init(self) -> None:
        await self._repo.init()

    # ── SSE ──────────────────────────────────────────────────────────────────

    def subscribe(self) -> asyncio.Queue[str]:
        q: asyncio.Queue[str] = asyncio.Queue()
        self._subscribers.append(q)
        return q

    def unsubscribe(self, queue: asyncio.Queue[str]) -> None:
        try:
            self._subscribers.remove(queue)
        except ValueError:
            pass

    async def broadcast(self) -> None:
        websites = await self._repo.get_all()
        payload = json.dumps(websites)
        for q in list(self._subscribers):
            q.put_nowait(payload)

    # ── public operations ─────────────────────────────────────────────────────

    async def record_download(self, url: str, source: str, cdn_origin: str | None = None) -> None:
        origin, name = _extract_origin(url)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        await self._repo.upsert(origin, name, source, now)
        if cdn_origin:
            await self._repo.add_cdn(origin, cdn_origin)
        await self.broadcast()

    async def get_all(self) -> list[dict[str, Any]]:
        return await self._repo.get_all()

    async def get(self, website_id: int) -> dict[str, Any] | None:
        return await self._repo.get(website_id)

    async def update_rating(self, website_id: int, rating: int) -> None:
        if await self._repo.get(website_id) is None:
            raise WebsiteNotFoundError(website_id)
        await self._repo.update_rating(website_id, rating)
        await self.broadcast()

    async def set_working(self, website_id: int, working: bool) -> None:
        if await self._repo.get(website_id) is None:
            raise WebsiteNotFoundError(website_id)
        await self._repo.update_working(website_id, working)
        await self.broadcast()

    async def delete(self, website_id: int) -> None:
        await self._repo.delete(website_id)
        await self.broadcast()

    async def flush_not_working(self) -> int:
        count = await self._repo.flush_not_working()
        await self.broadcast()
        return count

    async def remove_cdn_for_website_origin(self, website_origin: str, cdn_origin: str) -> None:
        await self._repo.remove_cdn(website_origin, cdn_origin)
        await self.broadcast()

    async def flush_cdns(self, website_id: int) -> int:
        website = await self._repo.get(website_id)
        if website is None:
            raise WebsiteNotFoundError(website_id)
        count = await self._repo.flush_cdns(website["url"])
        await self.broadcast()
        return count


# ── helpers ───────────────────────────────────────────────────────────────────

def _extract_origin(url: str) -> tuple[str, str]:
    try:
        parsed = urlparse(url)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}", parsed.netloc
    except Exception:
        pass
    return url, url
