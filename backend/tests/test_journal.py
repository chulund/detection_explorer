"""The journal, which is what makes a progress stream resumable.

sse-starlette handles framing, pings and disconnects. It cannot remember. A browser that
reconnects sends Last-Event-ID and expects what it missed, and only the application knows
what that was.
"""

from __future__ import annotations

import json

import pytest

from app.runs.journal import Journal

pytestmark = pytest.mark.anyio


@pytest.fixture
def journal(tmp_path) -> Journal:
    return Journal(tmp_path / "journals")


async def test_ids_start_at_one_and_increase(journal):
    for kind in ("run.state", "run.frame", "run.done"):
        await journal.append("r1", kind, {})
    assert [e.id for e in journal.read("r1")] == [1, 2, 3]


async def test_events_are_durable_before_they_are_visible(journal):
    """Written first, then emitted. A replayed event is harmless; a lost one is not."""
    await journal.append("r1", "run.frame", {"index": 1})
    path = journal.path_for("r1")
    body = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert body["kind"] == "run.frame" and body["payload"]["index"] == 1


async def test_read_after_returns_only_later_events(journal):
    for i in range(5):
        await journal.append("r1", "run.frame", {"index": i})
    assert [e.id for e in journal.read("r1", after=3)] == [4, 5]


async def test_counters_survive_a_restart(tmp_path):
    """A fresh Journal over the same directory must not restart ids at 1."""
    first = Journal(tmp_path / "j")
    await first.append("r1", "run.state", {})
    await first.append("r1", "run.frame", {})

    second = Journal(tmp_path / "j")
    event = await second.append("r1", "run.done", {})
    assert event.id == 3
    assert [e.id for e in second.read("r1")] == [1, 2, 3]


async def test_runs_have_independent_id_sequences(journal):
    await journal.append("r1", "run.state", {})
    event = await journal.append("r2", "run.state", {})
    assert event.id == 1


async def test_listeners_receive_live_events(journal):
    queue = journal.subscribe("r1")
    await journal.append("r1", "run.frame", {"index": 1})
    event = await queue.get()
    assert event.kind == "run.frame"
    journal.unsubscribe("r1", queue)
    assert journal.listener_count("r1") == 0


async def test_unsubscribing_one_listener_leaves_the_others(journal):
    a = journal.subscribe("r1")
    b = journal.subscribe("r1")
    journal.unsubscribe("r1", a)
    await journal.append("r1", "run.done", {})
    assert journal.listener_count("r1") == 1
    assert (await b.get()).kind == "run.done"


async def test_reading_an_unknown_run_is_empty_not_an_error(journal):
    assert journal.read("never-existed") == []
