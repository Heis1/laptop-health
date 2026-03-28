from __future__ import annotations
import re
from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon, QFont, QFontMetrics
from PySide6.QtWidgets import QPushButton, QFrame, QHBoxLayout, QLabel, QStyle, QVBoxLayout, QWidget, QSizePolicy, QBoxLayout

from ui_v2.widgets.sparkline import Sparkline
from ui_v2.widgets.ring import Ring
from ui_v2.services.updates import UPDATE_ACCENT_RGBA, classify_update_status

ICON_MAP = {
    "CPU": QStyle.SP_ComputerIcon,
    "GPU": QStyle.SP_ComputerIcon,
    "Disk Usage": QStyle.SP_DriveHDIcon,
    "Pending Updates": QStyle.SP_MessageBoxWarning,
    "Network": QStyle.SP_DriveNetIcon,
    "Wakeup Analysis": QStyle.SP_DialogApplyButton,
}

_RESPONSIVE_TYPE_BASE = {
    "CardHuge": 34.0,
    "CardBig": 30.0,
    "CardTitle": 13.0,
    "CardSub": 11.0,
    "Badge": 11.0,
}


def apply_responsive_card_fonts(widget: QWidget, width: int | None = None) -> None:
    width = max(220, int(width if width is not None else widget.width() or widget.sizeHint().width() or 320))
    divisor = widget.property("_responsive_width_divisor")
    try:
        divisor = max(1.0, float(divisor))
    except Exception:
        divisor = 1.0
    width = max(220, int(width / divisor))
    if width >= 420:
        scale = 1.0
    elif width >= 340:
        scale = 0.84 + ((width - 340) / 80.0) * 0.16
    elif width >= 280:
        scale = 0.72 + ((width - 280) / 60.0) * 0.12
    else:
        scale = 0.62 + ((width - 220) / 60.0) * 0.10
    scale = max(0.62, min(1.0, scale))

    for cls in (QLabel, QPushButton):
        for child in widget.findChildren(cls):
            base = _RESPONSIVE_TYPE_BASE.get(child.objectName())
            if base is None:
                continue
            base_style = child.property("_responsive_base_style")
            if base_style is None:
                base_style = child.styleSheet()
                child.setProperty("_responsive_base_style", base_style)
            child.setStyleSheet(f"{base_style}\nfont-size: {base * scale:.2f}pt;")

