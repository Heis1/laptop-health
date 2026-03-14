from __future__ import annotations
from PySide6.QtWidgets import QWidget, QGraphicsDropShadowEffect
from PySide6.QtGui import QColor

def apply_card_shadow(w: QWidget) -> None:
    eff = QGraphicsDropShadowEffect(w)
    eff.setBlurRadius(26)
    eff.setOffset(0, 10)
    eff.setColor(QColor(0, 0, 0, 140))
    w.setGraphicsEffect(eff)
