#!/usr/bin/env python3
# Entry point for Laptop Health (Linux)
#
# Keeps environment checks and bootstrapping here.
# UI + application logic lives in ui.py.

from __future__ import annotations

import sys


def _running_frozen() -> bool:
    return getattr(sys, "frozen", False)


def _ensure_venv() -> None:
    # Must run inside venv (dev only). Allow PyInstaller builds.
    if _running_frozen():
        return
    if sys.prefix == sys.base_prefix:
        raise RuntimeError(
            "Virtual environment not active.\n"
            "Run: source .venv/bin/activate"
        )


def main(argv: list[str] | None = None) -> int:
    _ensure_venv()
    import ui  # local module

    return ui.main(argv or sys.argv)

if __name__ == "__main__":
    raise SystemExit(main())
