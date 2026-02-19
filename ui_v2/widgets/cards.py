from __future__ import annotations
from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QStyle, QVBoxLayout, QWidget
from ui_v2.widgets.sparkline import Sparkline
from ui_v2.widgets.ring import Ring

ICON_MAP = {
    "CPU": QStyle.SP_ComputerIcon,
    "GPU": QStyle.SP_DriveHDIcon,
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

        big_lbl = QLabel(big)
        big_lbl.setObjectName("CardBig")
        sub_lbl = QLabel(sub)
        sub_lbl.setObjectName("CardSub")

        left.addWidget(big_lbl)
        left.addWidget(sub_lbl)
        left.addStretch(1)

        content.addLayout(left, 2)

        if right_widget is not None:
            content.addWidget(right_widget, 0, Qt.AlignRight | Qt.AlignVCenter)

        outer.addLayout(content)

        if spark_points is not None:
            outer.addWidget(Sparkline(spark_points, accent=accent))

class UpdatesCard(QFrame):
    def __init__(self, accent: str = "red"):
        super().__init__()
        self.setObjectName("Card")
        self.setProperty("accent", accent)

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

        badge = QLabel("Attention")
        badge.setObjectName("Badge")
        row.addWidget(badge)

        outer.addLayout(row)

        def add_row(label: str, value: str):
            r = QHBoxLayout()
            l = QLabel(label); l.setObjectName("RowLabel")
            v = QLabel(value); v.setObjectName("RowValue")
            r.addWidget(l); r.addStretch(1); r.addWidget(v)
            outer.addLayout(r)

        add_row("Updates Available", "7")
        add_row("Security Updates", "2")
        add_row("Reboot Required", "No")
        outer.addStretch(1)

def demo_disk_card():
    return MetricCard("Disk Usage", "72% Used", "35 GB Free", "orange", right_widget=Ring(72, "orange"))
