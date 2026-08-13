"""Run persistence: states, attempts, and the lineage a retry must not erase.

Follows the July feed's store pattern (`sqlite3.connect(..., check_same_thread=False)`,
`row_factory = sqlite3.Row`, schema applied on construction) so the two codebases read alike.

The design point worth stating: a retry after failure creates a **new attempt** rather than
resetting the old run. Overwriting would destroy the record of what went wrong, and on a
deliverable whose whole claim is that the computation genuinely ran, the failure history is
evidence rather than noise.
"""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

STATES = ("queued", "running", "succeeded", "failed", "cancelled")
TERMINAL = frozenset({"succeeded", "failed", "cancelled"})

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    run_key TEXT NOT NULL,
    scene TEXT NOT NULL,
    frame_keys TEXT NOT NULL,
    frames TEXT NOT NULL,
    state TEXT NOT NULL,
    attempt INTEGER NOT NULL DEFAULT 1,
    parent_run_id TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_key ON runs (run_key, created_at);
"""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class Run:
    id: str
    run_key: str
    scene: str
    frame_keys: list[str]
    frames: list[str]
    state: str
    attempt: int
    parent_run_id: str | None
    error: str | None
    created_at: str
    updated_at: str

    @property
    def terminal(self) -> bool:
        return self.state in TERMINAL

    def to_dict(self) -> dict:
        return {
            "run_id": self.id, "run_key": self.run_key, "scene": self.scene,
            "frames": self.frames, "state": self.state, "attempt": self.attempt,
            "parent_run_id": self.parent_run_id, "error": self.error,
            "created_at": self.created_at, "updated_at": self.updated_at,
        }


class RunStore:
    def __init__(self, path: str | Path) -> None:
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)

    # ------------------------------------------------------------------ writes

    def create(self, *, run_key: str, scene: str, frame_keys: list[str],
               frames: list[str], attempt: int = 1,
               parent_run_id: str | None = None) -> Run:
        run_id = uuid.uuid4().hex
        now = _now()
        with self._conn:
            self._conn.execute(
                "INSERT INTO runs (id, run_key, scene, frame_keys, frames, state, "
                "attempt, parent_run_id, error, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (run_id, run_key, scene, "\n".join(frame_keys), "\n".join(frames),
                 "queued", attempt, parent_run_id, None, now, now))
        return self.get(run_id)

    def set_state(self, run_id: str, state: str, error: str | None = None) -> Run:
        if state not in STATES:
            raise ValueError(f"unknown state {state!r}; expected one of {STATES}")
        with self._conn:
            self._conn.execute(
                "UPDATE runs SET state = ?, error = ?, updated_at = ? WHERE id = ?",
                (state, error, _now(), run_id))
        return self.get(run_id)

    def next_attempt(self, run_key: str) -> Run:
        """Start a fresh attempt from the latest run under this key.

        The previous attempt is left exactly as it was. Its failure is part of the
        record of what the pipeline actually did.
        """
        previous = self.find_by_run_key(run_key)
        if previous is None:
            raise KeyError(f"no run with key {run_key!r}")
        return self.create(
            run_key=run_key, scene=previous.scene, frame_keys=previous.frame_keys,
            frames=previous.frames, attempt=previous.attempt + 1,
            parent_run_id=previous.id)

    # ------------------------------------------------------------------ reads

    def _row(self, row: sqlite3.Row) -> Run:
        return Run(
            id=row["id"], run_key=row["run_key"], scene=row["scene"],
            frame_keys=row["frame_keys"].split("\n") if row["frame_keys"] else [],
            frames=row["frames"].split("\n") if row["frames"] else [],
            state=row["state"], attempt=row["attempt"],
            parent_run_id=row["parent_run_id"], error=row["error"],
            created_at=row["created_at"], updated_at=row["updated_at"])

    def get(self, run_id: str) -> Run:
        row = self._conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(f"no run {run_id!r}")
        return self._row(row)

    def find_by_run_key(self, run_key: str) -> Run | None:
        """The most recent attempt under this key, whatever its state."""
        row = self._conn.execute(
            "SELECT * FROM runs WHERE run_key = ? ORDER BY attempt DESC, created_at DESC "
            "LIMIT 1", (run_key,)).fetchone()
        return self._row(row) if row else None

    def orphans(self) -> list[Run]:
        """Runs left mid-flight by a restart: `running` with no live worker."""
        rows = self._conn.execute(
            "SELECT * FROM runs WHERE state IN ('queued','running')").fetchall()
        return [self._row(r) for r in rows]

    def recover_orphans(self) -> list[Run]:
        """Mark interrupted runs failed on startup, preserving their journals."""
        return [self.set_state(run.id, "failed", "interrupted") for run in self.orphans()]
