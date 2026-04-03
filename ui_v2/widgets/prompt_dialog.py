from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QStyle, QVBoxLayout, QWidget


_ACCENT_STRIP = {
    "blue": "rgba(96,165,250,0.95)",
    "green": "rgba(52,211,153,0.95)",
    "orange": "rgba(255,190,120,0.95)",
    "red": "rgba(248,113,113,0.95)",
    "slate": "rgba(148,163,184,0.95)",
}


class PromptDialog(QDialog):
    def __init__(
        self,
        parent: QWidget,
        title: str,
        message: str,
        *,
        accent: str = "orange",
        ok_text: str = "OK",
        cancel_text: str | None = None,
    ) -> None:
        super().__init__(parent)

        self.setModal(True)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        host = parent.window()
        self.setGeometry(host.geometry())

        strip = _ACCENT_STRIP.get(accent, _ACCENT_STRIP["orange"])
        icon_style = QStyle.SP_MessageBoxWarning if accent in {"orange", "red"} else QStyle.SP_MessageBoxInformation

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scrim = QFrame()
        scrim.setObjectName("PromptScrim")
        scrim_lay = QVBoxLayout(scrim)
        scrim_lay.setContentsMargins(0, 0, 0, 0)
        scrim_lay.setSpacing(0)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addStretch(1)

        card = QFrame()
        card.setObjectName("PromptCard")
        card.setFixedWidth(500)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(10)

        hdr = QHBoxLayout()
        ico = QLabel()
        ico.setPixmap(self.style().standardIcon(icon_style).pixmap(20, 20))
        hdr.addWidget(ico)

        title_lbl = QLabel(title)
        title_lbl.setObjectName("PromptTitle")
        hdr.addWidget(title_lbl)
        hdr.addStretch(1)

        btn_x = QPushButton("✕")
        btn_x.setObjectName("PromptX")
        btn_x.setCursor(Qt.PointingHandCursor)
        btn_x.clicked.connect(self.reject if cancel_text else self.accept)
        hdr.addWidget(btn_x)
        lay.addLayout(hdr)

        body = QLabel(message)
        body.setObjectName("PromptBody")
        body.setWordWrap(True)
        lay.addWidget(body)

        btns = QHBoxLayout()
        btns.addStretch(1)

        if cancel_text is not None:
            btn_cancel = QPushButton(cancel_text)
            btn_cancel.setObjectName("ActionBtn")
            btn_cancel.clicked.connect(self.reject)
            btns.addWidget(btn_cancel)

        btn_ok = QPushButton(ok_text)
        btn_ok.setObjectName("ActionBtn")
        btn_ok.clicked.connect(self.accept)
        btns.addWidget(btn_ok)
        lay.addLayout(btns)

        row.addWidget(card)
        row.addStretch(1)
        scrim_lay.addStretch(1)
        scrim_lay.addLayout(row)
        scrim_lay.addStretch(1)
        root.addWidget(scrim)

        if cancel_text is not None:
            scrim.mousePressEvent = lambda e: self.reject()

        self.setStyleSheet(
            f"""
            QFrame#PromptScrim {{
                background: rgba(0, 0, 0, 0.55);
            }}
            QFrame#PromptCard {{
                background: rgba(10, 14, 22, 0.92);
                border: 1px solid rgba(255,255,255,0.14);
                border-left: 6px solid {strip};
                border-radius: 16px;
            }}
            QLabel#PromptTitle {{
                color: rgba(255,255,255,0.96);
                font-weight: 700;
                font-size: 16px;
            }}
            QLabel#PromptBody {{
                color: rgba(255,255,255,0.82);
                font-size: 12px;
            }}
            QPushButton#PromptX {{
                color: rgba(255,255,255,0.75);
                background: transparent;
                border: 0px;
                padding: 4px 8px;
                border-radius: 10px;
                font-size: 14px;
            }}
            QPushButton#PromptX:hover {{
                background: rgba(255,255,255,0.10);
                color: rgba(255,255,255,0.92);
            }}
            QPushButton#ActionBtn {{
                color: rgba(255,255,255,0.92);
                background: rgba(255,255,255,0.08);
                border: 1px solid rgba(255,255,255,0.14);
                padding: 7px 12px;
                border-radius: 10px;
                min-width: 110px;
            }}
            QPushButton#ActionBtn:hover {{
                background: rgba(255,255,255,0.12);
                border: 1px solid rgba(255,255,255,0.18);
            }}
            QPushButton#ActionBtn:pressed {{
                background: rgba(255,255,255,0.06);
            }}
            """
        )

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)
