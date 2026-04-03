from __future__ import annotations
import os
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import Qt, QThreadPool, QTimer
from PySide6.QtGui import QFont
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
from ui_v2.pages.remote import RemotePage
from ui_v2.pages.storage import StoragePage
from ui_v2.pages.updates import UpdatesPage
from ui_v2.pages.devtools import DevToolsPage
from ui_v2.services.probe import ProbeConfig, load_probe_configs, save_probe_config, save_probe_configs
from ui_v2.widgets.export_report_dialog import ExportReportDialog
from ui_v2.widgets.probe_settings_dialog import ProbeSettingsDialog
from ui_v2.export.report_pdf import export_current_view_pdf, export_system_report_pdf, capture_widget_pixmap


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # Modern UI font
        app_font = QFont("Segoe UI")
        app_font.setPointSize(10)
        self.setFont(app_font)
        self.setWindowTitle("Laptop Health (UI v2)")
        self.resize(1280, 820)
        self.setMinimumSize(980, 700)

        root = QWidget()
        self.setCentralWidget(root)
        main = QHBoxLayout(root)
        main.setContentsMargins(16, 14, 16, 16)
        main.setSpacing(14)

        left_col = QWidget()
        left_col_l = QVBoxLayout(left_col)
        left_col_l.setContentsMargins(0, 0, 0, 0)
        left_col_l.setSpacing(10)

        self.sidebar = Sidebar()
        left_col_l.addWidget(self.sidebar)
        left_col.setMaximumWidth(260)

        main.addWidget(left_col)

        content = QWidget()
        c = QVBoxLayout(content)
        c.setContentsMargins(0, 0, 0, 0)
        c.setSpacing(8)
        main.addWidget(content, 1)

        top = QFrame()
        t = QHBoxLayout(top)
        t.setContentsMargins(0, 0, 0, 0)
        t.setSpacing(10)
        t.addStretch(1)

        # Header actions
        self.btn_export = QToolButton()
        self.btn_export.setObjectName("TopBtn")
        self.btn_export.setIcon(self.style().standardIcon(QStyle.SP_DialogSaveButton))
        self.btn_export.setText("Actions")
        self.btn_export.setToolTip("View export actions")
        self.btn_export.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.btn_export.setPopupMode(QToolButton.InstantPopup)

        export_menu = QMenu(self)
        act_current = export_menu.addAction("Export current view (PDF)...")
        act_current.triggered.connect(self._export_current_pdf)
        act_report = export_menu.addAction("Export system report (PDF)...")
        act_report.triggered.connect(self._export_system_report)

        self.btn_export.setMenu(export_menu)
        t.addWidget(self.btn_export)
        
        # Exit button

        exit_btn = QToolButton()
        exit_btn.setObjectName("ExitBtn")
        exit_btn.setToolTip("Exit Laptop Health")

        exit_btn.setText("⏻")
        exit_btn.setFont(QFont("Segoe UI", 18))

        exit_btn.setAutoRaise(True)
        exit_btn.clicked.connect(self.close)

        t.addWidget(exit_btn) 
        
        
        c.addWidget(top, 0, Qt.AlignTop)

        self.stack = QStackedWidget()
        self.pages = {
            "dashboard": DashboardPage(lambda: self._go("remote")),
            "power": PowerPage(),
            "storage": StoragePage(),
            "network": NetworkPage(),
            "remote": RemotePage(self._open_probe_settings, self),
            "updates": UpdatesPage(),
            "dev": DevToolsPage(),
        }
        self.page_order = ["dashboard", "power", "storage", "network", "remote", "updates", "dev"]
        for k in self.page_order:
            self.stack.addWidget(self.pages[k])
        c.addWidget(self.stack, 1)


        self.sidebar.buttons["dashboard"].clicked.connect(lambda: self._go("dashboard"))
        self.sidebar.buttons["power"].clicked.connect(lambda: self._go("power"))
        self.sidebar.buttons["storage"].clicked.connect(lambda: self._go("storage"))
        self.sidebar.buttons["network"].clicked.connect(lambda: self._go("network"))
        self.sidebar.buttons["remote"].clicked.connect(lambda: self._go("remote"))
        self.sidebar.buttons["updates"].clicked.connect(lambda: self._go("updates"))
        # Dev Tools is only present in developer mode
        if "dev" in getattr(self.sidebar, "buttons", {}):
            self.sidebar.buttons["dev"].clicked.connect(lambda: self._go("dev"))
        self.setStyleSheet(qss())

    def closeEvent(self, event):
        should_accept = False
        try:
            pages = getattr(self, "pages", {}) or {}
            updates_page = pages.get("updates")
            if updates_page is not None:
                try:
                    if not updates_page.shutdown_running_action():
                        return
                except Exception:
                    return

            # 1) Stop page and child-widget timers first
            for page in pages.values():
                try:
                    for timer in page.findChildren(QTimer):
                        try:
                            timer.stop()
                        except Exception:
                            pass
                except Exception:
                    pass

                for attr in ("timer", "timer_fast", "timer_slow", "timer_probe", "timer_probe_cycle", "scan_feedback_timer"):
                    t = getattr(page, attr, None)
                    if t is not None:
                        try:
                            t.stop()
                        except Exception:
                            pass

                # 2) Clear page-local thread pools
                for obj in [page, *page.findChildren(QWidget)]:
                    pool = getattr(obj, "pool", None)
                    if isinstance(pool, QThreadPool):
                        try:
                            pool.clear()
                            pool.waitForDone(250)
                        except Exception:
                            pass

            # 3) Stop ALL queued global workers + wait briefly
            pool = QThreadPool.globalInstance()
            pool.clear()
            pool.waitForDone(1500)

            # 4) Clear worker refs after pools drained
            for page in pages.values():
                if hasattr(page, "_workers"):
                    try:
                        page._workers.clear()
                    except Exception:
                        pass

            should_accept = True

        finally:
            try:
                if should_accept:
                    event.accept()
                else:
                    event.ignore()
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

    def _open_probe_settings(self, probe_id: str | None = None) -> None:
        configs = load_probe_configs()
        selected = next((cfg for cfg in configs if cfg.id == probe_id), None)
        if selected is None:
            selected = configs[0] if configs else ProbeConfig(id="", name="Raspberry Pi")
        dlg = ProbeSettingsDialog(selected, self)
        if dlg.exec() != QDialog.Accepted:
            return
        updated = dlg.config()
        if probe_id and configs:
            for index, cfg in enumerate(configs):
                if cfg.id == probe_id:
                    configs[index] = updated
                    break
            else:
                configs.append(updated)
            save_probe_configs(configs)
        else:
            save_probe_config(updated)
        for key in ("dashboard", "remote"):
            page = self.pages.get(key)
            if page is None:
                continue
            if hasattr(page, "reload_probe_config"):
                try:
                    page.reload_probe_config()
                except Exception:
                    pass
            if hasattr(page, "refresh_now"):
                try:
                    page.refresh_now()
                except Exception:
                    pass


def main(argv: list[str] | None = None) -> int:
    argv = list(argv or sys.argv)
    if "--dev" in argv:
        os.environ["LAPTOP_HEALTH_DEV"] = "1"
        argv.remove("--dev")

    app = QApplication(argv)
    w = MainWindow()
    w.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
