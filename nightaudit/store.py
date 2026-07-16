"""Small JSON state files, written atomically.

nightaudit is invoked from cron and may be killed mid-write; every state file
goes through a temp file + ``os.replace`` so a torn write can never leave a
half-parsed ledger behind.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def read_json(path: Path, default: Any) -> Any:
    """Read ``path``, returning ``default`` if it is missing or unreadable.

    A corrupt state file is not worth crashing a cron job over — nightaudit
    starts from ``default`` and carries on.
    """
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return default
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return default


def write_json(path: Path, data: Any) -> None:
    """Serialise ``data`` to ``path`` atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=True)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
