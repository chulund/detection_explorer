"""Run endpoints: idempotency by state, honest refusals, and resumable streams."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.runs import api as runs_api


def test_relative_state_root_is_resolved_from_the_repository():
    repository = Path(__file__).resolve().parents[2]
    assert runs_api.resolve_state_root("runs-test") == repository / "runs-test"


def test_run_keys_return_the_structured_provenance_used_for_identity(
        monkeypatch):
    inspected = {
        "available": True,
        "reproducible": True,
        "pipeline": {"configured_sha": "pin", "actual_sha": "pin",
                     "checkout_clean": True},
        "configuration": {"period": "both", "sha256": "config"},
        "ancillary": {"pixel_grid_sha256": "grid",
                      "sensor_geometry_sha256": "geometry"},
    }
    monkeypatch.setenv("BRIGHT_PIPELINE_PATH", "configured")
    monkeypatch.setattr(runs_api, "inspect_pipeline", lambda: inspected)

    _, frame_keys, frames, provenance = runs_api.keys_for("april-9-demo")

    assert len(frame_keys) == len(frames) == 6
    assert provenance["pipeline"]["actual_sha"] == "pin"
    assert set(provenance["inputs"]["manifest_sha256_by_frame"]) == set(frames)


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
    directory = runs_api.STATE_ROOT / "frames"
    directory.mkdir(parents=True, exist_ok=True)
    for frame, key in zip(run.frames, run.frame_keys):
        (directory / f"{key}.json").write_text(json.dumps({
            "frame": frame, "frame_key": key,
            "computed_at": "2026-04-09T05:00:00Z", "detections": [],
        }), encoding="utf-8")
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


def test_succeeded_run_with_missing_frame_cache_starts_a_new_attempt(
        client, monkeypatch, tmp_path):
    from app.runs.store import RunStore

    store = RunStore(tmp_path / "runs.sqlite")
    previous = store.create(
        run_key="same", scene="april-9-demo", frame_keys=["missing"],
        frames=["20260409040000"], provenance={"pipeline": {"actual_sha": "pin"}},
    )
    store.set_state(previous.id, "succeeded")
    submitted = []

    class Queue:
        async def submit(self, run):
            submitted.append(run)

    monkeypatch.setattr(runs_api, "STORE", store)
    monkeypatch.setattr(
        runs_api, "keys_for",
        lambda scene: ("same", ["missing"], ["20260409040000"],
                       {"pipeline": {"actual_sha": "pin"}}),
    )
    monkeypatch.setattr(runs_api, "build_queue", lambda: Queue())

    response = client.post("/api/v2/runs", json={"scene": "april-9-demo"})

    assert response.status_code == 202
    assert response.json()["delivery"] == "fresh"
    assert response.json()["attempt"] == 2
    assert submitted[0].parent_run_id == previous.id


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


def test_get_succeeded_run_reports_an_incomplete_cache(client, monkeypatch, tmp_path):
    from app.runs.store import RunStore

    store = RunStore(tmp_path / "runs.sqlite")
    run = store.create(
        run_key="incomplete", scene="april-9-demo", frame_keys=["missing"],
        frames=["20260409040000"],
    )
    store.set_state(run.id, "succeeded")
    monkeypatch.setattr(runs_api, "STORE", store)

    response = client.get(f"/api/v2/runs/{run.id}")

    assert response.status_code == 409
    assert "incomplete" in response.json()["detail"]


def test_cancelling_a_finished_run_is_a_noop(client, finished_run):
    body = client.post(f"/api/v2/runs/{finished_run.id}/cancel").json()
    assert body["state"] == "succeeded"


def test_cancel_without_a_built_queue_still_journals_a_terminal_event(
        client, monkeypatch, tmp_path):
    from app.runs.journal import Journal
    from app.runs.store import RunStore

    store = RunStore(tmp_path / "runs.sqlite")
    journal = Journal(tmp_path / "journals")
    run = store.create(
        run_key="cancel-no-queue", scene="april-9-demo",
        frame_keys=["fk"], frames=["20260409040000"],
    )
    monkeypatch.setattr(runs_api, "STORE", store)
    monkeypatch.setattr(runs_api, "JOURNAL", journal)
    monkeypatch.setattr(runs_api, "build_queue", lambda: None)

    response = client.post(f"/api/v2/runs/{run.id}/cancel")

    assert response.json()["state"] == "cancelled"
    [event] = journal.read(run.id)
    assert event.kind == "run.state"
    assert event.payload == {"state": "cancelled"}


@pytest.fixture
def run_with_cached_frame(finished_run):
    """A finished run whose first frame has a cache file, as a real run leaves behind."""
    directory = runs_api.STATE_ROOT / "frames"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{finished_run.frame_keys[0]}.json"
    path.write_text(json.dumps({
        "frame": "20260409040000",
        "frame_key": finished_run.frame_keys[0],
        "computed_at": "2026-04-09T05:00:00Z",
        # x,y join the pixel grid; 671,287 is a real pixel from the staged scene.
        "detections": [{"region": "nsw", "x": "671", "y": "287",
                        "lon": "148.0", "lat": "-32.0", "frp": "12.5",
                        "confidence": "80", "period": "day",
                        "dt": "20260409040000"}],
    }), encoding="utf-8")
    yield finished_run
    path.unlink(missing_ok=True)


def test_run_detections_carry_their_ahi_footprint(client, run_with_cached_frame):
    """Without this the BRIGHT layer has nothing with area to draw, only bare points.

    Skips rather than fails without the pixel grid: the fixture profile has no BRIGHT
    checkout, and that is a supported configuration.
    """
    from app.footprints.ahi import available as ahi_available

    if not ahi_available():
        pytest.skip("AHI pixel grid unavailable; research profile only")

    body = client.get(f"/api/v2/runs/{run_with_cached_frame.id}").json()
    [row] = body["detections"][0]["detections"]
    assert row["footprint"]["type"] == "Polygon"
    assert row["footprint_method"] == "ahi_grid"
    assert row["footprint_status"] == "validated"


def test_a_run_without_the_grid_still_returns_its_detections(
        client, run_with_cached_frame, monkeypatch):
    """Degrade, do not raise. The rows are real output even when the grid is absent."""
    from app.footprints import ahi

    monkeypatch.setattr(ahi, "pixel_footprint", lambda x, y: None)

    body = client.get(f"/api/v2/runs/{run_with_cached_frame.id}").json()
    [row] = body["detections"][0]["detections"]
    assert row["footprint"] is None
    assert row["lat"] == "-32.0"


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


def test_cancelled_run_state_is_a_terminal_stream_event():
    assert runs_api._is_terminal_event("run.state", {"state": "cancelled"})
    assert not runs_api._is_terminal_event("run.state", {"state": "running"})


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


def test_restart_recovery_appends_a_terminal_error_event():
    import anyio

    run = runs_api.STORE.create(
        run_key="test-journalled-orphan", scene="april-9-demo",
        frame_keys=["fk"], frames=["20260409040000"],
    )
    runs_api.STORE.set_state(run.id, "running")

    anyio.run(runs_api.recover_orphans_and_journal)

    [event] = runs_api.JOURNAL.read(run.id)
    assert event.kind == "run.error"
    assert event.payload == {"reason": "interrupted", "state": "failed"}
