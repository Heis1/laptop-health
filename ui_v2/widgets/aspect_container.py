from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget


class AspectRatioContainer(QWidget):
    """
    Keeps a single child widget scaled to the largest rectangle that fits inside
    this container while preserving a fixed aspect ratio.

    Window can maximize/fullscreen; we letterbox/pillarbox inside the window.
    """
    def __init__(self, ratio: float = 16 / 9, parent: QWidget | None = None):
        super().__init__(parent)
        self._ratio = float(ratio)
        self._child: QWidget | None = None
        self.setAttribute(Qt.WA_StyledBackground, True)

    def set_ratio(self, ratio: float) -> None:
        self._ratio = float(ratio)
        self._apply()

    def setWidget(self, w: QWidget) -> None:
        self._child = w
        w.setParent(self)
        w.show()
        self._apply()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._apply()

    def _apply(self) -> None:
        if self._child is None:
            return
        W = max(1, self.width())
        H = max(1, self.height())
        r = self._ratio if self._ratio > 0 else (16 / 9)

        # largest rect with aspect r inside WxH
        if (W / H) >= r:
            h = H
            w = int(round(h * r))
        else:
            w = W
            h = int(round(w / r))

        x = (W - w) // 2
        y = (H - h) // 2
        self._child.setGeometry(x, y, w, h)
