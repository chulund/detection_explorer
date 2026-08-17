"""Detection Explorer backend.

`.env` is read here, in the package initialiser, because it has to be read before
anything else in the package. Provider availability, the run queue and the state
directory are all decided at import time from `os.environ`, so a load placed in
`main.py` alongside its other imports would run after `registry` had already concluded
that no keys were configured.

That is not hypothetical. `.env.example` says "copy to .env and fill in" and
`docs/STATUS.md` describes a research profile consisting of exactly that file, but
nothing read it: FIRMS served fixtures with a valid key sitting in `.env`, and BRIGHT
reported `BRIGHT_PIPELINE_PATH unset` on a machine holding the pipeline.
"""

from __future__ import annotations

import os
from pathlib import Path

#: backend/app/__init__.py -> backend -> the repository root, where `.env` belongs.
REPO_ROOT = Path(__file__).resolve().parents[2]

ENV_PATH = REPO_ROOT / ".env"

#: Set by the test suite. A developer's real `.env` carries a FIRMS key, and a key makes
#: the FIRMS provider fetch over the network instead of reading committed fixtures, so
#: loading it here would quietly put an offline test suite on the internet. The suite
#: builds each profile with monkeypatch instead, which is what makes both profiles
#: testable on one machine.
SKIP_VAR = "DETECTION_EXPLORER_SKIP_ENV"


def load_env(path: Path | None = None) -> list[str]:
    """Read `KEY=value` lines into the environment. Returns the names it set.

    The shell wins: a variable already set is left alone, so a one-off run can override
    the file without editing it, and the test suite can pin a value.

    An absent file is not an error. The fixture profile is a clean clone with no `.env`
    at all, and it is a supported configuration rather than a broken one.
    """
    target = Path(path) if path is not None else ENV_PATH
    if not target.is_file():
        return []

    applied = []
    for line in target.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, _, value = stripped.partition("=")
        name = name.strip()
        if not name or name in os.environ:
            continue
        # Quotes are stripped so a Windows path with spaces can be quoted in the file.
        os.environ[name] = value.strip().strip('"').strip("'")
        applied.append(name)
    return applied


if not os.environ.get(SKIP_VAR):
    load_env()
