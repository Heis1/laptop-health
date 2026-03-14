# ui_v2/widgets/busy_overlay.py
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets


class BusyOverlay(QtWidgets.QWidget):
    """
    Lightweight busy overlay you can place on top of any widget.
    - Semi-transparent tint
    - Centered spinner + label
    - Non-invasive: does not need to block the whole window
    """
    def __init__(self, parent: QtWidgets.QWidget, text: str = "Working…") -> None:
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self._text = QtWidgets.QLabel(text)
        self._text.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        self._movie = QtGui.QMovie(self._spinner_gif_bytes(), b"GIF", self)
        self._spinner = QtWidgets.QLabel()
        self._spinner.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._spinner.setMovie(self._movie)

        box = QtWidgets.QVBoxLayout()
        box.setContentsMargins(24, 24, 24, 24)
        box.setSpacing(10)
        box.addStretch(1)
        box.addWidget(self._spinner, 0, QtCore.Qt.AlignmentFlag.AlignHCenter)
        box.addWidget(self._text, 0, QtCore.Qt.AlignmentFlag.AlignHCenter)
        box.addStretch(1)

        panel = QtWidgets.QFrame()
        panel.setObjectName("busyOverlayPanel")
        panel.setLayout(box)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(panel)

        # Styling kept simple; your global QSS will still apply.
        self.setStyleSheet("""
            #busyOverlayPanel {
                background: rgba(0, 0, 0, 0.35);
                border-radius: 18px;
            }
            QLabel {
                color: rgba(255, 255, 255, 0.92);
                font-size: 13px;
            }
        """)

        self.hide()

    def setText(self, text: str) -> None:
        self._text.setText(text)

    def start(self) -> None:
        self.resize(self.parentWidget().size())
        self.raise_()
        self.show()
        self._movie.start()

    def stop(self) -> None:
        self._movie.stop()
        self.hide()

    def eventFilter(self, obj, event):
        if obj is self.parentWidget() and event.type() == QtCore.QEvent.Type.Resize:
            self.resize(self.parentWidget().size())
        return super().eventFilter(obj, event)

    @staticmethod
    def _spinner_gif_bytes() -> bytes:
        """
        Tiny embedded spinner GIF (base64 decoded).
        Keeps this widget self-contained.
        """
        import base64
        return base64.b64decode(
            b"R0lGODlhIAAgAPQAAP///wAAAMbGxq+vr+fn5+Li4tDQ0P39/dfX19bW1tbW1tTU"
            b"1NPT09LS0tHR0c/Pz8zMzMvLy9fX19nZ2f///yH5BAEAAB8ALAAAAAAgACAAAAWc"
            b"4CeOZGmeaKqubOu+cCzPdF2CqHkKJbEoG5wYF2o0EoYAAo1Cw2bQKQbXwGg4QXo2"
            b"gqI0pYwN5gNQxQKZy2nMZk1K8YyQkK1o8p4cQ8GQ6Ew4hK0lCk6oYI6F6hQwqSg5"
            b"7FQ4lD0wCkYyGQpGdGqYkCkJkQqvCkYgYyEAOw=="
        )
