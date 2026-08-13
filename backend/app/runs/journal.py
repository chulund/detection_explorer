"""The event journal behind resumable progress streams.

`sse-starlette` handles the transport: framing, keep-alive pings, disconnect detection. What
it cannot do is remember. A browser that reconnects sends `Last-Event-ID` and expects the
events it missed, and only the application knows what those were.

So every event is appended to `runs/<run_id>/events.jsonl` *before* it is emitted. Written
first, then sent: if the process dies between the two, a reconnecting client replays an event
it may already have seen, which is harmless. The reverse order would lose events outright.

Identifiers are monotonic integers from 1, per run. They are the resume cursor, so they must
never be reused or reordered.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class Event:
    id: int
    kind: str
    payload: dict
    at: str

    def to_dict(self) -> dict:
        return {"id": self.id, "kind": self.kind, "payload": self.payload, "at": self.at}


class Journal:
    """Append-only event log per run, plus live fan-out to connected listeners."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._listeners: dict[str, list[asyncio.Queue]] = {}
        self._counters: dict[str, int] = {}

    def path_for(self, run_id: str) -> Path:
        directory = self.root / run_id
        directory.mkdir(parents=True, exist_ok=True)
        return directory / "events.jsonl"

    def read(self, run_id: str, after: int = 0) -> list[Event]:
        """Journalled events with id greater than `after`, oldest first."""
        path = self.path_for(run_id)
        if not path.exists():
            return []
        events = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            body = json.loads(line)
            if body["id"] > after:
                events.append(Event(body["id"], body["kind"], body["payload"], body["at"]))
        return events

    def _next_id(self, run_id: str) -> int:
        if run_id not in self._counters:
            existing = self.read(run_id)
            self._counters[run_id] = existing[-1].id if existing else 0
        self._counters[run_id] += 1
        return self._counters[run_id]

    async def append(self, run_id: str, kind: str, payload: dict) -> Event:
        event = Event(
            id=self._next_id(run_id), kind=kind, payload=payload,
            at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        # Durable before visible. A replayed event is harmless; a lost one is not.
        with self.path_for(run_id).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.to_dict()) + "\n")

        for queue in list(self._listeners.get(run_id, [])):
            queue.put_nowait(event)
        return event

    # ------------------------------------------------------------------ listeners

    def subscribe(self, run_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._listeners.setdefault(run_id, []).append(queue)
        return queue

    def unsubscribe(self, run_id: str, queue: asyncio.Queue) -> None:
        listeners = self._listeners.get(run_id, [])
        if queue in listeners:
            listeners.remove(queue)
        if not listeners:
            self._listeners.pop(run_id, None)

    def listener_count(self, run_id: str) -> int:
        return len(self._listeners.get(run_id, []))
