"""`.env` reaches the process.

`.env.example` says "copy to .env and fill in", and `docs/STATUS.md` describes a research
profile that is nothing but a `.env` with two keys in it. Nothing read the file, so both
profiles behaved identically: FIRMS fell back to fixtures with a key sitting in `.env`,
and BRIGHT reported itself unavailable with the pipeline installed. These tests are the
reason that cannot happen again quietly.
"""

from __future__ import annotations

import os

from app import load_env


def test_values_in_the_file_reach_the_environment(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text("EXPLORER_TEST_KEY=from-file\n", encoding="utf-8")
    monkeypatch.delenv("EXPLORER_TEST_KEY", raising=False)

    load_env(path)
    assert os.environ["EXPLORER_TEST_KEY"] == "from-file"


def test_the_shell_wins_over_the_file(tmp_path, monkeypatch):
    """A one-off override must not need the checked-in configuration edited."""
    path = tmp_path / ".env"
    path.write_text("EXPLORER_TEST_KEY=from-file\n", encoding="utf-8")
    monkeypatch.setenv("EXPLORER_TEST_KEY", "from-shell")

    load_env(path)
    assert os.environ["EXPLORER_TEST_KEY"] == "from-shell"


def test_comments_and_blank_lines_are_not_variables(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text("# a comment\n\nEXPLORER_TEST_KEY=value\n", encoding="utf-8")
    monkeypatch.delenv("EXPLORER_TEST_KEY", raising=False)

    assert load_env(path) == ["EXPLORER_TEST_KEY"]


def test_an_absent_file_is_not_an_error(tmp_path):
    """The fixture profile is a clean clone with no `.env`, and it must still start."""
    assert load_env(tmp_path / "nothing-here") == []


def test_the_default_path_is_the_repository_root(tmp_path):
    """Where `.env.example` tells the reader to put it, not the backend directory."""
    from app import ENV_PATH, REPO_ROOT

    assert ENV_PATH == REPO_ROOT / ".env"
    assert (REPO_ROOT / ".env.example").exists()


def test_this_suite_does_not_load_the_developers_env():
    """Guards the offline promise in `conftest.py`.

    A real `.env` carries a FIRMS key, and with a key the provider fetches over the
    network instead of reading the committed fixtures. Without this the suite would
    quietly start depending on credentials and on FIRMS being reachable.
    """
    from app import SKIP_VAR

    assert os.environ.get(SKIP_VAR)
