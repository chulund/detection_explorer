"""Run endpoints: idempotency by state, honest refusals, and resumable streams."""

from __future__ import annotations

import json

import pytest

from app.runs import api as runs_api


def _sse_events(text: str) -> list[dict]:
    """Parse an SSE body into {id, event, data} dicts."""
    events, current = [], {}
    for line in text.splitlines():
        if not line.strip():
            if current:
                events.append(current)
                current = {}
            continue
        if ":" not in line:
            continue
        field, _, value = line.partition(":")
        current[field.strip()] = value.strip()
    if current:
        events.append(current)
    return [e for e in events if "id" in e]


@pytest.fixture
def finished_run():
    """A succeeded run with a journal, created directly rather than through the queue."""
    run = runs_api.STORE.create(run_key="test-finished", scene="april-9-demo",
                                frame_keys=["fk1", "fk2"],
                                frames=["20260409040000", "20260409041000"])
    import anyio

    async def _seed():
        await runs_api.JOURNAL.append(run.id, "run.state", {"state": "running"})
        await runs_api.JOURNAL.append(run.id, "run.frame", {"index": 1, "of": 2})
        await runs_api.JOURNAL.append(run.id, "run.frame", {"index": 2, "of": 2})
        await runs_api.JOURNAL.append(run.id, "run.done", {"state": "succeeded"})

    anyio.run(_seed)
    runs_api.STORE.set_state(run.id, "succeeded")
    return runs_api.STORE.get(run.id)


# ------------------------------------------------------------------ refusals

def test_a_run_on_the_current_scene_is_refused(client):
    """The current scene is retrieved, not computed. Refusing is honest; pretending
    to compute live data would not be."""
    response = client.post("/api/v2/runs", json={"scene": "current"})
    assert response.status_code == 400
    assert "retrieved, not computed" in response.json()["detail"]


def test_an_unknown_scene_is_a_404(client):
    assert client.post("/api/v2/runs", json={"scene": "nope"}).status_code == 404


def test_without_a_pipeline_the_service_says_so_rather_than_failing_obscurely(
        client, monkeypatch, tmp_path):
    """The fixture profile has no BRIGHT checkout; the refusal must explain that.

    Uses a throwaway store. The real one persists across runs, so a previously
    succeeded run for this scene would be returned as a cached result and the refusal
    would never be reached — which is exactly what happened once a genuine run had been
    executed against the running service.
    """
    from app.runs.store import RunStore

    monkeypatch.delenv("BRIGHT_PIPELINE_PATH", raising=False)
    monkeypatch.setattr(runs_api, "QUEUE", None)
    monkeypatch.setattr(runs_api, "STORE", RunStore(tmp_path / "runs.sqlite"))

    response = client.post("/api/v2/runs", json={"scene": "april-9-demo"})
    assert response.status_code == 503
    assert "BRIGHT_PIPELINE_PATH" in response.json()["detail"]


def test_unknown_run_ids_are_404(client):
    assert client.get("/api/v2/runs/nope").status_code == 404
    assert client.post("/api/v2/runs/nope/cancel").status_code == 404
    assert client.get("/api/v2/runs/nope/events").status_code == 404


# ------------------------------------------------------------------ inspection

def test_get_run_reports_state_and_lineage(client, finished_run):
    body = client.get(f"/api/v2/runs/{finished_run.id}").json()
    assert body["state"] == "succeeded"
    assert body["attempt"] == 1
    assert body["frames"] == ["20260409040000", "20260409041000"]


def test_cancelling_a_finished_run_is_a_noop(client, finished_run):
    body = client.post(f"/api/v2/runs/{finished_run.id}/cancel").json()
    assert body["state"] == "succeeded"


# ------------------------------------------------------------------ streaming

def test_the_stream_replays_the_whole_journal_by_default(client, finished_run):
    with client.stream("GET", f"/api/v2/runs/{finished_run.id}/events") as response:
        events = _sse_events("".join(response.iter_text()))
    assert [e["id"] for e in events] == ["1", "2", "3", "4"]
    assert events[-1]["event"] == "run.done"


def test_last_event_id_resumes_rather_than_repeating(client, finished_run):
    """The whole point of the journal: a reconnect gets what it missed, not everything."""
    with client.stream("GET", f"/api/v2/runs/{finished_run.id}/events",
                       headers={"Last-Event-ID": "2"}) as response:
        events = _sse_events("".join(response.iter_text()))
    assert [e["id"] for e in events] == ["3", "4"]


def test_event_payloads_survive_the_round_trip(client, finished_run):
    with client.stream("GET", f"/api/v2/runs/{finished_run.id}/events") as response:
        events = _sse_events("".join(response.iter_text()))
    frames = [json.loads(e["data"]) for e in events if e["event"] == "run.frame"]
    assert [f["index"] for f in frames] == [1, 2]


def test_a_terminal_run_closes_the_stream_rather_than_hanging(client, finished_run):
    with client.stream("GET", f"/api/v2/runs/{finished_run.id}/events") as response:
        text = "".join(response.iter_text())
    assert "run.done" in text


# ------------------------------------------------------------------ recovery

def test_restart_marks_in_flight_runs_interrupted():
    """Nothing can still be running after a restart; the journal is preserved."""
    run = runs_api.STORE.create(run_key="test-orphan", scene="april-9-demo",
                                frame_keys=["fk"], frames=["20260409040000"])
    runs_api.STORE.set_state(run.id, "running")

    runs_api.recover_orphans()

    recovered = runs_api.STORE.get(run.id)
    assert recovered.state == "failed"
    assert recovered.error == "interrupted"
