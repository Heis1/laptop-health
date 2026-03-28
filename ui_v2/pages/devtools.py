from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ui_v2.services.devtools_state import (
    get_linux_updates_mode,
    get_sidebar_update_mode,
    reset_flags,
    set_linux_updates_mode,
    set_sidebar_update_mode,
)


class DevActionCard(QFrame):
    clicked = Signal()

    def __init__(self, text: str, accent: str, detail: str | None = None):
        super().__init__()
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(74)

        palette = {
            "blue": (
                "rgba(96,165,250,0.18)",
                "rgba(96,165,250,0.34)",
            ),
            "orange": (
                "rgba(251,146,60,0.18)",
                "rgba(251,146,60,0.38)",
            ),
            "slate": (
                "rgba(148,163,184,0.18)",
                "rgba(148,163,184,0.34)",
            ),
            "red": (
                "rgba(248,113,113,0.18)",
                "rgba(248,113,113,0.36)",
            ),
        }
        bg, border = palette[accent]
        self.setStyleSheet(
            f"background: {bg};"
            f"border: 1px solid {border};"
            "border-radius: 12px;"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(3)

        title = QLabel(text)
        title.setWordWrap(True)
        title.setStyleSheet(
            "color: rgba(255,255,255,0.96);"
            "font-size: 12px;"
            "font-weight: 800;"
        )
        layout.addWidget(title)

        if detail:
            subtitle = QLabel(detail)
            subtitle.setWordWrap(True)
            subtitle.setStyleSheet(
                "color: rgba(255,255,255,0.68);"
                "font-size: 11px;"
                "font-weight: 500;"
            )
            layout.addWidget(subtitle)

    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)


def _make_button(text: str, accent: str, detail: str | None = None) -> DevActionCard:
    return DevActionCard(text, accent, detail)


