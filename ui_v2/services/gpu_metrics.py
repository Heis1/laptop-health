from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(slots=True)
class GpuInfo:
    name: Optional[str] = None
    temp_c: Optional[float] = None
    busy_pct: Optional[float] = None


def _read_text(p: Path) -> Optional[str]:
    try:
        return p.read_text(encoding="utf-8", errors="ignore").strip()
    except Exception:
        return None


def _read_float(p: Path, scale: float = 1.0) -> Optional[float]:
    s = _read_text(p)
    if not s:
        return None
    try:
        return float(s) / scale
    except Exception:
        return None


def _gpu_name_from_device(dev: Path) -> Optional[str]:
    # Prefer a readable name if present
    for rel in ("product_name", "uevent", "vendor"):
        t = _read_text(dev / rel)
        if not t:
            continue
        if rel == "uevent":
            for line in t.splitlines():
                if line.startswith("DRIVER="):
                    return line.split("=", 1)[1].strip()
        else:
            return t
    return None


def _temp_from_hwmon(dev: Path) -> Optional[float]:
    hwmon_root = dev / "hwmon"
    if not hwmon_root.exists():
        return None
    for hw in sorted(hwmon_root.glob("hwmon*")):
        for tf in ("temp1_input", "temp2_input", "temp3_input"):
            v = _read_float(hw / tf, scale=1000.0)  # millidegC -> C
            if v is not None and v > 0:
                return v
    return None


def _busy_from_sysfs(dev: Path) -> Optional[float]:
    # AMDGPU commonly exposes this
    v = _read_float(dev / "gpu_busy_percent")
    if v is not None:
        return v
    # Some Intel stacks expose this
    v = _read_float(dev / "gt_busy_percent")
    if v is not None:
        return v
    return None


def get_gpu() -> GpuInfo | None:
    """
    Best-effort GPU metrics via Linux sysfs. Returns None if nothing readable.
    """
    drm = Path("/sys/class/drm")
    if not drm.exists():
        return None

    cards = sorted([p for p in drm.glob("card[0-9]*") if p.is_dir()])
    for card in cards:
        dev = card / "device"
        if not dev.exists():
            continue

        info = GpuInfo(
            name=_gpu_name_from_device(dev),
            temp_c=_temp_from_hwmon(dev),
            busy_pct=_busy_from_sysfs(dev),
        )

        if info.name or info.temp_c is not None or info.busy_pct is not None:
            return info

    return None
