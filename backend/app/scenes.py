"""Scenes: bounded temporal contexts that make epoch mixing impossible.

A scene is not a single instant. It is a time window together with the set of data natures
admitted inside it. `current` rolls with the clock and admits only genuinely live records;
`april-9-demo` is fixed to a past hour and admits only historical ones.

Admission is enforced here rather than inside each provider. A provider is the wrong place
for it: providers are where mistakes happen, and the whole point is that no bug in one can
put an April record into a feed labelled live, or the reverse.

The interval was chosen by screening eight candidate hours against four gates. See
`docs/decisions/scene-selection.md`. The short version: the hour with the most BRIGHT
detections had no polar overpass at all, which would have produced an interface whose central
comparison had one side missing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Iterable, Sequence

from .models import DATA_NATURES, Detection

CURRENT_WINDOW_MINUTES = 70
FRAME_CADENCE_MINUTES = 10


@dataclass(frozen=True)
class Scene:
    id: str
    title: str
    description: str
    admitted: frozenset[str]
    #: Fixed scenes carry an explicit half-open interval; rolling scenes carry None.
    fixed_window: tuple[datetime, datetime] | None = None
    frames: Sequence[str] = field(default_factory=tuple)

    def window(self) -> tuple[datetime, datetime]:
        """Half-open [start, end). Rolling scenes resolve against the clock each call."""
        if self.fixed_window is not None:
            return self.fixed_window
        end = datetime.now(timezone.utc)
        return end - timedelta(minutes=CURRENT_WINDOW_MINUTES), end

    def admits(self, data_nature: str) -> bool:
        return data_nature in self.admitted

    def to_dict(self) -> dict:
        start, end = self.window()
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "window": {"start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                       "end": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                       "half_open": True},
            "admits": sorted(self.admitted),
            "frames": list(self.frames),
            "rolling": self.fixed_window is None,
        }


def _frames(start: datetime, end: datetime) -> tuple[str, ...]:
    out, cursor = [], start
    while cursor < end:
        out.append(cursor.strftime("%Y%m%d%H%M%S"))
        cursor += timedelta(minutes=FRAME_CADENCE_MINUTES)
    return tuple(out)


_DEMO_START = datetime(2026, 4, 9, 4, 0, tzinfo=timezone.utc)
_DEMO_END = datetime(2026, 4, 9, 5, 0, tzinfo=timezone.utc)

SCENES: dict[str, Scene] = {
    "current": Scene(
        id="current",
        title="Current",
        description=(
            "Live hotspots from Digital Earth Australia's operational service, over a "
            "rolling 70-minute window. Genuinely current. No BRIGHT recomputation, and "
            "never a cached fixture: if a source is unavailable it is reported absent "
            "rather than substituted."
        ),
        admitted=frozenset({"live"}),
    ),
    "april-9-demo": Scene(
        id="april-9-demo",
        title="9 April 2026, 04:00–05:00 UTC",
        description=(
            "Six BRIGHT frames at ten-minute cadence, recomputed from staged Himawari "
            "inputs, against two VIIRS overpasses: Suomi-NPP at 04:27–04:29 and NOAA-20 "
            "at 04:47–04:49. Chosen because it is one of the few hours that day carrying "
            "both geostationary and polar observations of the same fire."
        ),
        admitted=frozenset({"replay", "static"}),
        fixed_window=(_DEMO_START, _DEMO_END),
        frames=_frames(_DEMO_START, _DEMO_END),
    ),
}

DEFAULT_SCENE = "april-9-demo"


def get_scene(scene_id: str) -> Scene:
    try:
        return SCENES[scene_id]
    except KeyError:
        raise KeyError(f"unknown scene {scene_id!r}; known: {sorted(SCENES)}") from None


def admit(records: Iterable[Detection], scene: Scene) -> list[Detection]:
    """Drop anything the scene does not admit. The last line of defence against epoch mixing."""
    kept = []
    for record in records:
        if record.data_nature not in DATA_NATURES:
            raise ValueError(f"unknown data_nature {record.data_nature!r}")
        if scene.admits(record.data_nature):
            kept.append(record)
    return kept