class DevToolsPage(QWidget):
    def __init__(self):
        super().__init__()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: 0; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
        )
        outer.addWidget(scroll)

        content = QWidget()
        scroll.setWidget(content)

        root = QVBoxLayout(content)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(14)

        hero = QFrame()
        hero.setStyleSheet(
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:1,"
            " stop:0 rgba(13,27,45,0.96), stop:1 rgba(22,38,70,0.96));"
            "border: 1px solid rgba(96,165,250,0.20);"
            "border-radius: 18px;"
        )
        hero_l = QVBoxLayout(hero)
        hero_l.setContentsMargins(18, 16, 18, 16)
        hero_l.setSpacing(6)

        title = QLabel("Dev Tools")
        title.setStyleSheet("color: rgba(255,255,255,0.98); font-size: 22px; font-weight: 800;")
        hero_l.addWidget(title)

        subtitle = QLabel("Preview runtime-only UI states without changing the real machine or release feed.")
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: rgba(191,219,254,0.76); font-size: 12px;")
        hero_l.addWidget(subtitle)

        root.addWidget(hero)

        card = QFrame()
        card.setStyleSheet(
            "background: rgba(255,255,255,0.03);"
            "border: 1px solid rgba(255,255,255,0.08);"
            "border-radius: 18px;"
        )
        card_l = QVBoxLayout(card)
        card_l.setContentsMargins(18, 18, 18, 18)
        card_l.setSpacing(14)

        section = QLabel("Sidebar Update Footer")
        section.setStyleSheet("color: rgba(255,255,255,0.94); font-size: 15px; font-weight: 800;")
        card_l.addWidget(section)

        desc = QLabel(
            "Switch between different sidebar footer states so you can inspect the exact colors, chip styles, and copy."
        )
        desc.setWordWrap(True)
        desc.setMinimumHeight(38)
        desc.setStyleSheet("color: rgba(255,255,255,0.66); font-size: 12px;")
        card_l.addWidget(desc)

        self.sidebar_status = QLabel("")
        self.sidebar_status.setWordWrap(True)
        self.sidebar_status.setMinimumHeight(44)
        self.sidebar_status.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.sidebar_status.setStyleSheet(
            "color: rgba(255,255,255,0.88);"
            "background: rgba(255,255,255,0.04);"
            "border: 1px solid rgba(255,255,255,0.08);"
            "border-radius: 12px;"
            "padding: 10px 12px;"
            "font-size: 12px;"
            "font-weight: 600;"
        )
        card_l.addWidget(self.sidebar_status)

        self.btn_real = _make_button("Use real release state", "blue", "Follow the real GitHub release check")
        self.btn_real.clicked.connect(lambda: self._set_sidebar_mode("real"))
        card_l.addWidget(self.btn_real)

        self.btn_available = _make_button("Simulate update available", "orange", "Preview the orange update chip")
        self.btn_available.clicked.connect(lambda: self._set_sidebar_mode("available"))
        card_l.addWidget(self.btn_available)

        self.btn_current = _make_button("Simulate up to date", "slate", "Preview the neutral current-state chip")
        self.btn_current.clicked.connect(lambda: self._set_sidebar_mode("current"))
        card_l.addWidget(self.btn_current)

        self.btn_error = _make_button("Simulate check failed", "red", "Preview the failed release-check state")
        self.btn_error.clicked.connect(lambda: self._set_sidebar_mode("error"))
        card_l.addWidget(self.btn_error)

        footer = QHBoxLayout()
        footer.addStretch(1)
        self.btn_reset = _make_button("Reset all dev flags", "blue", "Clear every active simulation mode")
        self.btn_reset.clicked.connect(self._reset_all_flags)
        footer.addWidget(self.btn_reset)
        card_l.addLayout(footer)

        root.addWidget(card)

        os_card = QFrame()
        os_card.setStyleSheet(
            "background: rgba(255,255,255,0.03);"
            "border: 1px solid rgba(255,255,255,0.08);"
            "border-radius: 18px;"
        )
        os_card_l = QVBoxLayout(os_card)
        os_card_l.setContentsMargins(18, 18, 18, 18)
        os_card_l.setSpacing(14)

        os_title = QLabel("Linux Update Simulation")
        os_title.setStyleSheet("color: rgba(255,255,255,0.94); font-size: 15px; font-weight: 800;")
        os_card_l.addWidget(os_title)

        os_desc = QLabel(
            "Override the Linux package-update state seen by the Updates page and other update summary views."
        )
        os_desc.setWordWrap(True)
        os_desc.setMinimumHeight(38)
        os_desc.setStyleSheet("color: rgba(255,255,255,0.66); font-size: 12px;")
        os_card_l.addWidget(os_desc)

        self.os_status = QLabel("")
        self.os_status.setWordWrap(True)
        self.os_status.setMinimumHeight(44)
        self.os_status.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.os_status.setStyleSheet(
            "color: rgba(255,255,255,0.88);"
            "background: rgba(255,255,255,0.04);"
            "border: 1px solid rgba(255,255,255,0.08);"
            "border-radius: 12px;"
            "padding: 10px 12px;"
            "font-size: 12px;"
            "font-weight: 600;"
        )
        os_card_l.addWidget(self.os_status)

        buttons = [
            ("Use real OS state", "blue", "real", "Follow the live package state"),
            ("Clean system", "slate", "clean", "No pending Linux package updates"),
            ("Normal updates", "orange", "updates", "Regular package updates available"),
            ("Security updates", "red", "security", "Security updates require attention"),
            ("Kept back packages", "orange", "kept", "Show packages held back from upgrade"),
            ("Held packages", "red", "held", "Show manually held packages"),
            ("Reboot required", "orange", "reboot", "Preview post-update reboot state"),
            ("Mixed warning state", "red", "mixed", "Security, reboot, kept and held combined"),
            ("Simulate check failure", "red", "error", "Force update check to fail"),
        ]
        for label, accent, mode, detail in buttons:
            btn = _make_button(label, accent, detail)
            btn.clicked.connect(lambda _=False, m=mode: self._set_linux_updates_mode(m))
            os_card_l.addWidget(btn)

        root.addWidget(os_card)
        root.addStretch(1)

        self._refresh_labels()

    def _apply_sidebar_refresh(self) -> None:
        window = self.window()
        sidebar = getattr(window, "sidebar", None)
        if sidebar is not None and hasattr(sidebar, "_check_updates"):
            sidebar._check_updates()

    def _refresh_labels(self) -> None:
        sidebar_mode = get_sidebar_update_mode()
        sidebar_mapping = {
            "real": "Sidebar footer mode: real GitHub release state",
            "available": "Sidebar footer mode: forced update available preview",
            "current": "Sidebar footer mode: forced up-to-date preview",
            "error": "Sidebar footer mode: forced check-failed preview",
        }
        self.sidebar_status.setText(sidebar_mapping.get(sidebar_mode, "Sidebar footer mode: real GitHub release state"))

        linux_mode = get_linux_updates_mode()
        linux_mapping = {
            "real": "Linux updates mode: real system package state",
            "clean": "Linux updates mode: clean system with no pending updates",
            "updates": "Linux updates mode: normal pending updates available",
            "security": "Linux updates mode: security updates available",
            "kept": "Linux updates mode: kept back packages",
            "held": "Linux updates mode: held packages",
            "reboot": "Linux updates mode: reboot required state",
            "mixed": "Linux updates mode: mixed warning state",
            "error": "Linux updates mode: simulated check failure",
        }
        self.os_status.setText(linux_mapping.get(linux_mode, "Linux updates mode: real system package state"))

    def _set_sidebar_mode(self, mode: str) -> None:
        set_sidebar_update_mode(mode)
        self._apply_sidebar_refresh()
        self._refresh_labels()

    def _set_linux_updates_mode(self, mode: str) -> None:
        set_linux_updates_mode(mode)
        window = self.window()
        pages = getattr(window, "pages", {}) or {}
        updates_page = pages.get("updates")
        if updates_page is not None and hasattr(updates_page, "refresh"):
            updates_page.refresh()
        self._refresh_labels()

    def _reset_all_flags(self) -> None:
        reset_flags()
        self._apply_sidebar_refresh()
        self._refresh_labels()
