from __future__ import annotations

_STATE = {
    "sidebar_update_mode": "real",
    "linux_updates_mode": "real",
}

_VALID_UPDATE_MODES = {
    "real",
    "available",
    "current",
    "error",
}

_VALID_LINUX_UPDATE_MODES = {
    "real",
    "clean",
    "updates",
    "security",
    "kept",
    "held",
    "reboot",
    "mixed",
    "error",
}


def get_sidebar_update_mode() -> str:
    value = str(_STATE.get("sidebar_update_mode", "real"))
    return value if value in _VALID_UPDATE_MODES else "real"


def set_sidebar_update_mode(mode: str) -> None:
    normalized = str(mode or "real").strip().lower()
    _STATE["sidebar_update_mode"] = normalized if normalized in _VALID_UPDATE_MODES else "real"


def get_linux_updates_mode() -> str:
    value = str(_STATE.get("linux_updates_mode", "real"))
    return value if value in _VALID_LINUX_UPDATE_MODES else "real"


def set_linux_updates_mode(mode: str) -> None:
    normalized = str(mode or "real").strip().lower()
    _STATE["linux_updates_mode"] = normalized if normalized in _VALID_LINUX_UPDATE_MODES else "real"


def reset_flags() -> None:
    _STATE["sidebar_update_mode"] = "real"
    _STATE["linux_updates_mode"] = "real"
