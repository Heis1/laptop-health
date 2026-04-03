from __future__ import annotations
import json
import os
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QPoint, Qt, QThreadPool, QTimer
from PySide6.QtGui import QFont, QMouseEvent, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFrame, QHBoxLayout, QLabel, QMainWindow, QStackedWidget,
    QVBoxLayout, QWidget, QStyle, QToolButton, QDialog
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
from ui_v2.widgets.probe_settings_dialog import ProbeSettingsDialog


UI_PREFS_PATH = os.path.join(os.path.expanduser("~"), ".config", "laptop-health", "ui_prefs.json")
APP_ICON_PATH = str(Path(__file__).resolve().parents[1] / "assets" / "laptop-health.png")


def _load_theme_mode() -> str:
    try:
        with open(UI_PREFS_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return "light" if str(data.get("theme_mode", "dark")).lower() == "light" else "dark"
    except Exception:
        return "dark"


def _save_theme_mode(mode: str) -> None:
    os.makedirs(os.path.dirname(UI_PREFS_PATH), mode=0o700, exist_ok=True)
    with open(UI_PREFS_PATH, "w", encoding="utf-8") as handle:
        json.dump({"theme_mode": mode}, handle, indent=2)


def _shutdown_widget_timers_and_pools(page: QWidget) -> None:
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

    for obj in [page, *page.findChildren(QWidget)]:
        pool = getattr(obj, "pool", None)
        if isinstance(pool, QThreadPool):
            try:
                pool.clear()
                pool.waitForDone(250)
            except Exception:
                pass


class PopoutWindow(QWidget):
    def __init__(self, title: str, subtitle: str, content: QWidget, theme_mode: str = "dark"):
        super().__init__(None, Qt.Window | Qt.FramelessWindowHint)
        self._drag_offset: QPoint | None = None
        self._content = content
        self._theme_mode = theme_mode
        self.setObjectName("PopoutWindow")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.resize(1120, 760)
        self.setMinimumSize(900, 620)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(0)

        content_frame = QFrame()
        content_frame.setObjectName("PopoutSurface")
        content_frame.setAttribute(Qt.WA_StyledBackground, True)
        content_l = QVBoxLayout(content_frame)
        content_l.setContentsMargins(14, 10, 14, 14)
        content_l.setSpacing(8)

        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(8)
        controls.addStretch(1)

        self.btn_min = QToolButton()
        self.btn_min.setObjectName("TitleBtn")
        self.btn_min.setToolTip("Minimize")
        self.btn_min.setText("−")
        self.btn_min.clicked.connect(self.showMinimized)
        controls.addWidget(self.btn_min)

        self.btn_max = QToolButton()
        self.btn_max.setObjectName("TitleBtn")
        self.btn_max.setToolTip("Maximize")
        self.btn_max.setText("□")
        self.btn_max.clicked.connect(self._toggle_maximize)
        controls.addWidget(self.btn_max)

        self.btn_close = QToolButton()
        self.btn_close.setObjectName("TitleCloseBtn")
        self.btn_close.setToolTip("Close")
        self.btn_close.setText("✕")
        self.btn_close.clicked.connect(self.close)
        controls.addWidget(self.btn_close)
        content_l.addLayout(controls)

        page_host = QWidget()
        page_host.setObjectName("PopoutContent")
        page_host.setAttribute(Qt.WA_StyledBackground, True)
        page_host_l = QVBoxLayout(page_host)
        page_host_l.setContentsMargins(0, 0, 0, 0)
        page_host_l.setSpacing(0)

        content.setObjectName("PopoutContent")
        content.setAttribute(Qt.WA_StyledBackground, True)
        page_host_l.addWidget(content, 1)
        content_l.addWidget(page_host, 1)
        root.addWidget(content_frame, 1)
        self._apply_theme()

    def _apply_theme(self) -> None:
        self.setStyleSheet(qss(self._theme_mode))

    def _toggle_maximize(self) -> None:
        if self.isMaximized():
            self.showNormal()
            self.btn_max.setText("□")
            self.btn_max.setToolTip("Maximize")
        else:
            self.showMaximized()
            self.btn_max.setText("❐")
            self.btn_max.setToolTip("Restore")

    def _is_title_drag_target(self, widget: QWidget | None, pos: QPoint) -> bool:
        if pos.y() > 56:
            return False
        while widget is not None:
            if widget in {self.btn_min, self.btn_max, self.btn_close}:
                return False
            if isinstance(widget, (QDialog, QFrame)):
                break
            widget = widget.parentWidget()
        return True

    def mousePressEvent(self, event: QMouseEvent):
        pos = event.position().toPoint()
        if event.button() == Qt.LeftButton and self._is_title_drag_target(self.childAt(pos), pos):
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag_offset is not None and (event.buttons() & Qt.LeftButton) and not self.isMaximized():
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        pos = event.position().toPoint()
        if event.button() == Qt.LeftButton and self._is_title_drag_target(self.childAt(pos), pos):
            self._toggle_maximize()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def closeEvent(self, event):
        try:
            _shutdown_widget_timers_and_pools(self._content)
        finally:
            super().closeEvent(event)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._theme_mode = _load_theme_mode()
        self._drag_offset: QPoint | None = None
        self._popouts: list[PopoutWindow] = []

        # Modern UI font
        app_font = QFont("Segoe UI")
        app_font.setPointSize(10)
        self.setFont(app_font)
        self.setWindowTitle("Laptop Health")
        if os.path.exists(APP_ICON_PATH):
            self.setWindowIcon(QIcon(APP_ICON_PATH))
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        self.resize(1280, 820)
        self.setMinimumSize(980, 700)

        root = QWidget()
        self.setCentralWidget(root)
        root_l = QVBoxLayout(root)
        root_l.setContentsMargins(12, 10, 12, 12)
        root_l.setSpacing(10)

        self.titlebar = QFrame()
        self.titlebar.setObjectName("TitleBar")
        t = QHBoxLayout(self.titlebar)
        t.setContentsMargins(14, 10, 14, 10)
        t.setSpacing(10)

        self.title_mark = QLabel()
        self.title_mark.setObjectName("TitleBarMark")
        self.title_mark.setAlignment(Qt.AlignCenter)
        if os.path.exists(APP_ICON_PATH):
            title_pixmap = QPixmap(APP_ICON_PATH)
            if not title_pixmap.isNull():
                self.title_mark.setPixmap(
                    title_pixmap.scaled(24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )
        if self.title_mark.pixmap() is None:
            self.title_mark.setText("LH")
        t.addWidget(self.title_mark, 0, Qt.AlignVCenter)

        title_copy = QVBoxLayout()
        title_copy.setContentsMargins(0, 0, 0, 0)
        title_copy.setSpacing(0)

        self.title_label = QLabel("Laptop Health")
        self.title_label.setObjectName("TitleBarText")
        title_copy.addWidget(self.title_label)

        self.title_sub = QLabel("System insight for Linux laptops")
        self.title_sub.setObjectName("TitleBarSub")
        title_copy.addWidget(self.title_sub)
        t.addLayout(title_copy)

        t.addStretch(1)

        self.btn_theme = QToolButton()
        self.btn_theme.setObjectName("TopBtn")
        self.btn_theme.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))
        self.btn_theme.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.btn_theme.clicked.connect(self._toggle_theme_mode)
        self._sync_theme_action()
        t.addWidget(self.btn_theme)

        self.btn_min = QToolButton()
        self.btn_min.setObjectName("TitleBtn")
        self.btn_min.setToolTip("Minimize")
        self.btn_min.setText("−")
        self.btn_min.clicked.connect(self.showMinimized)
        t.addWidget(self.btn_min)

        self.btn_max = QToolButton()
        self.btn_max.setObjectName("TitleBtn")
        self.btn_max.setToolTip("Maximize")
        self.btn_max.setText("□")
        self.btn_max.clicked.connect(self._toggle_maximize)
        t.addWidget(self.btn_max)

        self.btn_close = QToolButton()
        self.btn_close.setObjectName("TitleCloseBtn")
        self.btn_close.setToolTip("Close")
        self.btn_close.setText("⏻")
        self.btn_close.setFont(QFont("Segoe UI", 18))
        self.btn_close.clicked.connect(self.close)
        t.addWidget(self.btn_close)

        root_l.addWidget(self.titlebar)

        main = QHBoxLayout()
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(14)
        root_l.addLayout(main, 1)

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
        c.setSpacing(0)
        main.addWidget(content, 1)

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
        for key, btn in self.sidebar.popout_buttons.items():
            btn.clicked.connect(lambda checked=False, k=key: self._open_popout(k))
        # Dev Tools is only present in developer mode
        if "dev" in getattr(self.sidebar, "buttons", {}):
            self.sidebar.buttons["dev"].clicked.connect(lambda: self._go("dev"))
        self._apply_theme_mode()

    def _make_page(self, key: str) -> QWidget:
        if key == "dashboard":
            return DashboardPage(lambda: self._go("remote"))
        if key == "power":
            return PowerPage()
        if key == "storage":
            return StoragePage()
        if key == "network":
            return NetworkPage()
        if key == "remote":
            return RemotePage(self._open_probe_settings, self)
        if key == "updates":
            return UpdatesPage()
        if key == "dev":
            return DevToolsPage()
        raise KeyError(key)

    def _page_title_for_key(self, key: str) -> tuple[str, str]:
        mapping = {
            "dashboard": ("Overview", "Live system summary"),
            "power": ("Power & Thermal", "Wake activity and thermal analysis"),
            "storage": ("Storage", "Mounted drives and storage analysis"),
            "network": ("Network", "Live network metrics and discovery"),
            "remote": ("Probe/s", "Probe management and remote monitoring"),
            "updates": ("Updates", "System package and release updates"),
            "dev": ("Dev Tools", "Developer utilities and simulation"),
        }
        return mapping.get(key, ("Laptop Health", ""))

    def _open_popout(self, key: str) -> None:
        try:
            page = self._make_page(key)
        except Exception:
            return
        title, subtitle = self._page_title_for_key(key)
        win = PopoutWindow(title, subtitle, page, self._theme_mode)
        win.setAttribute(Qt.WA_DeleteOnClose, True)
        win.destroyed.connect(lambda *args, w=win: self._popouts.remove(w) if w in self._popouts else None)
        self._popouts.append(win)
        win.show()
        win.raise_()
        win.activateWindow()

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        super().mouseDoubleClickEvent(event)
        if event.button() == Qt.LeftButton:
            self._toggle_maximize()

    def _toggle_maximize(self) -> None:
        if self.isMaximized():
            self.showNormal()
            self.btn_max.setText("□")
            self.btn_max.setToolTip("Maximize")
        else:
            self.showMaximized()
            self.btn_max.setText("❐")
            self.btn_max.setToolTip("Restore")

    def _is_title_drag_target(self, widget: QWidget | None) -> bool:
        while widget is not None:
            if widget in {self.btn_theme, self.btn_min, self.btn_max, self.btn_close}:
                return False
            if widget is self.titlebar:
                return True
            widget = widget.parentWidget()
        return False

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton and self._is_title_drag_target(self.childAt(event.position().toPoint())):
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag_offset is not None and (event.buttons() & Qt.LeftButton) and not self.isMaximized():
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._drag_offset = None
        super().mouseReleaseEvent(event)

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

    def _go(self, key: str) -> None:
        self._set_active_nav(key)
        self.stack.setCurrentIndex(self.page_order.index(key))
        self._set_active_nav(key)

    def _sync_theme_action(self) -> None:
        label = "Light Mode" if self._theme_mode == "dark" else "Dark Mode"
        self.btn_theme.setText(label)
        self.btn_theme.setToolTip(f"Switch to {label}")

    def _apply_theme_mode(self) -> None:
        app = QApplication.instance()
        if app is None:
            return
        app.setProperty("theme_mode", self._theme_mode)
        app.setStyleSheet(qss(self._theme_mode))
        for page in self.pages.values():
            try:
                if hasattr(page, "apply_theme_mode"):
                    page.apply_theme_mode(self._theme_mode)
            except Exception:
                pass
        for win in list(self._popouts):
            try:
                win._theme_mode = self._theme_mode
                win._apply_theme()
                if hasattr(win._content, "apply_theme_mode"):
                    win._content.apply_theme_mode(self._theme_mode)
            except Exception:
                pass
        self._sync_theme_action()

    def _toggle_theme_mode(self) -> None:
        self._theme_mode = "light" if self._theme_mode == "dark" else "dark"
        _save_theme_mode(self._theme_mode)
        self._apply_theme_mode()

    def _set_active_nav(self, key: str):
        for k, btn in self.sidebar.buttons.items():
            btn.setProperty("active", "1" if k == key else "0")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
            btn.update()
            row = self.sidebar.rows.get(k)
            if row is not None:
                row.setProperty("active", "1" if k == key else "0")
                row.style().unpolish(row)
                row.style().polish(row)
                row.update()

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
