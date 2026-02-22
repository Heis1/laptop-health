from __future__ import annotations

from collections import deque
from typing import Optional

from PySide6.QtCore import QThreadPool, QTimer, Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QStyle, QVBoxLayout

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
    # identity
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

    # totals
    if m.total_read_gb is not None and m.total_written_gb is not None:
        bits.append(f"Total R/W {m.total_read_gb:.0f}G / {m.total_written_gb:.0f}G")

    # io dev
    if m.io_devname:
        bits.append(f"I/O /dev/{m.io_devname}")

    return " • ".join(bits) if bits else "—"


class DiskInfoCard(QFrame):
    """
    Inspector tile: intuitive disk activity view.
      - Big Read/Write MB/s + sparklines
      - Compact identity/meta line
      - Accent based on root used %
    """
    def __init__(self, parent: Optional[object] = None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setProperty("accent", "purple")

        self.pool = QThreadPool()

        # History for sparklines (MB/s normalized)
        self._read_hist = deque([0.0] * 36, maxlen=36)
        self._write_hist = deque([0.0] * 36, maxlen=36)

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

        self.badge = QLabel("Root")
        self.badge.setObjectName("Badge")
        hdr.addWidget(self.badge)

        outer.addLayout(hdr)

        # Big used/free summary (kept but not dominant)
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

        self.read_spark = Sparkline(list(self._read_hist), accent="blue")
        self.read_spark.setMinimumHeight(52)
        self.write_spark = Sparkline(list(self._write_hist), accent="orange")
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

        # First refresh and timer
        self._refresh()
        self.timer = QTimer(self)
        self.timer.setInterval(5000)  # IO feels nice at 5s
        self.timer.timeout.connect(self._refresh)
        self.timer.start()

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

    def _apply(self, snap):
        if not isinstance(snap, StorageSnapshot):
            self._apply_err("Disk info error")
            return

        m = snap.root

        # summary line (compact)
        used = "—" if m.used_pct is None else f"{int(m.used_pct)}% used"
        free = "—" if m.free_gb is None else f"{float(m.free_gb):.0f} GB free"
        self.summary.setText(f"/  ({m.mount}) • {used} • {free}")

        # read/write numbers
        self.read_big.setText(_fmt_mbps(m.read_mbps))
        self.write_big.setText(_fmt_mbps(m.write_mbps))

        # update sparklines (cap at 200 MB/s for visual stability)
        cap = 200.0
        r = 0.0 if m.read_mbps is None else max(0.0, float(m.read_mbps))
        wv = 0.0 if m.write_mbps is None else max(0.0, float(m.write_mbps))
        self._read_hist.append(_norm01(r, 0.0, cap))
        self._write_hist.append(_norm01(wv, 0.0, cap))

        if hasattr(self.read_spark, "set_points"):
            self.read_spark.set_points(list(self._read_hist))
            self.write_spark.set_points(list(self._write_hist))
        else:
            self.read_spark._points = list(self._read_hist)
            self.write_spark._points = list(self._write_hist)
            self.read_spark.update()
            self.write_spark.update()

        # meta line
        self.meta.setText(_fmt_meta(m))

        # accent based on used%
        self.setProperty("accent", _accent_for_used(m.used_pct))
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()
