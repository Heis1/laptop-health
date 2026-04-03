from __future__ import annotations
from typing import Optional

from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QStyle, QVBoxLayout, QProgressBar
)

from ui_v2.services.storage_metrics import MountMetrics


def _util_class(total_mbps: float) -> str:
    # tune these thresholds as you like
    if total_mbps < 1.0:
        return "idle"
    if total_mbps < 50.0:
        return "ok"
    if total_mbps < 150.0:
        return "busy"
    return "hot"


def _palette(util: str) -> tuple[str, str]:
    """
    Returns (accent_name, hex_color_for_text_and_bar)
    """
    if util == "idle":
        return ("blue", "#7aa2f7")
    if util == "ok":
        return ("green", "#3ddc97")
    if util == "busy":
        return ("orange", "#ffb86b")
    return ("red", "#ff5c5c")


class StorageIOCard(QFrame):
    def __init__(self, title: str, accent: str = "orange", parent: Optional[object] = None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setProperty("accent", accent)
        self.setMinimumHeight(165)
        self.setMaximumHeight(235)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.setSpacing(8)

        hdr = QHBoxLayout()
        ico = QLabel()
        ico.setPixmap(self.style().standardIcon(QStyle.SP_DriveHDIcon).pixmap(16, 16))
        hdr.addWidget(ico)

        self.title = QLabel(title)
        self.title.setObjectName("CardTitle")
        hdr.addWidget(self.title)
        hdr.addStretch(1)
        outer.addLayout(hdr)

        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(4)

        self.read_big = QLabel("—"); self.read_big.setObjectName("CardHuge")
        self.write_big = QLabel("—"); self.write_big.setObjectName("CardHuge")
        self.read_sub = QLabel("Read MB/s"); self.read_sub.setObjectName("CardSub")
        self.write_sub = QLabel("Write MB/s"); self.write_sub.setObjectName("CardSub")

        grid.addWidget(self.read_big, 0, 0)
        grid.addWidget(self.write_big, 0, 1)
        grid.addWidget(self.read_sub, 1, 0)
        grid.addWidget(self.write_sub, 1, 1)
        outer.addLayout(grid)

        self.activity = QProgressBar()
        self.activity.setRange(0, 100)
        self.activity.setTextVisible(False)
        self.activity.setFixedHeight(6)
        outer.addWidget(self.activity)

        self.meta = QLabel("—")
        self.meta.setObjectName("CardSub")
        self.meta.setWordWrap(True)
        outer.addWidget(self.meta)

    def apply(self, m: MountMetrics):
        self.title.setText(f"{m.label} I/O  ({m.mount})")

        read = m.read_mbps or 0.0
        write = m.write_mbps or 0.0
        total = read + write

        util = _util_class(total)
        accent, hexcol = _palette(util)

        # set card accent for border glow (your theme already uses this)
        self.setProperty("accent", accent)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

        # numbers
        self.read_big.setText("—" if m.read_mbps is None else f"{read:.1f}")
        self.write_big.setText("—" if m.write_mbps is None else f"{write:.1f}")

        # colour the numbers so they stand out
        self.read_big.setStyleSheet(f"color: {hexcol};")
        self.write_big.setStyleSheet(f"color: {hexcol};")

        # activity bar (cap at 200 MB/s visual)
        self.activity.setValue(min(100, int((total / 200.0) * 100)))
        self.activity.setStyleSheet(
            "QProgressBar{background: rgba(255,255,255,0.06); border: 0; border-radius: 3px;}"
            f"QProgressBar::chunk{{background: {hexcol}; border-radius: 3px;}}"
        )

        # meta line
        parts = []
        if m.active is not None:
            parts.append("Active" if m.active else "Idle")
        if m.devpath:
            parts.append(f"Part: {m.devpath}")
        if m.io_devname:
            parts.append(f"I/O: /dev/{m.io_devname}")
        if m.total_read_gb is not None and m.total_written_gb is not None:
            parts.append(f"Total R/W: {m.total_read_gb:.0f}G / {m.total_written_gb:.0f}G")
        if m.fstype:
            parts.append(f"FS: {m.fstype}")
        if m.size:
            parts.append(f"Size: {m.size}")
        if m.rota is not None:
            parts.append("SSD" if m.rota == 0 else "HDD")
        if m.temp_c is not None:
            parts.append(f"Temp: {m.temp_c:.0f}°C")

        self.meta.setText(" • ".join(parts) if parts else "—")
