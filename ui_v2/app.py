from __future__ import annotations
from PySide6.QtWidgets import (
    QApplication,
    QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton, QStackedWidget,
    QVBoxLayout, QWidget, QStyle, QToolButton
)

from ui_v2.theme import qss
from ui_v2.widgets.aspect_container import AspectRatioContainer
from ui_v2.widgets.sidebar import Sidebar
from ui_v2.pages.dashboard import DashboardPage
from ui_v2.pages.power import PowerPage
from ui_v2.pages.network import NetworkPage
from ui_v2.pages.storage import StoragePage
from ui_v2.pages.updates import UpdatesPage
from ui_v2.pages.devtools import DevToolsPage


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # Modern UI font
        from PySide6.QtGui import QFont
        app_font = QFont("Segoe UI")
        app_font.setPointSize(10)
        self.setFont(app_font)
        self.setWindowTitle("Laptop Health (UI v2)")
        # Keep the dashboard tight (prevents wide dead space)
        self.resize(1180, 780)
        self.setMinimumWidth(1080)
        self.setMaximumWidth(1280)
        self.resize(1280, 820)

        root = QWidget()
        # Keep dashboard proportional inside the window (no scrollbars).
        self._aspect = AspectRatioContainer(ratio=423/259)
        self.resize(1269, 777)
        self.setMinimumSize(1269, 777)
        self._aspect.setWidget(root)
        self.setCentralWidget(self._aspect)
        main = QHBoxLayout(root)
        main.setContentsMargins(18, 18, 18, 18)
        main.setSpacing(16)

        self.sidebar = Sidebar()
        main.addWidget(self.sidebar)

        content = QWidget()
        c = QVBoxLayout(content)
        c.setContentsMargins(0, 0, 0, 0)
        c.setSpacing(16)
        main.addWidget(content, 1)

        top = QFrame()
        t = QHBoxLayout(top)
        t.setContentsMargins(6, 6, 6, 6)
        t.setSpacing(12)

        title = QLabel("Laptop Health Dashboard")
        title.setObjectName("PageTitle")
        t.addWidget(title)
        t.addStretch(1)

        export = QPushButton("Export")
        export.setObjectName("TopBtn")
        export.setIcon(self.style().standardIcon(QStyle.SP_DialogSaveButton))
        export.setEnabled(False)
        export.setToolTip("Export (coming soon)")
        t.addWidget(export)

       #Exit Button configuration
        from PySide6.QtGui import QFont

        exit_btn = QToolButton()
        exit_btn.setObjectName("ExitBtn")
        exit_btn.setToolTip("Exit Laptop Health")

        exit_btn.setText("⏻")
        exit_btn.setFont(QFont("Segoe UI", 18))

        exit_btn.setAutoRaise(True)
        exit_btn.clicked.connect(self.close)

        t.addWidget(exit_btn) 
        
        
        c.addWidget(top)

        self.stack = QStackedWidget()
        self.pages = {
            "dashboard": DashboardPage(),
            "power": PowerPage(),
            "storage": StoragePage(),
            "network": NetworkPage(),
            "updates": UpdatesPage(),
            "dev": DevToolsPage(),
        }
        order = ["dashboard", "power", "storage", "network", "updates", "dev"]
        for k in order:
            self.stack.addWidget(self.pages[k])
        c.addWidget(self.stack, 1)


        self.sidebar.buttons["dashboard"].clicked.connect(lambda: self._go("dashboard"))
        self.sidebar.buttons["power"].clicked.connect(lambda: self._go("power"))
        self.sidebar.buttons["storage"].clicked.connect(lambda: self._go("storage"))
        self.sidebar.buttons["network"].clicked.connect(lambda: self._go("network"))
        self.sidebar.buttons["updates"].clicked.connect(lambda: self._go("updates"))
        self.sidebar.buttons["dev"].clicked.connect(lambda: self._go("dev"))

        self.setStyleSheet(qss())

    def closeEvent(self, event):
        # Graceful shutdown:
        # stop timers, wait briefly for threadpools, then close.
        try:
            pages = getattr(self, "pages", {}) or {}
            for page in pages.values():
                # Stop QTimers (dashboard refresh, etc.)
                t = getattr(page, "timer", None)
                if t is not None:
                    try:
                        t.stop()
                    except Exception:
                        pass

                # Clear worker references (but only after pool wait)
                pool = getattr(page, "pool", None)
                if pool is not None:
                    try:
                        pool.waitForDone(1500)  # ms; short, prevents hang
                    except Exception:
                        pass

                # If the page tracks workers, clear after waiting
                if hasattr(page, "_workers"):
                    try:
                        page._workers.clear()
                    except Exception:
                        pass
        finally:
            try:
                event.accept()
            except Exception:
                pass


    def _go(self, key: str) -> None:
        self._set_active_nav(key)
        order = ["dashboard", "power", "storage", "network", "updates", "dev"]
        self.stack.setCurrentIndex(order.index(key))
        self._set_active_nav(key)

    def _set_active_nav(self, key: str):
        for k, btn in self.sidebar.buttons.items():
            btn.setProperty("active", "1" if k == key else "0")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
            btn.update()

