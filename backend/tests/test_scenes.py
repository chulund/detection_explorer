"""Scenes exist to make epoch mixing impossible rather than merely discouraged.

A scene is a bounded temporal context plus the sources admitted to it. `current` rolls with
the clock and admits only live records; `april-9-demo` is fixed and admits only historical
ones. Admission is enforced here rather than in each provider, so that a provider bug cannot
leak a live record into a historical scene.
"""

from __future__ import annotations

import pytest

from app.scenes import SCENES, admit


def test_both_scenes_exist():
    assert set(SCENES) == {"current", "april-9-demo"}


def test_demo_scene_is_the_half_open_april_9_hour():
    scene = SCENES["april-9-demo"]
    start, end = scene.window()
    assert start.isoformat() == "2026-04-09T04:00:00+00:00"
    assert end.isoformat() == "2026-04-09T05:00:00+00:00"


def test_demo_scene_frames_are_six_at_ten_minutes():
    # Frames are an immutable sequence on a frozen dataclass; compare by content.
    assert list(SCENES["april-9-demo"].frames) == [
        "20260409040000", "20260409041000", "20260409042000",
        "20260409043000", "20260409044000", "20260409045000",
    ]


def test_current_scene_window_rolls_with_the_clock():
    a = SCENES["current"].window()
    b = SCENES["current"].window()
    assert b[1] >= a[1]
    assert (a[1] - a[0]).total_seconds() == 70 * 60


def test_current_admits_live_and_rejects_historical():
    scene = SCENES["current"]
    assert scene.admits("live")
    assert not scene.admits("static")
    assert not scene.admits("replay")


def test_demo_admits_historical_and_rejects_live():
    scene = SCENES["april-9-demo"]
    assert scene.admits("replay")
    assert scene.admits("static")
    assert not scene.admits("live")


def test_admit_filters_rather_than_trusting_the_provider(make_detection):
    scene = SCENES["april-9-demo"]
    records = [make_detection(data_nature="static"), make_detection(data_nature="live")]
    kept = admit(records, scene)
    assert [r.data_nature for r in kept] == ["static"]


def test_unknown_data_nature_is_never_admitted(make_detection):
    with pytest.raises(ValueError):
        make_detection(data_nature="archive")
