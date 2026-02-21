from __future__ import annotations
from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget, QSizePolicy
from ui_v2.theme import ACCENT

def qcolor(hexstr: str, alpha: int = 255) -> QColor:
    c = QColor(hexstr)
    c.setAlpha(alpha)
    return c

class Sparkline(QWidget):
    def __init__(self, points: list[float], accent: str = "blue", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._points = points[:] if points else [0, 1, 0.5, 0.8, 0.6, 0.9, 0.7]
        self._accent = accent
        self.setMinimumHeight(46)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_points(self, points: list[float]) -> None:
        """Replace sparkline data (expects 0..1 normalized floats)."""
        if not points:
            return
        self._points = points[:]
        self.update()

    def paintEvent(self, event):
        w, h = self.width(), self.height()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        p.setPen(QPen(qcolor("#223247", 140), 1))
        for i in range(1, 4):
            y = int(h * i / 4)
            p.drawLine(0, y, w, y)

        pts = self._points
        mn, mx = min(pts), max(pts)
        rng = (mx - mn) if mx != mn else 1.0

        def xy(i: int, v: float):
            x = (w - 2) * (i / (len(pts) - 1)) + 1
            y = (h - 6) * (1 - ((v - mn) / rng)) + 3
            return x, y

        path = QPainterPath()
        x0, y0 = xy(0, pts[0])
        path.moveTo(x0, y0)
        for i, v in enumerate(pts[1:], start=1):
            x, y = xy(i, v)
            path.lineTo(x, y)

        fill = QPainterPath(path)
        fill.lineTo(w - 1, h - 1)
        fill.lineTo(1, h - 1)
        fill.closeSubpath()

        accent_hex = ACCENT.get(self._accent, ACCENT["blue"])
        p.fillPath(fill, qcolor(accent_hex, 45))
        p.setPen(QPen(qcolor(accent_hex, 220), 2))
        p.drawPath(path)
