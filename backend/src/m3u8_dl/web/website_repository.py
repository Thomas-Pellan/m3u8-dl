from pathlib import Path
from typing import Any

import aiosqlite

_COLUMNS = ("id", "url", "name", "rating", "working", "last_used_at", "use_count", "source")


class WebsiteRepository:
    def __init__(self, db_path: Path) -> None:
        self._path = db_path

    async def init(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._path) as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS websites (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    url          TEXT NOT NULL UNIQUE,
                    name         TEXT NOT NULL,
                    rating       INTEGER NOT NULL DEFAULT 0,
                    working      INTEGER NOT NULL DEFAULT 1,
                    last_used_at TEXT NOT NULL,
                    use_count    INTEGER NOT NULL DEFAULT 1,
                    source       TEXT NOT NULL DEFAULT 'simple'
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS website_cdns (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    website_url TEXT NOT NULL,
                    cdn_origin  TEXT NOT NULL,
                    UNIQUE(website_url, cdn_origin)
                )
            """)
            await conn.commit()

    def _row_to_dict(self, row: tuple) -> dict[str, Any]:
        d = dict(zip(_COLUMNS, row))
        d["working"] = bool(d["working"])
        return d

    async def get_all(self) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self._path) as conn:
            async with conn.execute(
                f"SELECT {', '.join(_COLUMNS)} FROM websites ORDER BY last_used_at DESC"
            ) as cur:
                rows = await cur.fetchall()

            async with conn.execute(
                "SELECT website_url, cdn_origin FROM website_cdns ORDER BY website_url, cdn_origin"
            ) as cur:
                cdn_rows = await cur.fetchall()

        cdns_by_url: dict[str, list[str]] = {}
        for url, origin in cdn_rows:
            cdns_by_url.setdefault(url, []).append(origin)

        result = []
        for r in rows:
            d = self._row_to_dict(r)
            d["cdns"] = cdns_by_url.get(d["url"], [])
            result.append(d)
        return result

    async def get(self, website_id: int) -> dict[str, Any] | None:
        async with aiosqlite.connect(self._path) as conn:
            async with conn.execute(
                f"SELECT {', '.join(_COLUMNS)} FROM websites WHERE id = ?", (website_id,)
            ) as cur:
                row = await cur.fetchone()
        return self._row_to_dict(row) if row else None

    async def upsert(self, url: str, name: str, source: str, last_used_at: str) -> None:
        async with aiosqlite.connect(self._path) as conn:
            await conn.execute(
                """
                INSERT INTO websites (url, name, rating, working, last_used_at, use_count, source)
                VALUES (?, ?, 0, 1, ?, 1, ?)
                ON CONFLICT(url) DO UPDATE SET
                    last_used_at = excluded.last_used_at,
                    use_count    = use_count + 1,
                    source       = excluded.source
                """,
                (url, name, last_used_at, source),
            )
            await conn.commit()

    async def update_rating(self, website_id: int, rating: int) -> None:
        async with aiosqlite.connect(self._path) as conn:
            await conn.execute(
                "UPDATE websites SET rating = ? WHERE id = ?", (rating, website_id)
            )
            await conn.commit()

    async def update_working(self, website_id: int, working: bool) -> None:
        async with aiosqlite.connect(self._path) as conn:
            await conn.execute(
                "UPDATE websites SET working = ? WHERE id = ?",
                (1 if working else 0, website_id),
            )
            await conn.commit()

    async def delete(self, website_id: int) -> None:
        async with aiosqlite.connect(self._path) as conn:
            await conn.execute("DELETE FROM websites WHERE id = ?", (website_id,))
            await conn.commit()

    async def flush_not_working(self) -> int:
        async with aiosqlite.connect(self._path) as conn:
            cur = await conn.execute("DELETE FROM websites WHERE working = 0")
            await conn.commit()
            return cur.rowcount

    # ── CDN methods ───────────────────────────────────────────────────────────

    async def add_cdn(self, website_url: str, cdn_origin: str) -> None:
        async with aiosqlite.connect(self._path) as conn:
            await conn.execute(
                "INSERT OR IGNORE INTO website_cdns (website_url, cdn_origin) VALUES (?, ?)",
                (website_url, cdn_origin),
            )
            await conn.commit()

    async def remove_cdn(self, website_url: str, cdn_origin: str) -> None:
        async with aiosqlite.connect(self._path) as conn:
            await conn.execute(
                "DELETE FROM website_cdns WHERE website_url = ? AND cdn_origin = ?",
                (website_url, cdn_origin),
            )
            await conn.commit()

    async def flush_cdns(self, website_url: str) -> int:
        async with aiosqlite.connect(self._path) as conn:
            cur = await conn.execute(
                "DELETE FROM website_cdns WHERE website_url = ?", (website_url,)
            )
            await conn.commit()
            return cur.rowcount
