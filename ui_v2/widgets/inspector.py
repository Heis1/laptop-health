from __future__ import annotations

from collections import deque
import math
import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QToolButton,
    QVBoxLayout,
    QSizePolicy,
    QWidget,
)

from ui_v2.widgets.cards import MetricCard
from ui_v2.widgets.shadow import apply_card_shadow
from ui_v2.widgets.cpu_details_card import CpuDetailsCard
from ui_v2.widgets.disk_info_card import DiskInfoCard
from ui_v2.services.wakeups import wakeups_hint_fast, wakeups_hint_deep


class Inspector(QFrame):
    def __init__(self):
        super().__init__()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        # ----- Header -----
        hdr = QHBoxLayout()
        self.toggle = QToolButton()
        self.toggle.hide()  # twisty removed
        self.toggle.setObjectName("InspectorToggle")
        self.toggle.setText("System Inspector")
        self.toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        hdr.addWidget(self.toggle)
        hdr.addStretch(1)

        dots = QLabel("• • •")
        dots.setObjectName("InspectorDots")
        hdr.addWidget(dots)
        outer.addLayout(hdr)

        # ----- Container -----
        self.container = QFrame()
        self.container.setObjectName("InspectorContainer")
        apply_card_shadow(self.container)

        # Don’t eat leftover vertical space
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(16, 16, 16, 16)
        container_layout.setSpacing(12)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)

        # ----- Cards -----
        self.cpu_details = CpuDetailsCard()
        self.disk = DiskInfoCard()

        # Wakeups: history + scaling
        self._wake_hist = deque([0.0] * 36, maxlen=36)

        # Right-side info stack
        self._wake_info = QWidget()
        info = QVBoxLayout(self._wake_info)
        info.setContentsMargins(0, 0, 0, 0)
        info.setSpacing(6)

        self._wake_line1 = QLabel("✓ Proxy: /proc/stat (fast)")
        self._wake_line1.setObjectName("CardSub")
        self._wake_line2 = QLabel("✓ Deep: powertop (needs sudo)")
        self._wake_line2.setObjectName("CardSub")
        self._wake_line3 = QLabel("—")
        self._wake_line3.setObjectName("CardSub")

        info.addWidget(self._wake_line1)
        info.addWidget(self._wake_line2)
        info.addWidget(self._wake_line3)
        info.addStretch(1)

        self.wake = MetricCard(
            "Wakeup Analysis",
            "—",
            "—",
            "green",
            right_widget=self._wake_info,
            spark_points=list(self._wake_hist),
        )

        # Status circle icon (mock-style)
        self._wake_icon = QLabel("")
        self._wake_icon.setFixedSize(14, 14)
        self._wake_icon.setStyleSheet(
            "QLabel { background: rgba(92,255,160,0.95); border-radius: 7px; }"
        )

        # Replace default MetricCard icon with our dot, add spacing
        hdr_layout = self.wake.layout().itemAt(0).layout()
        if hdr_layout.count() > 0:
            item = hdr_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        hdr_layout.insertWidget(0, self._wake_icon)
        hdr_layout.insertSpacing(1, 6)

        # Wake title slightly stronger
        t = self.wake.findChild(QLabel, "CardTitle")
        if t is not None:
            t.setStyleSheet("font-weight: 600;")

        if getattr(self.wake, "spark", None) is not None:
            self.wake.spark.setMinimumHeight(58)

        grid.addWidget(self.cpu_details, 0, 0)
        grid.addWidget(self.disk, 0, 1)
        grid.addWidget(self.wake, 0, 2)

        container_layout.addLayout(grid)
        outer.addWidget(self.container)

    def update_overview(self, m) -> None:
        """Receive OverviewMetrics from DashboardPage and fan out to sub-cards."""
        # CPU Details
        try:
            fn = getattr(self.cpu_details, "update_overview", None)
            if callable(fn):
                fn(m)
        except Exception:
            pass

        # Disk info
        try:
            fn = getattr(self.disk, "set_disk", None)
            if callable(fn):
                fn(getattr(m, "root_used_pct", None), getattr(m, "root_free_gb", None))
        except Exception:
            pass

        # Wakeup Analysis
        try:
            big = getattr(m, "wakeups_big", "—")
            sub = getattr(m, "wakeups_sub", "—")
            accent = getattr(m, "wakeups_accent", "green")

            self.wake.set_values(big, sub, accent)

            # Hint lines (cheap but useful)
            try:
                self._wake_line1.setText(wakeups_hint_fast())
            except Exception:
                pass
            try:
                self._wake_line2.setText(wakeups_hint_deep())
            except Exception:
                pass

            # Sparkline from big ("123 ctx/s")
            v = None
            if isinstance(big, str):
                mm = re.search(r"([-+]?[0-9]*\.?[0-9]+)", big)
                if mm:
                    v = float(mm.group(1))
            elif isinstance(big, (int, float)):
                v = float(big)

            if v is not None:
                # log scale: 0..~10000 maps nicely
                val = max(0.0, min(1.0, math.log10(v + 1.0) / 4.0))
                self._wake_hist.append(val)
                if getattr(self.wake, "spark", None) is not None:
                    self.wake.set_spark(list(self._wake_hist))
        except Exception:
            pass
