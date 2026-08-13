"""What every detection source must offer.

Providers *retrieve* detections. They do not compute them: a BRIGHT run is expensive,
stateful and failure-prone, and giving it the same lifecycle as an HTTP GET would be a
category error. Computation lives in `app.runs`.

A provider answers three questions. What is it called, can it serve this scene right now,
and what does it return for this scene's window. `available` takes the scene because the
answer genuinely differs: FIRMS can serve a historical scene from a committed fixture, but
must report itself unavailable for the current scene rather than substituting April records
into a feed labelled live.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from ..models import Detection
from ..scenes import Scene


@runtime_checkable
class Provider(Protocol):
    name: str

    def available(self, scene: Scene) -> bool:
        """Can this provider serve that scene, right now, honestly?"""

    def nature_for(self, scene: Scene) -> str:
        """The `data_nature` records will carry in that scene."""

    def fetch(self, scene: Scene, window: tuple[datetime, datetime]) -> list[Detection]:
        """Detections for the window. Must not return anything the scene disallows."""


class ProviderUnavailable(RuntimeError):
    """Raised when a provider is asked for data it cannot honestly supply."""

    def __init__(self, provider: str, reason: str) -> None:
        super().__init__(f"{provider} unavailable: {reason}")
        self.provider = provider
        self.reason = reason
