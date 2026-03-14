from __future__ import annotations

from collections import deque
from typing import Optional

from PySide6.QtCore import QThreadPool, QTimer, Qt, QEvent
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QStyle,
    QVBoxLayout,
    QPushButton,
)

from ui_v2.qtworker import QtWorker
from ui_v2.services.storage_metrics import gather_storage, StorageSnapshot, MountMetrics
from ui_v2.widgets.sparkline import Sparkline


def _accent_for_used(used_pct: int | None) -> str:
    if used_pct is None:
        return "purple"
    u = float(used_pct)
    if u < 75:
        return "green"
    if u < 88:
        return "orange"
    return "red"


def _norm01(v: float, lo: float, hi: float) -> float:
    if hi <= lo:
        return 0.0
    x = (v - lo) / (hi - lo)
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return float(x)


def _fmt_mbps(v: float | None) -> str:
    if v is None:
        return "—"
    try:
        v = float(v)
    except Exception:
        return "—"
    if v < 10:
        return f"{v:.1f}"
    return f"{v:.0f}"


def _fmt_meta(m: MountMetrics) -> str:
    bits: list[str] = []
    if m.devpath:
        bits.append(m.devpath)
    if m.fstype:
        bits.append(m.fstype)
    if m.rota is not None:
        bits.append("SSD" if int(m.rota) == 0 else "HDD")
    if m.size:
        bits.append(m.size)
    if m.temp_c is not None:
        bits.append(f"{m.temp_c:.0f}°C")
    if m.total_read_gb is not None and m.total_written_gb is not None:
        bits.append(f"Total R/W {m.total_read_gb:.0f}G / {m.total_written_gb:.0f}G")
    if m.io_devname:
        bits.append(f"I/O /dev/{m.io_devname}")
    return " • ".join(bits) if bits else "—"


