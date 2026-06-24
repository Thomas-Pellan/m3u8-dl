import json
from pathlib import Path
from typing import Any

import aiosqlite

_COLUMNS = (
    "id", "status", "url", "output_name", "mode", "quality", "parallel",
    "started_at", "scheduled_at", "progress", "error", "output", "logs",
)


class JobRepository:
    def __init__(self, db_path: Path) -> None:
        self._path = db_path

    async def init(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._path) as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id           TEXT PRIMARY KEY,
                    status       TEXT NOT NULL,
                    url          TEXT NOT NULL,
                    output_name  TEXT NOT NULL,
                    mode         TEXT NOT NULL,
                    quality      TEXT NOT NULL,
                    parallel     INTEGER NOT NULL,
                    started_at   TEXT NOT NULL,
                    scheduled_at TEXT,
                    progress     INTEGER,
                    error        TEXT,
                    output       TEXT,
                    logs         TEXT NOT NULL DEFAULT '[]'
                )
            """)
            await conn.commit()

    def _row_to_dict(self, row: tuple) -> dict[str, Any]:
        d = dict(zip(_COLUMNS, row))
        d["logs"] = json.loads(d["logs"] or "[]")
        return d

    async def get_all(self) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self._path) as conn:
            async with conn.execute(
                f"SELECT {', '.join(_COLUMNS)} FROM jobs ORDER BY started_at"
            ) as cur:
                rows = await cur.fetchall()
        return [self._row_to_dict(r) for r in rows]

    async def get(self, job_id: str) -> dict[str, Any] | None:
        async with aiosqlite.connect(self._path) as conn:
            async with conn.execute(
                f"SELECT {', '.join(_COLUMNS)} FROM jobs WHERE id = ?", (job_id,)
            ) as cur:
                row = await cur.fetchone()
        return self._row_to_dict(row) if row else None

    async def insert(self, job: dict[str, Any]) -> None:
        placeholders = ", ".join("?" * len(_COLUMNS))
        async with aiosqlite.connect(self._path) as conn:
            await conn.execute(
                f"INSERT INTO jobs ({', '.join(_COLUMNS)}) VALUES ({placeholders})",
                tuple(
                    json.dumps(job[c]) if c == "logs" else job.get(c)
                    for c in _COLUMNS
                ),
            )
            await conn.commit()

    async def update(self, job_id: str, **fields: Any) -> None:
        if not fields:
            return
        if "logs" in fields:
            fields["logs"] = json.dumps(fields["logs"])
        clause = ", ".join(f"{k} = ?" for k in fields)
        async with aiosqlite.connect(self._path) as conn:
            await conn.execute(
                f"UPDATE jobs SET {clause} WHERE id = ?",
                (*fields.values(), job_id),
            )
            await conn.commit()

    async def delete(self, job_id: str) -> None:
        async with aiosqlite.connect(self._path) as conn:
            await conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
            await conn.commit()

    async def mark_interrupted(self) -> None:
        """Mark any running/pending jobs as failed — called once on server startup."""
        async with aiosqlite.connect(self._path) as conn:
            await conn.execute(
                "UPDATE jobs SET status = 'error', error = 'Interrupted (server restarted)' "
                "WHERE status IN ('running', 'pending')"
            )
            await conn.commit()

    async def count_by_status(self, status: str) -> int:
        async with aiosqlite.connect(self._path) as conn:
            async with conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE status = ?", (status,)
            ) as cur:
                row = await cur.fetchone()
        return row[0] if row else 0
