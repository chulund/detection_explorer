"""BRIGHT preflight and the provenance that participates in run identity."""

from __future__ import annotations

import pytest

from app.runs import provenance


def _pipeline(tmp_path):
    pipeline = tmp_path / "bright"
    ancillary = pipeline / "ancillary"
    ancillary.mkdir(parents=True)
    (pipeline / "config.yaml").write_text("detection_nweeks: 4\n", encoding="utf-8")
    (ancillary / "himawari_pixel_grid_nsw.parquet").write_bytes(b"grid")
    (ancillary / provenance.SENSOR_GEOMETRY_NAME).write_bytes(b"geometry")
    return pipeline


def test_configured_pipeline_sha_must_match_the_checkout(tmp_path, monkeypatch):
    pipeline = _pipeline(tmp_path)
    monkeypatch.setattr(
        provenance, "_git", lambda path, *args: "actual-sha" if args[0] == "rev-parse" else ""
    )

    with pytest.raises(provenance.PipelinePreflightError, match="does not match"):
        provenance.inspect_pipeline(pipeline, configured_sha="expected-sha")
