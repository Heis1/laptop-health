from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from ui_v2.services.probe import ProbeConfig, secret_store_required


def _pihole_host_from_url(url: str) -> str:
    value = (url or "").strip()
    if not value:
        return ""
    for prefix in ("http://", "https://"):
        if value.startswith(prefix):
            value = value[len(prefix):]
            break
    value = value.split("/", 1)[0]
    return value


def _pihole_url_from_host(host: str) -> str:
    value = (host or "").strip().rstrip("/")
    if not value:
        return ""
    if value.startswith(("http://", "https://")):
        base = value.rstrip("/")
    else:
        base = f"http://{value}"
    if base.endswith("/admin"):
        return f"{base}/api.php"
    if "/admin/api.php" in base:
        return base
    return f"{base}/admin/api.php"


class ProbeSettingsDialog(QDialog):
    def __init__(self, config: ProbeConfig, parent=None):
        super().__init__(parent)
        self._probe_id = config.id
        self._existing_token = config.token
        self._existing_pihole_password = config.pihole_password
        self.setWindowTitle("Probe Settings")
        self.setModal(True)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        host = parent.window() if parent is not None else None
        if host is not None:
            self.setGeometry(host.geometry())
        else:
            self.resize(760, 560)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scrim = QFrame()
        scrim.setObjectName("ProbeScrim")
        scrim_lay = QVBoxLayout(scrim)
        scrim_lay.setContentsMargins(0, 0, 0, 0)
        scrim_lay.setSpacing(0)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addStretch(1)

        card = QFrame()
        card.setObjectName("ProbeCard")
        card.setFixedWidth(620)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(12)

        hdr = QHBoxLayout()
        title = QLabel("Probe Settings")
        title.setObjectName("ProbeTitle")
        hdr.addWidget(title)
        hdr.addStretch(1)

        btn_x = QPushButton("✕")
        btn_x.setObjectName("ProbeX")
        btn_x.setCursor(Qt.PointingHandCursor)
        btn_x.clicked.connect(self.reject)
        hdr.addWidget(btn_x)
        lay.addLayout(hdr)

        subtitle = QLabel("Configure the remote Raspberry Pi probe connection for the dashboard and remote page.")
        subtitle.setObjectName("ProbeSubtitle")
        subtitle.setWordWrap(True)
        lay.addWidget(subtitle)

        if not secret_store_required():
            warning = QLabel("Desktop secret storage is required. Install `secret-tool` / libsecret support before saving probe or Pi-hole credentials.")
            warning.setObjectName("ProbeSubtitle")
            warning.setWordWrap(True)
            lay.addWidget(warning)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.enabled = QCheckBox("Enable Raspberry Pi probe")
        self.enabled.setChecked(config.enabled)
        form.addRow("", self.enabled)

        self.name = QLineEdit(config.name)
        self.name.setPlaceholderText("Raspberry Pi")
        form.addRow("Device name", self.name)

        self.url = QLineEdit(config.url)
        self.url.setPlaceholderText("https://192.0.2.51:9821/metrics")
        form.addRow("Probe URL", self.url)

        self.token = QLineEdit("")
        self.token.setEchoMode(QLineEdit.Password)
        self.token.setPlaceholderText("Stored in the desktop secret store. Enable replacement to enter a new token.")
        self.token.setEnabled(False)
        form.addRow("Bearer token", self.token)

        self.replace_token = QCheckBox("Replace stored token")
        self.replace_token.toggled.connect(self._toggle_replace_token)
        form.addRow("", self.replace_token)

        self.show_token = QCheckBox("Show replacement token")
        self.show_token.setEnabled(False)
        self.show_token.toggled.connect(
            lambda checked: self.token.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)
        )
        form.addRow("", self.show_token)

        self.ca_cert_path = QLineEdit(config.ca_cert_path)
        self.ca_cert_path.setPlaceholderText("Optional local CA / self-signed cert path")
        form.addRow("CA certificate", self.ca_cert_path)

        self.pihole_enabled = QCheckBox("Enable Pi-hole stats")
        self.pihole_enabled.setChecked(config.pihole_enabled)
        form.addRow("", self.pihole_enabled)

        self.pihole_host = QLineEdit(_pihole_host_from_url(config.pihole_url))
        self.pihole_host.setPlaceholderText("192.0.2.51")
        form.addRow("Pi-hole host or IP", self.pihole_host)

        self.pihole_example = QLabel("Example: 192.0.2.51 → http://192.0.2.51/admin/api.php")
        self.pihole_example.setObjectName("ProbeSubtitle")
        self.pihole_example.setWordWrap(True)
        form.addRow("", self.pihole_example)

        self.pihole_password = QLineEdit("")
        self.pihole_password.setEchoMode(QLineEdit.Password)
        self.pihole_password.setPlaceholderText("Stored in the desktop secret store. Enable replacement to enter a new Pi-hole password.")
        self.pihole_password.setEnabled(False)
        form.addRow("Pi-hole password", self.pihole_password)

        self.replace_pihole_password = QCheckBox("Replace Pi-hole password")
        self.replace_pihole_password.toggled.connect(self._toggle_replace_pihole_password)
        form.addRow("", self.replace_pihole_password)

        self.show_pihole_password = QCheckBox("Show replacement Pi-hole password")
        self.show_pihole_password.setEnabled(False)
        self.show_pihole_password.toggled.connect(
            lambda checked: self.pihole_password.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)
        )
        form.addRow("", self.show_pihole_password)

        lay.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.Save).setObjectName("ActionBtn")
        buttons.button(QDialogButtonBox.Cancel).setObjectName("ActionBtn")
        lay.addWidget(buttons)

        row.addWidget(card)
        row.addStretch(1)
        scrim_lay.addStretch(1)
        scrim_lay.addLayout(row)
        scrim_lay.addStretch(1)
        root.addWidget(scrim)

        def _scrim_click(event) -> None:
            if not card.geometry().contains(event.position().toPoint()):
                self.reject()
                return
            event.accept()

        scrim.mousePressEvent = _scrim_click

        self.setStyleSheet(
            """
            QFrame#ProbeScrim {
                background: rgba(0, 0, 0, 0.55);
            }
            QFrame#ProbeCard {
                background: rgba(10, 14, 22, 0.92);
                border: 1px solid rgba(255,255,255,0.14);
                border-left: 6px solid rgba(96,165,250,0.95);
                border-radius: 16px;
            }
            QLabel#ProbeTitle {
                color: rgba(255,255,255,0.96);
                font-weight: 700;
                font-size: 18px;
            }
            QLabel#ProbeSubtitle {
                color: rgba(255,255,255,0.78);
                font-size: 12px;
            }
            QLabel, QCheckBox {
                color: rgba(248,251,255,0.96);
                font-size: 12px;
            }
            QLineEdit {
                color: rgba(248,251,255,0.96);
                background: rgba(255,255,255,0.08);
                border: 1px solid rgba(255,255,255,0.14);
                border-radius: 10px;
                padding: 7px 12px;
                font-size: 12px;
                font-weight: 600;
                selection-background-color: rgba(96,165,250,0.32);
            }
            QLineEdit:focus {
                border: 1px solid rgba(96,165,250,0.75);
                background: rgba(255,255,255,0.12);
            }
            QLineEdit:disabled {
                color: rgba(232,240,255,0.50);
                background: rgba(255,255,255,0.04);
                border: 1px solid rgba(255,255,255,0.08);
            }
            QPushButton#ProbeX {
                color: rgba(255,255,255,0.75);
                background: transparent;
                border: 0px;
                padding: 4px 8px;
                border-radius: 10px;
                font-size: 14px;
            }
            QPushButton#ProbeX:hover {
                background: rgba(255,255,255,0.10);
                color: rgba(255,255,255,0.92);
            }
            QPushButton#ActionBtn {
                color: rgba(255,255,255,0.92);
                background: rgba(255,255,255,0.08);
                border: 1px solid rgba(255,255,255,0.14);
                padding: 7px 12px;
                border-radius: 10px;
                min-width: 110px;
            }
            QPushButton#ActionBtn:hover {
                background: rgba(255,255,255,0.12);
                border: 1px solid rgba(255,255,255,0.18);
            }
            QPushButton#ActionBtn:pressed {
                background: rgba(255,255,255,0.06);
            }
            """
        )

    def _toggle_replace_token(self, checked: bool) -> None:
        self.token.setEnabled(checked)
        self.show_token.setEnabled(checked)
        if not checked:
            self.token.clear()
            self.show_token.setChecked(False)

    def _toggle_replace_pihole_password(self, checked: bool) -> None:
        self.pihole_password.setEnabled(checked)
        self.show_pihole_password.setEnabled(checked)
        if not checked:
            self.pihole_password.clear()
            self.show_pihole_password.setChecked(False)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)

    def config(self) -> ProbeConfig:
        return ProbeConfig(
            id=self._probe_id,
            enabled=self.enabled.isChecked(),
            name=(self.name.text().strip() or "Raspberry Pi"),
            url=self.url.text().strip(),
            token=self.token.text().strip() if self.replace_token.isChecked() else self._existing_token,
            ca_cert_path=self.ca_cert_path.text().strip(),
            pihole_enabled=self.pihole_enabled.isChecked(),
            pihole_url=_pihole_url_from_host(self.pihole_host.text().strip()) if self.pihole_enabled.isChecked() else "",
            pihole_password=self.pihole_password.text().strip() if self.replace_pihole_password.isChecked() else self._existing_pihole_password,
        )
