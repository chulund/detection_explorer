"""Run keys and run persistence.

The keys exist so that a cached frame is only reused when it would genuinely be identical.
The store exists so that a retry does not erase the evidence of what failed.
"""

from __future__ import annotations

import json

import pytest

from app.runs.keys import config_hash, frame_key, manifest_checksum, run_key
from app.runs.store import RunStore

BASE = dict(scene="april-9-demo", frame_ts="20260409040000", pipeline_sha="abc123",
            config_hash="cfg1", manifest_checksum="mfst1", schema_version="2.0")


@pytest.fixture
def store(tmp_path) -> RunStore:
    return RunStore(tmp_path / "runs.sqlite")


# ------------------------------------------------------------------ keys

def test_identical_inputs_give_an_identical_key():
    assert frame_key(**BASE) == frame_key(**BASE)


@pytest.mark.parametrize("field,value", [
    ("config_hash", "cfg2"),
    ("pipeline_sha", "def456"),
    ("manifest_checksum", "mfst2"),
    ("schema_version", "2.1"),
    ("frame_ts", "20260409041000"),
    ("scene", "current"),
])
def test_every_component_invalidates_the_frame(field, value):
    """A cached frame must not survive a change to anything that produced it."""
    assert frame_key(**BASE) != frame_key(**{**BASE, field: value})


def test_run_key_depends_on_frame_order():
    a = frame_key(**BASE)
    b = frame_key(**{**BASE, "frame_ts": "20260409041000"})
    assert run_key([a, b]) != run_key([b, a])


def test_key_components_cannot_collide_by_concatenation():
    """'ab'+'c' must not hash the same as 'a'+'bc'."""
    assert (frame_key(**{**BASE, "scene": "ab", "frame_ts": "c"})
            != frame_key(**{**BASE, "scene": "a", "frame_ts": "bc"}))


def test_config_hash_is_order_independent():
    assert config_hash({"a": 1, "b": 2}) == config_hash({"b": 2, "a": 1})


def test_manifest_checksum_reads_the_tracked_digests(tmp_path):
    path = tmp_path / "m.json"
    path.write_text(json.dumps({"frames": [
        {"frame": "20260409040000", "days": [{"sha256": "aa"}, {"sha256": "bb"}]}]}))
    first = manifest_checksum(path, "20260409040000")
    path.write_text(json.dumps({"frames": [
        {"frame": "20260409040000", "days": [{"sha256": "aa"}, {"sha256": "cc"}]}]}))
    assert manifest_checksum(path, "20260409040000") != first


def test_missing_frame_in_manifest_is_reported_not_faked(tmp_path):
    path = tmp_path / "m.json"
    path.write_text(json.dumps({"frames": []}))
    assert manifest_checksum(path, "20260409040000") == "absent"


def test_the_real_manifest_is_readable():
    """Guards the staging output against a format drift that would break caching."""
    from pathlib import Path
    real = Path(__file__).resolve().parents[2] / "manifests" / "april-9-demo.json"
    digest = manifest_checksum(real, "20260409040000")
    assert digest != "absent" and len(digest) == 64


# ------------------------------------------------------------------ store

def _make(store: RunStore, key: str = "k1") -> "object":
    return store.create(run_key=key, scene="april-9-demo",
                        frame_keys=["f1", "f2"], frames=["20260409040000",
                                                         "20260409041000"])


def test_a_new_run_starts_queued_as_attempt_one(store):
    run = _make(store)
    assert run.state == "queued" and run.attempt == 1
    assert run.parent_run_id is None


def test_find_by_run_key_returns_the_latest_attempt(store):
    first = _make(store)
    store.set_state(first.id, "failed", "boom")
    second = store.next_attempt("k1")
    assert store.find_by_run_key("k1").id == second.id


def test_retry_preserves_the_failed_attempt(store):
    """The failure is evidence of what the pipeline did, not noise to overwrite."""
    first = _make(store)
    store.set_state(first.id, "failed", "boom")
    second = store.next_attempt("k1")
    assert second.id != first.id
    assert second.attempt == 2 and second.parent_run_id == first.id
    assert store.get(first.id).state == "failed"
    assert store.get(first.id).error == "boom"


def test_frames_and_frame_keys_survive_a_round_trip(store):
    run = _make(store)
    fetched = store.get(run.id)
    assert fetched.frames == ["20260409040000", "20260409041000"]
    assert fetched.frame_keys == ["f1", "f2"]


def test_structured_provenance_survives_a_round_trip(store):
    provenance = {
        "pipeline": {"configured_sha": "abc123", "actual_sha": "abc123"},
        "configuration": {"sha256": "cfg"},
        "ancillary": {"pixel_grid_sha256": "grid"},
    }
    run = store.create(
        run_key="with-provenance", scene="april-9-demo",
        frame_keys=["f1"], frames=["20260409040000"],
        provenance=provenance,
    )

    assert store.get(run.id).provenance == provenance
    assert store.get(run.id).to_dict()["provenance"] == provenance


def test_unknown_state_is_refused(store):
    run = _make(store)
    with pytest.raises(ValueError, match="unknown state"):
        store.set_state(run.id, "vibing")


def test_terminal_flag(store):
    run = _make(store)
    assert not run.terminal
    assert store.set_state(run.id, "cancelled").terminal


def test_restart_marks_in_flight_runs_interrupted(store):
    queued = _make(store, "k1")
    running = _make(store, "k2")
    store.set_state(running.id, "running")
    done = _make(store, "k3")
    store.set_state(done.id, "succeeded")

    store.recover_orphans()

    assert store.get(queued.id).state == "failed"
    assert store.get(queued.id).error == "interrupted"
    assert store.get(running.id).state == "failed"
    assert store.get(done.id).state == "succeeded", "terminal runs must be untouched"
