"""Reproducibility preflight for a BRIGHT pipeline checkout."""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

PIXEL_GRID_NAME = "himawari_pixel_grid_nsw.parquet"
SENSOR_GEOMETRY_NAME = (
    "00000000000000-P1S-ABOM_GEOM_SENSOR-PRJ_GEOS141_2000-HIMAWARI8-AHI_subset_nsw.nc"
)


class PipelinePreflightError(RuntimeError):
    """The configured checkout cannot produce a reproducible run."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git(path: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=path, capture_output=True, text=True,
        timeout=10, check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise PipelinePreflightError(f"cannot inspect BRIGHT checkout: {detail}")
    return result.stdout.strip()


def inspect_pipeline(
    pipeline_path: str | os.PathLike[str] | None = None,
    *,
    configured_sha: str | None = None,
    require_reproducible: bool = True,
) -> dict:
    """Return hashable, path-free provenance and enforce the configured pin."""
    configured_path = pipeline_path or os.environ.get("BRIGHT_PIPELINE_PATH")
    configured_sha = configured_sha or os.environ.get("BRIGHT_PIPELINE_SHA")
    if not configured_path:
        if require_reproducible:
            raise PipelinePreflightError("BRIGHT_PIPELINE_PATH is not set")
        return {"available": False, "reproducible": False,
                "reason": "BRIGHT_PIPELINE_PATH unset"}

    pipeline = Path(configured_path).resolve()
    if not pipeline.is_dir():
        raise PipelinePreflightError("BRIGHT_PIPELINE_PATH is not a directory")
    if not configured_sha:
        raise PipelinePreflightError("BRIGHT_PIPELINE_SHA is not set")

    actual_sha = _git(pipeline, "rev-parse", "HEAD")
    if configured_sha != actual_sha:
        raise PipelinePreflightError(
            "BRIGHT_PIPELINE_SHA does not match the checkout HEAD"
        )
    dirty = _git(pipeline, "status", "--porcelain", "--untracked-files=normal")
    if dirty:
        raise PipelinePreflightError("BRIGHT checkout has uncommitted changes")

    required = {
        "configuration": pipeline / "config.yaml",
        "pixel_grid": pipeline / "ancillary" / PIXEL_GRID_NAME,
        "sensor_geometry": pipeline / "ancillary" / SENSOR_GEOMETRY_NAME,
    }
    missing = [name for name, path in required.items() if not path.is_file()]
    if missing:
        raise PipelinePreflightError(
            "BRIGHT checkout is missing required inputs: " + ", ".join(missing)
        )

    return {
        "available": True,
        "reproducible": True,
        "pipeline": {
            "configured_sha": configured_sha,
            "actual_sha": actual_sha,
            "checkout_clean": True,
        },
        "configuration": {
            "period": "both",
            "sha256": _sha256(required["configuration"]),
        },
        "ancillary": {
            "pixel_grid_sha256": _sha256(required["pixel_grid"]),
            "sensor_geometry_sha256": _sha256(required["sensor_geometry"]),
        },
    }
