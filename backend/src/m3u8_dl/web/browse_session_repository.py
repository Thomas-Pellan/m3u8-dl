import json
from pathlib import Path
from typing import Any

import aiosqlite

_COLUMNS = (
    "id", "status", "url", "created_at", "closed_at",
    "error", "candidates", "downloads", "close_when_done",
)


class BrowseSessionRepository:
    def __init__(self, db_path: Path) -> None:
        self._path = db_path

    async def init(self) -> None:
        async with aiosqlite.connect(self._path) as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS browse_sessions (
                    id              TEXT PRIMARY KEY,
                    status          TEXT NOT NULL,
                    url             TEXT NOT NULL,
                    created_at      TEXT NOT NULL,
                    closed_at       TEXT,
                    error           TEXT,
                    candidates      TEXT NOT NULL DEFAULT '[]',
                    downloads       TEXT NOT NULL DEFAULT '[]',
                    close_when_done INTEGER NOT NULL DEFAULT 0
                )
            """)
            await conn.commit()
            # Migrations for existing databases
            for col_sql in (
                "ALTER TABLE browse_sessions ADD COLUMN downloads TEXT NOT NULL DEFAULT '[]'",
                "ALTER TABLE browse_sessions ADD COLUMN close_when_done INTEGER NOT NULL DEFAULT 0",
            ):
                try:
                    await conn.execute(col_sql)
                    await conn.commit()
                except Exception:
                    pass

    def _row_to_dict(self, row: tuple) -> dict[str, Any]:
        d = dict(zip(_COLUMNS, row))
        d["candidates"] = json.loads(d.get("candidates") or "[]")
        d["downloads"] = json.loads(d.get("downloads") or "[]")
        d["close_when_done"] = bool(d.get("close_when_done", 0))
        return d

    async def get_all(self) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self._path) as conn:
            async with conn.execute(
                f"SELECT {', '.join(_COLUMNS)} FROM browse_sessions ORDER BY created_at DESC"
            ) as cur:
                rows = await cur.fetchall()
        return [self._row_to_dict(r) for r in rows]

    async def get(self, session_id: str) -> dict[str, Any] | None:
        async with aiosqlite.connect(self._path) as conn:
            async with conn.execute(
                f"SELECT {', '.join(_COLUMNS)} FROM browse_sessions WHERE id = ?",
                (session_id,),
            ) as cur:
                row = await cur.fetchone()
        return self._row_to_dict(row) if row else None

    async def get_active(self) -> dict[str, Any] | None:
        async with aiosqlite.connect(self._path) as conn:
            async with conn.execute(
                f"SELECT {', '.join(_COLUMNS)} FROM browse_sessions "
                "WHERE status IN ('opening', 'active') LIMIT 1"
            ) as cur:
                row = await cur.fetchone()
        return self._row_to_dict(row) if row else None

    async def insert(self, session: dict[str, Any]) -> None:
        async with aiosqlite.connect(self._path) as conn:
            await conn.execute(
                f"INSERT INTO browse_sessions ({', '.join(_COLUMNS)}) "
                f"VALUES ({', '.join('?' * len(_COLUMNS))})",
                (
                    session.get("id"),
                    session.get("status"),
                    session.get("url"),
                    session.get("created_at"),
                    session.get("closed_at"),
                    session.get("error"),
                    json.dumps(session.get("candidates", [])),
                    json.dumps(session.get("downloads", [])),
                    1 if session.get("close_when_done", False) else 0,
                ),
            )
            await conn.commit()

    async def update(self, session_id: str, **fields: Any) -> None:
        if not fields:
            return
        if "candidates" in fields:
            fields["candidates"] = json.dumps(fields["candidates"])
        if "downloads" in fields:
            fields["downloads"] = json.dumps(fields["downloads"])
        if "close_when_done" in fields:
            fields["close_when_done"] = 1 if fields["close_when_done"] else 0
        clause = ", ".join(f"{k} = ?" for k in fields)
        async with aiosqlite.connect(self._path) as conn:
            await conn.execute(
                f"UPDATE browse_sessions SET {clause} WHERE id = ?",
                (*fields.values(), session_id),
            )
            await conn.commit()

    async def delete(self, session_id: str) -> None:
        async with aiosqlite.connect(self._path) as conn:
            await conn.execute("DELETE FROM browse_sessions WHERE id = ?", (session_id,))
            await conn.commit()

    async def delete_all(self) -> None:
        async with aiosqlite.connect(self._path) as conn:
            await conn.execute("DELETE FROM browse_sessions")
            await conn.commit()
