from __future__ import annotations
from PySide6.QtGui import QFont

from typing import Optional
import shutil

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QStyle, QVBoxLayout
from ui_v2.widgets.cards import apply_responsive_card_fonts
from ui_v2.widgets.progressbar import SlimBar


from pathlib import Path as _Path

def find_mountpoint_for_path(target_path: str) -> str:
    """
    Return the mountpoint that contains target_path.
    Linux-only approach using /proc/mounts.
    """
    target = _Path(target_path).resolve()

    mounts: list[tuple[_Path, str]] = []
    try:
        with open("/proc/mounts", "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    mp = parts[1]
                    try:
                        mounts.append((_Path(mp).resolve(), mp))
                    except Exception:
                        continue
    except Exception:
        return "/"

    # Pick the deepest mountpoint that is a prefix of target
    best = "/"
    best_len = 1
    for resolved_mp, mp_str in mounts:
        try:
            if str(target).startswith(str(resolved_mp) + "/") or str(target) == str(resolved_mp):
                l = len(str(resolved_mp))
                if l > best_len:
                    best_len = l
                    best = mp_str
        except Exception:
            continue
    return best


def accent_for_disk_target(target: str, used_pct: int | None) -> str:
    if used_pct is None:
        return "blue"

    used = float(used_pct)
    if target == "root":
        if used >= 88:
            return "red"
        if used >= 75:
            return "orange"
        return "green"

    if used >= 95:
        return "red"
    if used >= 88:
        return "orange"
    return "green"


class DiskUsageCard(QFrame):
    def __init__(
        self,
        used_percent: int | None = None,
        free_text: str | None = None,
        mount_path: str = "/",
        parent: Optional[object] = None,
    ):
        super().__init__(parent)

        self.mount_path = mount_path
        self.target = "root"

        self.setObjectName("Card")
        self.setProperty("accent", "orange")
        self.setProperty("_responsive_width_divisor", 2)
        self.setMinimumHeight(120)  # reduced height

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 14)  # tighter padding
        outer.setSpacing(6)  # tighter vertical spacing

        hdr = QHBoxLayout()
        ico = QLabel()
        ico.setPixmap(self.style().standardIcon(QStyle.SP_DriveHDIcon).pixmap(16, 16))
        hdr.addWidget(ico)

        self.title = QLabel("Disk Usage")
        self.title.setObjectName("CardTitle")
        hdr.addWidget(self.title)
        hdr.addStretch(1)
        outer.addLayout(hdr)

        self.big = QLabel("—")

        f = QFont()

        f.setStyleHint(QFont.Monospace)

        f.setFixedPitch(True)

        
        self.big.setFont(f)

        self.big.setObjectName("CardBig")
        self.big.setWordWrap(True)
        outer.addWidget(self.big)

        self.sub = QLabel("—")
        self.sub.setObjectName("CardSub")
        self.sub.setWordWrap(True)
        outer.addWidget(self.sub)

        self.bar = SlimBar()
        self.bar.setFixedHeight(14)
        outer.addWidget(self.bar)

        if used_percent is not None or free_text is not None:
            if used_percent is None:
                self.big.setText("—")
                self.bar.setValue(0)
            else:
                self.big.setText(f"{int(used_percent)}% Used")
                self.bar.setValue(max(0, min(100, int(used_percent))))
            self.sub.setText(free_text or "—")
        else:
            self.refresh()
        apply_responsive_card_fonts(self)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        apply_responsive_card_fonts(self)

    def set_disk(self, used_pct: int | None, free_gb: float | None, target: str = "root", mount_label: str | None = None):
        self.target = target
        self.setProperty("accent", accent_for_disk_target(target, used_pct))
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

        if used_pct is None:
            self.big.setText("—")
            self.sub.setText("—")
            self.bar.setValue(0)
            return
        self.big.setText(f"{int(used_pct)}% Used")
        if free_gb is None:
            self.sub.setText("—")
        else:
            target_text = mount_label or ("Home" if target == "home" else "Root")
            self.sub.setText(f"{target_text} • {free_gb:.0f} GB Free")
        self.bar.setValue(max(0, min(100, int(used_pct))))

    def refresh(self):
        self.title.setText(f"Disk Usage ({self.mount_path})")
        try:
            du = shutil.disk_usage(self.mount_path)
            used_pct = int(round((du.used / du.total) * 100))
            free_gb = du.free / (1024**3)
            self.set_disk(used_pct, free_gb)
        except Exception:
            self.set_disk(None, None)
