from __future__ import annotations
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QFrame, QHBoxLayout, QLabel, QMainWindow, QStackedWidget,
    QVBoxLayout, QWidget, QStyle, QToolButton, QMenu, QDialog
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
from ui_v2.widgets.export_report_dialog import ExportReportDialog
from ui_v2.export.report_pdf import export_current_view_pdf, export_system_report_pdf, capture_widget_pixmap


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

       #Export Button configuration
        self.btn_export = QToolButton()
        self.btn_export.setObjectName("TopBtn")
        self.btn_export.setIcon(self.style().standardIcon(QStyle.SP_DialogSaveButton))
        self.btn_export.setText("Export")
        self.btn_export.setToolTip("Export options")
        self.btn_export.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.btn_export.setPopupMode(QToolButton.InstantPopup)

        export_menu = QMenu(self)
        act_current = export_menu.addAction("Export current view (PDF)...")
        act_current.triggered.connect(self._export_current_pdf)
        act_report = export_menu.addAction("Export system report (PDF)...")
        act_report.triggered.connect(self._export_system_report)

        self.btn_export.setMenu(export_menu)
        t.addWidget(self.btn_export)

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
        self.page_order = ["dashboard", "power", "storage", "network", "updates", "dev"]
        for k in self.page_order:
            self.stack.addWidget(self.pages[k])
        c.addWidget(self.stack, 1)


        self.sidebar.buttons["dashboard"].clicked.connect(lambda: self._go("dashboard"))
        self.sidebar.buttons["power"].clicked.connect(lambda: self._go("power"))
        self.sidebar.buttons["storage"].clicked.connect(lambda: self._go("storage"))
        self.sidebar.buttons["network"].clicked.connect(lambda: self._go("network"))
        self.sidebar.buttons["updates"].clicked.connect(lambda: self._go("updates"))
        # Dev Tools is only present in developer mode
        if "dev" in getattr(self.sidebar, "buttons", {}):
            self.sidebar.buttons["dev"].clicked.connect(lambda: self._go("dev"))
        self.setStyleSheet(qss())

    def closeEvent(self, event):
        from PySide6.QtCore import QThreadPool

        try:
            # 1) Stop timers first
            pages = getattr(self, "pages", {}) or {}
            for page in pages.values():
                t = getattr(page, "timer", None)
                if t is not None:
                    try:
                        t.stop()
                    except Exception:
                        pass

            # 2) Stop ALL queued global workers + wait briefly
            pool = QThreadPool.globalInstance()
            pool.clear()
            pool.waitForDone(1500)

            # 3) Clear worker refs after pool drained
            for page in pages.values():
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

    def _export_current_pdf(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        from PySide6.QtCore import QDateTime

        target = self.stack.currentWidget()
        if target is None:
            return
        self.raise_()
        self.activateWindow()
        target.repaint()
        QApplication.processEvents()

        ts = QDateTime.currentDateTime().toString("yyyy-MM-dd_HHmmss")
        default_name = f"laptop-health_{ts}.pdf"

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export current view",
            default_name,
            "PDF Files (*.pdf)",
        )

        if not path:
            return

        export_current_view_pdf(target, path)

    def _export_system_report(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        from PySide6.QtCore import QDateTime

        dialog = ExportReportDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return

        selections = dialog.selected_sections()
        if not selections:
            return

        ts = QDateTime.currentDateTime().toString("yyyy-MM-dd_HHmmss")
        default_name = f"laptop-health_report_{ts}.pdf"

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export system report",
            default_name,
            "PDF Files (*.pdf)",
        )

        if not path:
            return

        screenshots: dict[str, object] = {}

        # Only capture the dashboard screenshot for the report (sections are text)
        if selections.get("dashboard", False):
            current_index = self.stack.currentIndex()
            dash_idx = self.page_order.index("dashboard")
            if self.stack.currentIndex() != dash_idx:
                self.stack.setCurrentIndex(dash_idx)

            self.raise_()
            self.activateWindow()
            w = self.pages.get("dashboard")
            if w is not None:
                w.repaint()
                QApplication.processEvents()
                screenshots["dashboard"] = capture_widget_pixmap(w, scale=2.0)

            # restore previous page
            if self.stack.currentIndex() != current_index:
                self.stack.setCurrentIndex(current_index)

        export_system_report_pdf(
            path=path,
            screenshots=screenshots,
            sections=selections,
        )

        if self.stack.currentIndex() != current_index:
            self.stack.setCurrentIndex(current_index)

    def _go(self, key: str) -> None:
        self._set_active_nav(key)
        self.stack.setCurrentIndex(self.page_order.index(key))
        self._set_active_nav(key)

    def _set_active_nav(self, key: str):
        for k, btn in self.sidebar.buttons.items():
            btn.setProperty("active", "1" if k == key else "0")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
            btn.update()
