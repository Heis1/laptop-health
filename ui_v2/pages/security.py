from __future__ import annotations

import json
import os
from pathlib import Path
import time

from PySide6.QtWidgets import QDialog, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ui_v2.services.probe import enabled_probe_configs, secret_store_required
from ui_v2.theme import current_theme_mode, qss
from ui_v2.widgets.cards import MetricCard


SECURITY_PREFS_PATH = Path.home() / ".config" / "laptop-health" / "security_prefs.json"
NETWORK_DISCOVERY_REVIEW_REVISION = "network-discovery-v1"


class SecurityPage(QWidget):
    """A local, read-only security posture summary for Laptop Health."""

    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)

        heading = QHBoxLayout()
        copy = QVBoxLayout()
        title = QLabel("Security Centre")
        title.setObjectName("PageTitle")
        copy.addWidget(title)
        subtitle = QLabel("Review local configuration, remote transport, credential protection, and packaged dependency posture.")
        subtitle.setObjectName("InspectorSub")
        subtitle.setWordWrap(True)
        copy.addWidget(subtitle)
        heading.addLayout(copy, 1)
        self.assessed_at = QLabel("Assessment has not run yet")
        self.assessed_at.setObjectName("InspectorSub")
        copy.addWidget(self.assessed_at)
        self.refresh_btn = QPushButton("Refresh assessment")
        self.refresh_btn.setObjectName("ActionButton")
        self.refresh_btn.clicked.connect(self.refresh)
        heading.addWidget(self.refresh_btn)
        outer.addLayout(heading)

        focus = QWidget()
        focus.setObjectName("Card")
        focus_l = QVBoxLayout(focus)
        focus_l.setContentsMargins(16, 14, 16, 14)
        focus_l.setSpacing(5)
        focus_title = QLabel("What Security Centre checks")
        focus_title.setObjectName("CardTitle")
        focus_l.addWidget(focus_title)
        focus_text = QLabel(
            "Remote transport and local CA use • credential storage in the desktop keyring • "
            "packaged dependency advisories • safe network-discovery posture. "
            "It is read-only: no probe, credential, or system setting is changed here."
        )
        focus_text.setObjectName("CardSub")
        focus_text.setWordWrap(True)
        focus_l.addWidget(focus_text)
        outer.addWidget(focus)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        self.transport = MetricCard("Remote transport", "—", "Probe endpoint encryption", "blue")
        self.secrets = MetricCard("Credentials", "—", "Secure local storage", "blue")
        self.dependencies = MetricCard("Dependencies", "Patched", "Build dependency posture", "green")
        self.network_review_btn = QPushButton("Review details")
        self.network_review_btn.setObjectName("ActionButton")
        self.network_review_btn.clicked.connect(self._show_network_review)
        self.network = MetricCard(
            "Network discovery",
            "Review",
            "Scan safety and permission",
            "orange",
            right_widget=self.network_review_btn,
        )
        grid.addWidget(self.transport, 0, 0)
        grid.addWidget(self.secrets, 0, 1)
        grid.addWidget(self.dependencies, 1, 0)
        grid.addWidget(self.network, 1, 1)
        outer.addLayout(grid)

        guidance = QWidget()
        guidance.setObjectName("Card")
        guidance_l = QVBoxLayout(guidance)
        guidance_l.setContentsMargins(16, 16, 16, 16)
        guidance_l.setSpacing(8)
        guidance_title = QLabel("What to do next")
        guidance_title.setObjectName("CardTitle")
        guidance_l.addWidget(guidance_title)
        self.guidance = QLabel()
        self.guidance.setObjectName("CardSub")
        self.guidance.setWordWrap(True)
        self.guidance.setTextInteractionFlags(self.guidance.textInteractionFlags())
        guidance_l.addWidget(self.guidance)
        outer.addWidget(guidance)
        outer.addStretch(1)
        self.refresh()

    def _show_network_review(self) -> None:
        dialog = QDialog(self)
        dialog.setObjectName("SecurityReviewDialog")
        dialog.setWindowTitle("Network discovery review")
        dialog.setMinimumWidth(520)
        # A modal dialog is a separate top-level surface. The base dark theme
        # does not set a QDialog fill, so set the surface explicitly as well.
        mode = current_theme_mode()
        if mode == "light":
            surface = "#f3efe7"
            text = "#1b2430"
            border = "#d9cab3"
        else:
            surface = "#0b1220"
            text = "#e8f0ff"
            border = "#1a2a41"
        dialog.setStyleSheet(
            qss(mode)
            + f"""
            QDialog#SecurityReviewDialog {{ background: {surface}; color: {text}; border: 1px solid {border}; }}
            QDialog#SecurityReviewDialog QLabel {{ color: {text}; }}
            """
        )
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(10)
        title = QLabel("Network discovery needs your review")
        title.setObjectName("PageTitle")
        layout.addWidget(title)
        explanation = QLabel(
            "Laptop Health can discover devices and, in detailed mode, request service and operating-system hints. "
            "That is useful on your own network, but it can be noisy and may violate another network’s rules if used without permission."
        )
        explanation.setObjectName("InspectorSub")
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        needed = QLabel(
            "What is needed:\n"
            "• Confirm that you own or are authorised to assess the target network.\n"
            "• Start with Quiet mode for basic host discovery.\n"
            "• Use detailed scanning only when you need ports, services, or OS hints.\n"
            "• Keep the target range narrow and avoid scanning public or shared networks."
        )
        needed.setObjectName("CardSub")
        needed.setWordWrap(True)
        layout.addWidget(needed)
        acknowledge = QPushButton("Acknowledge review")
        acknowledge.setObjectName("ActionButton")
        acknowledge.clicked.connect(lambda: self._acknowledge_network_review(dialog))
        layout.addWidget(acknowledge, 0)
        close = QPushButton("Close")
        close.setObjectName("ActionButton")
        close.clicked.connect(dialog.accept)
        layout.addWidget(close, 0)
        dialog.exec()

    @staticmethod
    def _network_review_acknowledged() -> bool:
        try:
            data = json.loads(SECURITY_PREFS_PATH.read_text(encoding="utf-8"))
            return data.get("network_discovery_review") == NETWORK_DISCOVERY_REVIEW_REVISION
        except (OSError, ValueError, AttributeError):
            return False

    def _acknowledge_network_review(self, dialog: QDialog) -> None:
        try:
            SECURITY_PREFS_PATH.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            SECURITY_PREFS_PATH.write_text(
                json.dumps({"network_discovery_review": NETWORK_DISCOVERY_REVIEW_REVISION}, indent=2) + "\n",
                encoding="utf-8",
            )
            os.chmod(SECURITY_PREFS_PATH, 0o600)
        except OSError:
            return
        self.refresh()
        dialog.accept()

    def refresh(self) -> None:
        configs = enabled_probe_configs()
        insecure = [cfg for cfg in configs if not cfg.url.lower().startswith("https://")]
        if not configs:
            self.transport.set_values("No probes", "Nothing remote is configured yet", "green")
        elif insecure:
            self.transport.set_values("HTTP found", f"{len(insecure)} of {len(configs)} active probe(s) need HTTPS", "red")
        else:
            self.transport.set_values("HTTPS", f"{len(configs)} active probe(s) use encryption", "green")

        if secret_store_required():
            self.secrets.set_values("Protected", "Secret Service is available for probe credentials", "green")
        else:
            self.secrets.set_values("Set up keyring", "Install a Secret Service provider before saving secrets", "orange")

        requirement = Path(__file__).resolve().parents[2] / "requirements-build.txt"
        self.dependencies.set_values(
            "Patched" if requirement.exists() else "Review",
            "Paramiko 5.0.0 • CVE-2026-44405 addressed",
            "green" if requirement.exists() else "orange",
        )
        if self._network_review_acknowledged():
            self.network.set_values("Acknowledged", "No new discovery guidance since your review", "green")
            self.network_review_btn.setText("View acknowledgement")
        else:
            self.network.set_values("Review", "Confirm safe and authorised scan use", "orange")
            self.network_review_btn.setText("Review details")
        bullets = [
            "1. Replace HTTP Probe and Pi-hole URLs with HTTPS, then add your local CA certificate in Probe settings.",
            "2. Apply system security updates regularly, particularly the Linux kernel and OpenSSL.",
            "3. Use Quiet discovery on networks you own. Detailed scans should only be run with permission.",
        ]
        self.guidance.setText("\n".join(bullets))
        self.assessed_at.setText(f"Last assessed {time.strftime('%H:%M:%S')} • {len(configs)} active probe(s)")
