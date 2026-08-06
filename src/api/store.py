from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import closing
from pathlib import Path
from typing import Optional

from .models import ChatMessage, RunDetail, RunStepEvent, RunSummary, StepPayload, utc_now_iso


class RunStore:
    """SQLite-backed persistence for run metadata and step events."""

    def __init__(self, db_path: str | Path = "run_visualizer.db") -> None:
        self.db_path = str(db_path)
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with closing(self._connect()) as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    arm TEXT NOT NULL,
                    task_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    duration_ms INTEGER,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    pass_fail INTEGER
                );
                CREATE TABLE IF NOT EXISTS steps (
                    step_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    parent_step_id TEXT,
                    arm TEXT NOT NULL,
                    type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    title TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (run_id, step_id),
                    FOREIGN KEY (run_id) REFERENCES runs(run_id)
                );
                CREATE INDEX IF NOT EXISTS idx_steps_run ON steps(run_id, started_at);
                CREATE TABLE IF NOT EXISTS messages (
                    message_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES runs(run_id)
                );
                CREATE INDEX IF NOT EXISTS idx_messages_run ON messages(run_id, timestamp);
                """
            )
            conn.commit()

    def create_run(
        self,
        run_id: str,
        arm: str,
        task_name: str,
        started_at: Optional[str] = None,
    ) -> None:
        with self._lock, closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO runs (run_id, arm, task_name, status, started_at)
                VALUES (?, ?, ?, 'running', ?)
                ON CONFLICT(run_id) DO NOTHING
                """,
                (run_id, arm, task_name, started_at or utc_now_iso()),
            )
            conn.commit()

    def update_run_status(
        self,
        run_id: str,
        status: str,
        duration_ms: Optional[int] = None,
        pass_fail: Optional[bool] = None,
        ended_at: Optional[str] = None,
    ) -> None:
        with self._lock, closing(self._connect()) as conn:
            conn.execute(
                """
                UPDATE runs
                SET status = ?, duration_ms = COALESCE(?, duration_ms),
                    pass_fail = COALESCE(?, pass_fail),
                    ended_at = COALESCE(?, ended_at)
                WHERE run_id = ?
                """,
                (
                    status,
                    duration_ms,
                    None if pass_fail is None else int(pass_fail),
                    ended_at,
                    run_id,
                ),
            )
            conn.commit()

    def upsert_step(self, event: RunStepEvent) -> None:
        with self._lock, closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO steps (
                    step_id, run_id, parent_step_id, arm, type, status,
                    title, started_at, ended_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id, step_id) DO UPDATE SET
                    parent_step_id = excluded.parent_step_id,
                    status = excluded.status,
                    title = excluded.title,
                    ended_at = excluded.ended_at,
                    payload_json = excluded.payload_json
                """,
                (
                    event.step_id,
                    event.run_id,
                    event.parent_step_id,
                    event.arm,
                    event.type,
                    event.status,
                    event.title,
                    event.started_at,
                    event.ended_at,
                    event.payload.model_dump_json(),
                ),
            )
            conn.commit()

    def list_runs(self) -> list[RunSummary]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT * FROM runs ORDER BY started_at DESC"
            ).fetchall()
        return [
            RunSummary(
                run_id=row["run_id"],
                arm=row["arm"],
                task_name=row["task_name"],
                status=row["status"],
                duration_ms=row["duration_ms"],
                started_at=row["started_at"],
                pass_fail=bool(row["pass_fail"]) if row["pass_fail"] is not None else None,
            )
            for row in rows
        ]

    def get_run(self, run_id: str) -> Optional[RunDetail]:
        with closing(self._connect()) as conn:
            run_row = conn.execute(
                "SELECT * FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if run_row is None:
                return None
            step_rows = conn.execute(
                "SELECT * FROM steps WHERE run_id = ? ORDER BY started_at ASC",
                (run_id,),
            ).fetchall()

        steps = [
            RunStepEvent(
                run_id=row["run_id"],
                step_id=row["step_id"],
                parent_step_id=row["parent_step_id"],
                arm=row["arm"],
                type=row["type"],
                status=row["status"],
                title=row["title"],
                started_at=row["started_at"],
                ended_at=row["ended_at"],
                payload=StepPayload.model_validate(json.loads(row["payload_json"])),
            )
            for row in step_rows
        ]
        return RunDetail(
            run_id=run_row["run_id"],
            arm=run_row["arm"],
            task_name=run_row["task_name"],
            status=run_row["status"],
            duration_ms=run_row["duration_ms"],
            started_at=run_row["started_at"],
            ended_at=run_row["ended_at"],
            pass_fail=bool(run_row["pass_fail"]) if run_row["pass_fail"] is not None else None,
            steps=steps,
        )

    def add_message(self, message: ChatMessage) -> None:
        with self._lock, closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO messages (message_id, run_id, role, content, timestamp)
                VALUES (?, ?, ?, ?, ?)
                """,
                (message.message_id, message.run_id, message.role, message.content, message.timestamp),
            )
            conn.commit()

    def get_messages(self, run_id: str) -> list[ChatMessage]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT * FROM messages WHERE run_id = ? ORDER BY timestamp ASC",
                (run_id,),
            ).fetchall()
        return [
            ChatMessage(
                run_id=row["run_id"],
                message_id=row["message_id"],
                role=row["role"],
                content=row["content"],
                timestamp=row["timestamp"],
            )
            for row in rows
        ]
