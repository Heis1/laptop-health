from __future__ import annotations
from typing import Optional
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QPainter, QPen, QFont
from PySide6.QtWidgets import QWidget
from ui_v2.theme import ACCENT, TEXT

def qcolor(hexstr: str, alpha: int = 255) -> QColor:
    c = QColor(hexstr)
    c.setAlpha(alpha)
    return c

class Ring(QWidget):
    def __init__(self, value: int = 72, accent: str = "orange", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.value = max(0, min(100, value))
        self.accent = accent
        self.setFixedSize(QSize(72, 72))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(6, 6, -6, -6)

        p.setPen(QPen(qcolor("#2a3b55", 200), 8, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(rect, 90 * 16, -360 * 16)

        accent_hex = ACCENT.get(self.accent, ACCENT["orange"])
        p.setPen(QPen(qcolor(accent_hex, 255), 8, Qt.SolidLine, Qt.RoundCap))
        span = int(-360 * 16 * (self.value / 100.0))
        p.drawArc(rect, 90 * 16, span)

        p.setPen(qcolor(TEXT, 255))
        f = QFont()
        f.setBold(True)
        f.setPointSize(10)
        p.setFont(f)
        p.drawText(self.rect(), Qt.AlignCenter, f"{self.value}%")
