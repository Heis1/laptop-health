from __future__ import annotations
from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QStyle, QVBoxLayout, QWidget

from ui_v2.widgets.sparkline import Sparkline
from ui_v2.widgets.ring import Ring

ICON_MAP = {
    "CPU": QStyle.SP_ComputerIcon,
    "GPU": QStyle.SP_ComputerIcon,
    "Disk Usage": QStyle.SP_DriveHDIcon,
    "Pending Updates": QStyle.SP_MessageBoxWarning,
    "Network": QStyle.SP_DriveNetIcon,
}

class MetricCard(QFrame):
    def __init__(
        self,
        title: str,
        big: str,
        sub: str,
        accent: str,
        badge: Optional[str] = None,
        right_widget: Optional[QWidget] = None,
        spark_points: Optional[list[float]] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setProperty("accent", accent)
        self.setMinimumHeight(150)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(10)

        row = QHBoxLayout()
        row.setSpacing(10)

        ico = QLabel()
        sp = ICON_MAP.get(title, QStyle.SP_FileIcon)
        icon: QIcon = self.style().standardIcon(sp)
        ico.setPixmap(icon.pixmap(18, 18))
        row.addWidget(ico)

        t = QLabel(title)
        t.setObjectName("CardTitle")
        row.addWidget(t)
        row.addStretch(1)

        if badge:
            b = QLabel(badge)
            b.setObjectName("Badge")
            row.addWidget(b)

        outer.addLayout(row)

        content = QHBoxLayout()
        content.setSpacing(12)

        left = QVBoxLayout()
        left.setSpacing(6)

        self.big_lbl = QLabel(big)
        self.big_lbl.setObjectName("CardBig")
        self.sub_lbl = QLabel(sub)
        self.sub_lbl.setObjectName("CardSub")

        left.addWidget(self.big_lbl)
        left.addWidget(self.sub_lbl)
        left.addStretch(1)

        content.addLayout(left, 2)

        if right_widget is not None:
            content.addWidget(right_widget, 0, Qt.AlignRight | Qt.AlignVCenter)

        outer.addLayout(content)

        self.spark = None
        if spark_points is not None:
            self.spark = Sparkline(spark_points, accent=accent)
            outer.addWidget(self.spark)

    def set_spark(self, points: list[float]) -> None:
        """Update sparkline points (expects 0..1 floats)."""
        spark = getattr(self, 'spark', None)
        if spark is None:
            return
        # Preferred API
        if hasattr(spark, 'set_points') and callable(getattr(spark, 'set_points')):
            spark.set_points(points)
        else:
            # Fallback if sparkline uses a public attribute
            try:
                spark.points = points
            except Exception:
                return
        spark.update()

    def set_values(self, big: str, sub: str, accent: str | None = None):
        self.big_lbl.setText(big)
        self.sub_lbl.setText(sub)
        if accent:
            self.setProperty("accent", accent)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()


class UpdatesCard(QFrame):
    def __init__(self, accent: str = "red"):
        super().__init__()
        self.setObjectName("Card")
        self.setProperty("accent", accent)
        self.setMinimumHeight(150)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(10)

        row = QHBoxLayout()
        row.setSpacing(10)

        ico = QLabel()
        ico.setPixmap(self.style().standardIcon(QStyle.SP_MessageBoxWarning).pixmap(18, 18))
        row.addWidget(ico)

        t = QLabel("Pending Updates")
        t.setObjectName("CardTitle")
        row.addWidget(t)
        row.addStretch(1)

        self.badge = QLabel("Attention")
        self.badge.setObjectName("Badge")
        row.addWidget(self.badge)

        outer.addLayout(row)

        self.rows: dict[str, QLabel] = {}

        def add_row(label: str, value: str):
            r = QHBoxLayout()
            l = QLabel(label); l.setObjectName("RowLabel")
            v = QLabel(value); v.setObjectName("RowValue")
            r.addWidget(l); r.addStretch(1); r.addWidget(v)
            outer.addLayout(r)
            self.rows[label] = v

        add_row("Updates Available", "—")
        outer.addStretch(1)

    def set_updates(self, count: int | None):
        if count is None:
            self.rows["Updates Available"].setText("—")
            self.badge.setText("Unknown")
        else:
            self.rows["Updates Available"].setText(str(count))
            self.badge.setText("OK" if count == 0 else "Attention")
