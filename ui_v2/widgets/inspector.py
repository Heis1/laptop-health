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
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui_v2.widgets.cards import MetricCard
from ui_v2.widgets.shadow import apply_card_shadow
from ui_v2.widgets.cpu_details_card import CpuDetailsCard
from ui_v2.widgets.disk_info_card import DiskInfoCard
from ui_v2.services.wakeups import wakeups_hint_fast, wakeups_hint_deep
from ui_v2.theme import ACCENT


class Inspector(QFrame):
    def __init__(self):
        super().__init__()
        self._cards: list[QWidget] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        # ----- Header -----
        hdr = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(2)

        self.title = QLabel("System Overview")
        self.title.setObjectName("InspectorTitle")
        title_box.addWidget(self.title)

        self.subtitle = QLabel("Live CPU, storage, and wake activity")
        self.subtitle.setObjectName("InspectorSub")
        title_box.addWidget(self.subtitle)
        hdr.addLayout(title_box)
        hdr.addStretch(1)

        self.summary_badge = QLabel("Awaiting refresh")
        self.summary_badge.setObjectName("Badge")
        hdr.addWidget(self.summary_badge)
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

        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(12)
        self.grid.setVerticalSpacing(12)
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 1)
        self.grid.setColumnStretch(2, 1)

        # ----- Cards -----
        self.cpu_details = CpuDetailsCard()
        self.disk = DiskInfoCard()
        self.cpu_details.setMinimumWidth(0)
        self.disk.setMinimumWidth(0)

        # Wakeups: history + scaling
        self._wake_hist = deque([0.0] * 36, maxlen=36)

        # Right-side info stack
        self._wake_info = QWidget()
        info = QVBoxLayout(self._wake_info)
        info.setContentsMargins(0, 0, 0, 0)
        info.setSpacing(6)

        try:
            self._wake_info.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        except Exception:
            pass

        self._wake_line1 = QLabel("✓ Proxy: /proc/stat (fast)")
        self._wake_line1.setObjectName("CardSub")
        self._wake_line1.setWordWrap(True)
        self._wake_line2 = QLabel("✓ Deep: powertop (needs sudo)")
        self._wake_line2.setObjectName("CardSub")
        self._wake_line2.setWordWrap(True)
        self._wake_line3 = QLabel("—")
        self._wake_line3.setObjectName("CardSub")
        self._wake_line3.setWordWrap(True)

        # Prevent right-side wake info from being clipped
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
            right_widget_position="below",
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
        self.wake.setMinimumWidth(0)
        self._cards = [self.cpu_details, self.disk, self.wake]

        self.grid.addWidget(self.cpu_details, 0, 0)
        self.grid.addWidget(self.disk, 0, 1)
        self.grid.addWidget(self.wake, 0, 2)

        container_layout.addLayout(self.grid)
        outer.addWidget(self.container)
        self._apply_responsive_card_sizes()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_responsive_card_sizes()

    def _apply_responsive_card_sizes(self) -> None:
        width = max(720, self.width())
        if width >= 1400:
            card_h = 270
            spark_h = 58
        elif width >= 1180:
            card_h = 258
            spark_h = 52
        elif width >= 1020:
            card_h = 246
            spark_h = 48
        else:
            card_h = 236
            spark_h = 44

        for card in self._cards:
            try:
                card.setMinimumHeight(card_h)
                card.setMaximumHeight(16777215)
            except Exception:
                pass

        try:
            self.cpu_details.spark.setMinimumHeight(spark_h)
            self.cpu_details.spark.setMaximumHeight(spark_h)
        except Exception:
            pass
        try:
            self.disk.read_spark.setMinimumHeight(spark_h)
            self.disk.read_spark.setMaximumHeight(spark_h)
            self.disk.write_spark.setMinimumHeight(spark_h)
            self.disk.write_spark.setMaximumHeight(spark_h)
        except Exception:
            pass
        try:
            if getattr(self.wake, "spark", None) is not None:
                self.wake.spark.setMinimumHeight(spark_h)
                self.wake.spark.setMaximumHeight(spark_h)
        except Exception:
            pass

    def _wake_status_text(self, accent: str, value: float | None) -> str:
        if value is None:
            return "Wake activity is unavailable"
        if accent == "red":
            return "Wake activity is elevated"
        if accent == "orange":
            return "Wake activity is above baseline"
        if value < 200:
            return "Wake activity is low"
        return "Wake activity is stable"

    def _set_wake_icon_accent(self, accent: str) -> None:
        color = ACCENT.get(accent, ACCENT["green"])
        self._wake_icon.setStyleSheet(
            f"QLabel {{ background: {color}; border-radius: 7px; }}"
        )

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
            fn = getattr(self.disk, "update_overview", None)
            if callable(fn):
                fn(m)
        except Exception:
            pass


        # Wakeup Analysis
        try:
            big = getattr(m, "wakeups_big", "—")
            sub = getattr(m, "wakeups_sub", "—")
            accent = getattr(m, "wakeups_accent", "green")

            self.wake.set_values(big, sub, accent)
            self._set_wake_icon_accent(accent)

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

            self._wake_line3.setText(self._wake_status_text(accent, v))
            self.summary_badge.setText(
                f"CPU {getattr(m, 'cpu_temp_c', None):.0f}°C • "
                f"Root {getattr(m, 'root_used_pct', '—')}%"
                if isinstance(getattr(m, "cpu_temp_c", None), (int, float))
                and getattr(m, "root_used_pct", None) is not None
                else "Overview live"
            )

            if v is not None:
                # log scale: 0..~10000 maps nicely
                val = max(0.0, min(1.0, math.log10(v + 1.0) / 4.0))
                self._wake_hist.append(val)
                if getattr(self.wake, "spark", None) is not None:
                    self.wake.set_spark(list(self._wake_hist))
        except Exception:
            pass
