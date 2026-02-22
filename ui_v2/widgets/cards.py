from __future__ import annotations
from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon, QFont
from PySide6.QtWidgets import QPushButton, QFrame, QHBoxLayout, QLabel, QStyle, QVBoxLayout, QWidget

from ui_v2.widgets.sparkline import Sparkline
from ui_v2.widgets.ring import Ring
from ui_v2.services.updates import UPDATE_ACCENT_RGBA, classify_update_status

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
    Overview Pending Updates (mock-style use of space):
      - Huge count on the left
      - 3-line list on the right (Updates/Security/Reboot)
      - View details button (styled) + updates icon
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
        hdr.setSpacing(10)

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

        # Body: big number + list
        body = QHBoxLayout()
        body.setSpacing(16)

        self.big = QLabel("—")
        self.big.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        f = QFont()
        f.setBold(True)
        f.setPointSize(34)  # big, uses the space
        self.big.setFont(f)
        self.big.setStyleSheet("color: rgba(255,255,255,0.96);")
        body.addWidget(self.big, 0)

        right = QVBoxLayout()
        right.setSpacing(6)

        self.row_updates = QLabel("Updates Available: —")
        self.row_updates.setObjectName("CardSub")
        right.addWidget(self.row_updates)

        self.row_security = QLabel("Security Updates: —")
        self.row_security.setObjectName("CardSub")
        right.addWidget(self.row_security)

        self.row_reboot = QLabel("Reboot Required: —")
        self.row_reboot.setObjectName("CardSub")
        right.addWidget(self.row_reboot)

        right.addStretch(1)
        body.addLayout(right, 1)

        outer.addLayout(body)

        # Footer button (styled + icon)
        foot = QHBoxLayout()
        foot.addStretch(1)

        self.btn_details = QPushButton("View details")
        self.btn_details.setCursor(Qt.PointingHandCursor)

        # Icon: use a standard refresh/updates glyph
        self.btn_details.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))

        # Make it match dashboard polish (avoid default button look)
        self.btn_details.setStyleSheet("""
            QPushButton {
                color: rgba(255,255,255,0.92);
                background: rgba(255,255,255,0.08);
                border: 1px solid rgba(255,255,255,0.14);
                padding: 6px 12px;
                border-radius: 10px;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.12);
                border: 1px solid rgba(255,255,255,0.18);
            }
            QPushButton:pressed {
                background: rgba(255,255,255,0.06);
            }
        """)

        self.btn_details.clicked.connect(self.details_requested.emit)
        foot.addWidget(self.btn_details)

        outer.addLayout(foot)
        outer.addStretch(1)

    def set_updates(self, total, security=None, reboot=None, kept_back=0, held=0, badge=None, accent=None):
        if total is None:
            self.big.setText("—")
            self.row_updates.setText("Updates Available: —")
            self.row_security.setText("Security Updates: —")
            self.row_reboot.setText("Reboot Required: —")
            status_badge, status_accent = classify_update_status(None, security, bool(reboot), kept_back, held)
        else:
            tot = int(total)
            sec = 0 if security is None else int(security)
            reb = False if reboot is None else bool(reboot)

            self.big.setText(str(tot))
            self.row_updates.setText(f"Updates Available: {tot}")
            self.row_security.setText(f"Security Updates: {sec}")
            self.row_reboot.setText("Reboot Required: Yes" if reb else "Reboot Required: No")
            status_badge, status_accent = classify_update_status(tot, sec, reb, int(kept_back or 0), int(held or 0))

        status_badge = badge or status_badge
        status_accent = accent or status_accent
        self.badge.setText(status_badge)
        self.badge.setStyleSheet(f"color: {UPDATE_ACCENT_RGBA.get(status_accent, 'rgba(255,255,255,0.85)')};")

        self.setProperty("accent", status_accent)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()
