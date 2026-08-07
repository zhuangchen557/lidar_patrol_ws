from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path
from typing import Any


class HistoryRepository:
    def __init__(self, path: Path) -> None:
        self.path = path

    async def initialize(self) -> None:
        await asyncio.to_thread(self._initialize_sync)

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize_sync(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS robot_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp INTEGER NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_robot_history_timestamp "
                "ON robot_history(timestamp)"
            )

    async def append(self, payload: dict[str, Any]) -> None:
        await asyncio.to_thread(self._append_sync, payload)

    def _append_sync(self, payload: dict[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO robot_history(timestamp, payload) VALUES (?, ?)",
                (int(payload["timestamp"]), json.dumps(payload, ensure_ascii=False)),
            )

    async def latest(self, limit: int) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._latest_sync, limit)

    def _latest_sync(self, limit: int) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM robot_history ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [json.loads(row["payload"]) for row in reversed(rows)]