class DiskInfoCard(QFrame):
    """
    Inspector tile: disk activity view with Root/Home toggle.
      - Big Read/Write MB/s + sparklines
      - Compact identity/meta line
      - Accent based on selected mount used %
      - Separate sparkline history for Root vs Home
    """

    def __init__(self, parent: Optional[object] = None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setProperty("accent", "purple")

        self.pool = QThreadPool()

        # Root/Home toggle state
        self._target = "root"  # "root" or "home"
        self._last_snap: StorageSnapshot | None = None

        # Separate history buffers per target (normalized 0..1)
        self._hist = {
            "root": {
                "read": deque([0.0] * 36, maxlen=36),
                "write": deque([0.0] * 36, maxlen=36),
            },
            "home": {
                "read": deque([0.0] * 36, maxlen=36),
                "write": deque([0.0] * 36, maxlen=36),
            },
        }

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(10)

        # Header
        hdr = QHBoxLayout()
        ico = QLabel()
        ico.setPixmap(self.style().standardIcon(QStyle.SP_DriveHDIcon).pixmap(16, 16))
        hdr.addWidget(ico)

        t = QLabel("Disk Info")
        t.setObjectName("CardTitle")
        hdr.addWidget(t)
        hdr.addStretch(1)

        # Clickable badge (styled like Badge)
        self.badge = QPushButton("Root")
        self.badge.setObjectName("Badge")
        self.badge.setCursor(Qt.PointingHandCursor)
        self.badge.setFlat(True)
        self.badge.clicked.connect(self._toggle_target)
        self.badge.installEventFilter(self)  # so we can refresh tooltip on hover
        hdr.addWidget(self.badge)

        outer.addLayout(hdr)

        # Compact summary
        self.summary = QLabel("—")
        self.summary.setObjectName("CardSub")
        outer.addWidget(self.summary)

        # Read/Write grid
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(6)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        self.read_label = QLabel("Read MB/s")
        self.read_label.setObjectName("CardSub")
        self.write_label = QLabel("Write MB/s")
        self.write_label.setObjectName("CardSub")

        self.read_big = QLabel("—")
        self.read_big.setObjectName("CardBig")
        self.write_big = QLabel("—")
        self.write_big.setObjectName("CardBig")

        self.read_spark = Sparkline(list(self._hist["root"]["read"]), accent="blue")
        self.read_spark.setMinimumHeight(52)
        self.write_spark = Sparkline(list(self._hist["root"]["write"]), accent="orange")
        self.write_spark.setMinimumHeight(52)

        grid.addWidget(self.read_label, 0, 0)
        grid.addWidget(self.write_label, 0, 1)
        grid.addWidget(self.read_big, 1, 0)
        grid.addWidget(self.write_big, 1, 1)
        grid.addWidget(self.read_spark, 2, 0)
        grid.addWidget(self.write_spark, 2, 1)

        outer.addLayout(grid)

        # Meta
        self.meta = QLabel("—")
        self.meta.setObjectName("CardSub")
        self.meta.setWordWrap(True)
        outer.addWidget(self.meta)

        outer.addStretch(1)

        # initial tooltip
        self._update_badge_tooltip()

        # First refresh and timer
        self._refresh()
        self.timer = QTimer(self)
        self.timer.setInterval(5000)
        self.timer.timeout.connect(self._refresh)
        self.timer.start()

    def eventFilter(self, obj, event):
        # Update tooltip right as user hovers, so it always shows "switch to X"
        if obj is self.badge and event.type() == QEvent.Enter:
            self._update_badge_tooltip()
        return super().eventFilter(obj, event)

    def _update_badge_tooltip(self):
        next_label = "Home" if self._target == "root" else "Root"
        self.badge.setToolTip(f"Click to switch to {next_label}")

    def _toggle_target(self):
        self._target = "home" if self._target == "root" else "root"
        self.badge.setText("Home" if self._target == "home" else "Root")
        self._update_badge_tooltip()

        # Re-render immediately from last snapshot WITHOUT appending duplicates
        if self._last_snap is not None:
            m = self._select_mount(self._last_snap)
            self._render(m, append=False)

    def _select_mount(self, snap: StorageSnapshot) -> MountMetrics:
        return snap.home if self._target == "home" else snap.root

    def _refresh(self):
        w = QtWorker(lambda: gather_storage(interval_s=0.6))
        w.signals.result.connect(self._apply)
        w.signals.error.connect(self._apply_err)
        self.pool.start(w)

    def _apply_err(self, msg: str):
        self.setProperty("accent", "red")
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()
        if msg:
            self.meta.setText(msg)

    def _render(self, m: MountMetrics, append: bool):
        # Compact summary line
        used = "—" if m.used_pct is None else f"{int(m.used_pct)}% used"
        free = "—" if m.free_gb is None else f"{float(m.free_gb):.0f} GB free"
        mount_label = "/" if self._target == "root" else "Home"
        self.summary.setText(f"{mount_label} ({m.mount}) • {used} • {free}")

        # Read/Write numbers
        self.read_big.setText(_fmt_mbps(m.read_mbps))
        self.write_big.setText(_fmt_mbps(m.write_mbps))

        # Update sparklines (cap at 200 MB/s for stable visuals)
        cap = 200.0
        hist = self._hist[self._target]
        if append:
            r = 0.0 if m.read_mbps is None else max(0.0, float(m.read_mbps))
            wv = 0.0 if m.write_mbps is None else max(0.0, float(m.write_mbps))
            hist["read"].append(_norm01(r, 0.0, cap))
            hist["write"].append(_norm01(wv, 0.0, cap))

        if hasattr(self.read_spark, "set_points"):
            self.read_spark.set_points(list(hist["read"]))
            self.write_spark.set_points(list(hist["write"]))
        else:
            self.read_spark._points = list(hist["read"])
            self.write_spark._points = list(hist["write"])
            self.read_spark.update()
            self.write_spark.update()

        # Meta + accent
        self.meta.setText(_fmt_meta(m))
        self.setProperty("accent", _accent_for_used(m.used_pct))
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def _apply(self, snap):
        if not isinstance(snap, StorageSnapshot):
            self._apply_err("Disk info error")
            return

        self._last_snap = snap
        m = self._select_mount(snap)
        self._render(m, append=True)
