from __future__ import annotations

import shutil
import subprocess

POWER_MODE_ORDER = ("Quiet", "Balanced", "Performance")

_CLI_NAME = "powerprofilesctl"
_CLI_TO_LABEL = {
    "power-saver": "Quiet",
    "balanced": "Balanced",
    "performance": "Performance",
}
_LABEL_TO_CLI = {label: cli for cli, label in _CLI_TO_LABEL.items()}


def _has_cli() -> bool:
    return bool(shutil.which(_CLI_NAME))


def get_active_power_mode() -> tuple[str, str]:
    if not _has_cli():
        return "Unavailable", "missing: powerprofilesctl"
    try:
        res = subprocess.run(
            [_CLI_NAME, "get"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except Exception as exc:
        return "Unavailable", str(exc)

    if res.returncode != 0:
        return "Unavailable", (res.stderr or res.stdout or f"rc={res.returncode}").strip()

    raw = (res.stdout or "").strip().lower()
    if not raw:
        return "Unavailable", "empty response"
    return _CLI_TO_LABEL.get(raw, raw.title()), ""


def set_active_power_mode(mode: str) -> tuple[bool, str]:
    cli_mode = _LABEL_TO_CLI.get(str(mode or "").strip())
    if not cli_mode:
        return False, "unknown mode"
    if not _has_cli():
        return False, "powerprofilesctl not installed"
    try:
        res = subprocess.run(
            [_CLI_NAME, "set", cli_mode],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except Exception as exc:
        return False, str(exc)

    if res.returncode != 0:
        return False, (res.stderr or res.stdout or f"rc={res.returncode}").strip()
    return True, ""
