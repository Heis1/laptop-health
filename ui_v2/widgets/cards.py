from __future__ import annotations
from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QPushButton, QFrame, QHBoxLayout, QLabel, QStyle, QVBoxLayout, QWidget

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
    """
    Overview Pending Updates card.
    Shows summary + link to detailed Updates page.
    """
    details_requested = Signal()

    def __init__(self, accent: str = "orange"):
        super().__init__()
        self.setObjectName("Card")
        self.setProperty("accent", accent)
        self.setMinimumHeight(160)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(10)

        # Header
        hdr = QHBoxLayout()
        ico = QLabel()
        ico.setPixmap(self.style().standardIcon(QStyle.SP_MessageBoxWarning).pixmap(18, 18))
        hdr.addWidget(ico)

        title = QLabel("Pending Updates")
        title.setObjectName("CardTitle")
        hdr.addWidget(title)
        hdr.addStretch(1)

        self.badge = QLabel("—")
        self.badge.setObjectName("Badge")
        hdr.addWidget(self.badge)

        outer.addLayout(hdr)

        # Summary
        self.summary = QLabel("—")
        self.summary.setObjectName("CardSub")
        outer.addWidget(self.summary)

        # Rows
        self.rows = {}

        def add_row(label: str):
            row = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setObjectName("CardSub")
            val = QLabel("—")
            val.setObjectName("CardSub")
            row.addWidget(lbl)
            row.addStretch(1)
            row.addWidget(val)
            outer.addLayout(row)
            self.rows[label] = val

        add_row("Updates Available")
        add_row("Security Updates")
        add_row("Reboot Required")

        # View details button
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)

        self.btn_details = QPushButton("View details")
        self.btn_details.setObjectName("copybtn")
        self.btn_details.clicked.connect(self.details_requested.emit)

        btn_row.addWidget(self.btn_details)
        outer.addLayout(btn_row)

        outer.addStretch(1)

    def set_updates(self, total, security=None, reboot=None):
        if total is None:
            self.summary.setText("Update status unavailable")
            self.badge.setText("Unknown")
            return

        total = int(total)
        security = 0 if security is None else int(security)
        reboot = False if reboot is None else bool(reboot)

        self.rows["Updates Available"].setText(str(total))
        self.rows["Security Updates"].setText(str(security))
        self.rows["Reboot Required"].setText("Yes" if reboot else "No")

        if total == 0 and not reboot:
            self.summary.setText("System is up to date")
            self.badge.setText("OK")
            accent = "green"
        else:
            if security > 0:
                self.summary.setText(f"{total} updates pending ({security} security)")
            else:
                self.summary.setText(f"{total} updates pending")
            self.badge.setText("Attention")
            accent = "red" if (security > 0 or reboot) else "orange"

        self.setProperty("accent", accent)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()