class MetricCard(QFrame):
    def __init__(
        self,
        title: str,
        big: str,
        sub: str,
        accent: str,
        badge: Optional[str] = None,
        right_widget: Optional[QWidget] = None,
        right_widget_position: str = "side",
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

        content.addLayout(left, 1)

        if right_widget is not None and right_widget_position == "side":
            try:
                right_widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
            except Exception:
                pass
            content.addWidget(right_widget, 1, Qt.AlignRight | Qt.AlignVCenter)
        outer.addLayout(content)

        if right_widget is not None and right_widget_position == "below":
            try:
                right_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            except Exception:
                pass
            outer.addWidget(right_widget)

        self.spark = None
        if spark_points is not None:
            self.spark = Sparkline(spark_points, accent=accent)
            outer.addWidget(self.spark)
        apply_responsive_card_fonts(self)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        apply_responsive_card_fonts(self)

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


class WakeupsCard(QFrame):
    def __init__(self, accent: str = "green"):
        super().__init__()
        self.setObjectName("Card")
        self.setProperty("accent", accent)
        self.setMinimumHeight(160)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(10)

        hdr = QHBoxLayout()
        hdr.setSpacing(10)

        ico = QLabel()
        ico.setPixmap(self.style().standardIcon(QStyle.SP_DialogApplyButton).pixmap(18, 18))
        hdr.addWidget(ico)

        title = QLabel("Wakeups")
        title.setObjectName("CardTitle")
        hdr.addWidget(title)
        hdr.addStretch(1)
        outer.addLayout(hdr)

        self.big = QLabel("—")
        self.big.setObjectName("CardHuge")
        self.big.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        mono = QFont()
        mono.setStyleHint(QFont.Monospace)
        mono.setFixedPitch(True)
        self.big.setFont(mono)
        outer.addWidget(self.big)

        self.primary = QLabel("ctx/s")
        self.primary.setObjectName("CardSub")
        self.primary.setWordWrap(True)
        outer.addWidget(self.primary)

        self.secondary = QLabel("—")
        self.secondary.setObjectName("CardSub")
        self.secondary.setWordWrap(True)
        outer.addWidget(self.secondary)
        outer.addStretch(1)

        apply_responsive_card_fonts(self)
        self._sync_big_slot()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        apply_responsive_card_fonts(self)
        self._sync_big_slot()

    def _sync_big_slot(self) -> None:
        fm = QFontMetrics(self.big.font())
        slot_w = fm.horizontalAdvance("99,999") + 6
        self.big.setMinimumWidth(slot_w)

    def set_values(self, big: str, sub: str, accent: str | None = None):
        number = "—"
        unit = "ctx/s"
        if isinstance(big, str):
            m = re.search(r"([0-9][0-9,]*)\s*([A-Za-z/]+)?", big)
            if m:
                number = m.group(1)
                if m.group(2):
                    unit = m.group(2)
            elif big.strip():
                number = big
        else:
            number = str(big)

        self.big.setText(number)
        self.primary.setText(unit)
        self.secondary.setText(sub if sub else "—")
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

        outer.addLayout(hdr)

        # Body: big number + list
        self.body = QBoxLayout(QBoxLayout.LeftToRight)
        self.body.setSpacing(16)

        self.big = QLabel("—")


        f = QFont()


        f.setStyleHint(QFont.Monospace)


        f.setFixedPitch(True)


        

        self.big.setFont(f)

        self.big.setStyleSheet("")
        self.big.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.big.setObjectName("CardHuge")
        f = QFont()
        f.setBold(True)
        f.setPointSize(34)  # big, uses the space
        self.big.setFont(f)
        self.big.setStyleSheet("color: rgba(255,255,255,0.96);")
        self.body.addWidget(self.big, 0)

        self.right = QVBoxLayout()
        self.right.setSpacing(6)

        self.row_updates = QLabel("Updates Available: —")
        self.row_updates.setObjectName("CardSub")
        self.row_updates.setWordWrap(True)
        self.right.addWidget(self.row_updates)

        self.row_security = QLabel("Security Updates: —")
        self.row_security.setObjectName("CardSub")
        self.row_security.setWordWrap(True)
        self.right.addWidget(self.row_security)

        self.row_reboot = QLabel("Reboot Required: —")
        self.row_reboot.setObjectName("CardSub")
        self.row_reboot.setWordWrap(True)
        self.right.addWidget(self.row_reboot)

        self.right.addStretch(1)
        self.body.addLayout(self.right, 1)

        outer.addLayout(self.body)

        # Footer button (styled + icon)
        self.foot = QHBoxLayout()
        self.foot.setSpacing(8)
        self.foot.addStretch(1)

        self.badge = QLabel("—")
        self.badge.setObjectName("Badge")
        self.badge.setCursor(Qt.PointingHandCursor)
        self.badge.setToolTip("Open Updates page")
        self.badge.mousePressEvent = self._on_badge_clicked
        self.foot.addWidget(self.badge, 0, Qt.AlignRight)

        self.btn_details = QPushButton("View details")
        self.btn_details.setCursor(Qt.PointingHandCursor)
        self.btn_details.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)

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
        self.foot.addWidget(self.btn_details)
        self.btn_details.hide()

        outer.addLayout(self.foot)
        outer.addStretch(1)
        self._apply_responsive_fonts()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_responsive_fonts()

    def _apply_responsive_fonts(self) -> None:
        apply_responsive_card_fonts(self)
        width = max(220, self.width() or self.sizeHint().width() or 320)
        if width < 360:
            self.body.setDirection(QBoxLayout.TopToBottom)
            self.body.setSpacing(8)
        else:
            self.body.setDirection(QBoxLayout.LeftToRight)
            self.body.setSpacing(16)

        if width >= 420:
            scale = 1.0
        elif width >= 360:
            scale = 0.88 + ((width - 360) / 60.0) * 0.12
        elif width >= 300:
            scale = 0.80 + ((width - 300) / 60.0) * 0.08
        else:
            scale = 0.76 + ((width - 220) / 80.0) * 0.04
        scale = max(0.76, min(1.0, scale))

        base_big_style = self.big.property("_responsive_base_style")
        if base_big_style is None:
            base_big_style = self.big.styleSheet()
            self.big.setProperty("_responsive_base_style", base_big_style)
        self.big.setStyleSheet(
            f"{base_big_style}\nfont-size: {34.0 * scale:.2f}pt;"
        )
        try:
            fm = QFontMetrics(self.big.font())
            self.big.setMinimumWidth(0 if width < 360 else fm.horizontalAdvance("99") + 8)
        except Exception:
            pass

        base_btn_style = self.btn_details.property("_responsive_base_style")
        if base_btn_style is None:
            base_btn_style = self.btn_details.styleSheet()
            self.btn_details.setProperty("_responsive_base_style", base_btn_style)
        self.btn_details.setStyleSheet(
            f"{base_btn_style}\nfont-size: {11.0 * scale:.2f}pt;"
        )
        self.foot.setDirection(QBoxLayout.LeftToRight)
        self.foot.setContentsMargins(0, 0, 0, 0)

    def _on_badge_clicked(self, event) -> None:
        self.details_requested.emit()
        if event is not None:
            event.accept()

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
        self.badge.setVisible(status_badge != "OK")

        self.setProperty("accent", status_accent)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()
