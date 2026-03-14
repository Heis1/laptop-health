from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import (
    QColor,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QWidget, QSizePolicy

from ui_v2.theme import ACCENT


def qcolor(hexstr: str, alpha: int = 255) -> QColor:
    c = QColor(hexstr)
    c.setAlpha(alpha)
    return c


class Sparkline(QWidget):
    """
    UI-style sparkline:
      - expects points already normalized to 0..1
      - draws soft gradient fill + crisp line
      - avoids per-frame min/max rescaling (more stable like the mock)
    """

    def __init__(self, points: list[float], accent: str = "blue", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._points = points[:] if points else [0.2, 0.35, 0.3, 0.55, 0.4, 0.7, 0.6]
        self._accent = accent
        self.setMinimumHeight(46)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

    def set_points(self, points: list[float]) -> None:
        """Replace sparkline data (expects 0..1 normalized floats)."""
        if not points:
            return
        self._points = points[:]
        self.update()

    def paintEvent(self, event):
        w, h = self.width(), self.height()
        if w <= 2 or h <= 2:
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        # clip to rounded rect (mock-like)
        r = QRectF(0.5, 0.5, w - 1.0, h - 1.0)
        clip = QPainterPath()
        clip.addRoundedRect(r, 8, 8)
        p.setClipPath(clip)

        # subtle grid (very faint)
        grid_pen = QPen(qcolor("#223247", 70), 1)
        p.setPen(grid_pen)
        for frac in (0.33, 0.66):
            y = int(h * frac)
            p.drawLine(0, y, w, y)

        pts = self._points
        n = len(pts)
        if n < 2:
            return

        # points are already normalized 0..1
        def clamp01(x: float) -> float:
            return 0.0 if x < 0.0 else (1.0 if x > 1.0 else float(x))

        def xy(i: int, v: float):
            x = (w - 2) * (i / (n - 1)) + 1
            # more headroom so peaks don't touch top
            top_pad = 6
            bot_pad = 6
            usable = max(1, h - top_pad - bot_pad)
            y = top_pad + usable * (1.0 - clamp01(v))
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

        # gradient fill (stronger near line, fades toward bottom)
        g = QLinearGradient(0, 0, 0, h)
        g.setColorAt(0.0, qcolor(accent_hex, 110))
        g.setColorAt(0.55, qcolor(accent_hex, 55))
        g.setColorAt(1.0, qcolor(accent_hex, 10))
        p.fillPath(fill, g)

        # soft glow under the line
        p.setPen(QPen(qcolor(accent_hex, 60), 5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPath(path)

        # crisp line on top
        p.setPen(QPen(qcolor(accent_hex, 220), 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPath(path)
