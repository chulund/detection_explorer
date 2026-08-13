"""Cache keys for BRIGHT runs, at two levels.

A run covers an interval; caching happens per frame. So a frame gets its own key and a run
is keyed by the ordered list of its frames. An interval overlapping an earlier run then
recomputes only what is new.

A frame timestamp alone would be wrong as a key. The same timestamp computed under a
different pipeline commit, a different configuration, or different staged inputs is a
different result, and serving the earlier one from cache would silently misreport what the
algorithm currently does. So all of that goes into the hash.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

#: A separator that cannot occur inside any component, so that concatenation is
#: unambiguous and "ab" + "c" cannot collide with "a" + "bc".
SEP = "\x1f"


def _sha(*parts: str) -> str:
    return hashlib.sha256(SEP.join(parts).encode("utf-8")).hexdigest()


def frame_key(*, scene: str, frame_ts: str, pipeline_sha: str, config_hash: str,
              manifest_checksum: str, schema_version: str) -> str:
    """Identity of one computed frame, under one exact set of inputs."""
    return _sha(scene, frame_ts, pipeline_sha, config_hash, manifest_checksum,
                schema_version)


def run_key(frame_keys: list[str]) -> str:
    """Identity of a run, from its frames in order.

    Order matters: a run over 04:00 then 04:10 is a different request from one over
    04:10 then 04:00, even though the frames cached are the same.
    """
    return _sha(*frame_keys)


def manifest_checksum(manifest_path: Path, frame_ts: str) -> str:
    """The staged-input digest for one frame, taken from the tracked manifest.

    Reads the per-day-slot digests the staging script recorded rather than re-hashing
    hundreds of megabytes of parquet on every request.
    """
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    for frame in manifest.get("frames", []):
        if frame.get("frame") == frame_ts:
            digests = [day.get("sha256") or "" for day in frame.get("days", [])]
            return _sha(*digests)
    return "absent"


def config_hash(config: dict) -> str:
    """Stable digest of the effective configuration."""
    return _sha(json.dumps(config, sort_keys=True, separators=(",", ":")))
