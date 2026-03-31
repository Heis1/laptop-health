from __future__ import annotations

import copy
import os
import re
import shlex
import uuid

from PySide6.QtCore import QThread, Qt, Signal, QTimer
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui_v2.services.probe import ProbeConfig, new_probe_config, upsert_probe_config
from ui_v2.widgets.prompt_dialog import PromptDialog


class _DeployThread(QThread):
    output = Signal(str)
    done = Signal(int)

    def __init__(self, *, host: str, user: str, tls_mode: str, tls_cn: str, token: str, ssh_password: str, sudo_password: str):
        super().__init__()
        self.host = host
        self.user = user
        self.tls_mode = tls_mode
        self.tls_cn = tls_cn
        self.token = token
        self.ssh_password = ssh_password
        self.sudo_password = sudo_password or ssh_password

    def run(self) -> None:
        try:
            import paramiko
        except Exception as exc:
            self.output.emit(f"Install failed: Paramiko is unavailable: {exc}\n")
            self.done.emit(1)
            return

        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        local_probe_py = os.path.join(repo_root, "probe", "pi_probe.py")
        local_service = os.path.join(repo_root, "probe", "pi-probe.service")
        local_cert_out = os.path.join(repo_root, "probe", "probe.crt")

        install_dir = "/opt/pi-probe"
        remote_cert_dir = f"{install_dir}/certs"
        remote_cert_path = f"{remote_cert_dir}/probe.crt"
        remote_key_path = f"{remote_cert_dir}/probe.key"
        env_file_path = "/etc/pi-probe.env"
        token_file_path = "/etc/pi-probe.token"
        service_name = "pi-probe"

        client = paramiko.SSHClient()
        client.load_system_host_keys()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            self.output.emit(f"Installing probe on {self.user}@{self.host}\n")
            client.connect(
                hostname=self.host,
                username=self.user,
                password=self.ssh_password,
                look_for_keys=False,
                allow_agent=False,
                timeout=15,
            )

            self._run_remote(client, f"mkdir -p {shlex.quote(install_dir)} {shlex.quote(remote_cert_dir)} /etc/systemd/system/{service_name}.service.d", sudo=True)

            self.output.emit("Uploading probe files\n")
            sftp = client.open_sftp()
            try:
                sftp.put(local_probe_py, "/tmp/pi_probe.py")
                sftp.put(local_service, "/tmp/pi-probe.service")
            finally:
                sftp.close()

            self._run_remote(
                client,
                f"cp /tmp/pi_probe.py {shlex.quote(install_dir)}/pi_probe.py && cp /tmp/pi-probe.service /etc/systemd/system/{service_name}.service",
                sudo=True,
            )

            if self.tls_mode == "self-signed":
                self.output.emit("Generating self-signed certificate on the Pi\n")
                tls_san = f"IP:{self.tls_cn}" if re.match(r'^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$', self.tls_cn) else f"DNS:{self.tls_cn}"
                self._run_remote(
                    client,
                    " && ".join(
                        [
                            f"openssl req -x509 -newkey rsa:4096 -keyout {shlex.quote(remote_key_path)} -out {shlex.quote(remote_cert_path)} -sha256 -days 365 -nodes -subj {shlex.quote('/CN=' + self.tls_cn)} -addext {shlex.quote('subjectAltName=' + tls_san)} >/dev/null 2>&1",
                            f"chown {shlex.quote(self.user)}:{shlex.quote(self.user)} {shlex.quote(remote_cert_path)} {shlex.quote(remote_key_path)}",
                            f"chmod 644 {shlex.quote(remote_cert_path)}",
                            f"chmod 600 {shlex.quote(remote_key_path)}",
                        ]
                    ),
                    sudo=True,
                )
                sftp = client.open_sftp()
                try:
                    sftp.get(remote_cert_path, local_cert_out)
                finally:
                    sftp.close()
                self.output.emit(f"Copied certificate to {local_cert_out}\n")

            self.output.emit("Writing probe token on the Pi\n")
            token_content = f"{self.token}\n"
            env_lines = [f"PI_PROBE_PORT=9821"]
            if self.tls_mode == "self-signed":
                env_lines.append(f"PI_PROBE_TLS_CERT={remote_cert_path}")
                env_lines.append(f"PI_PROBE_TLS_KEY={remote_key_path}")
            self._write_remote_file(client, token_file_path, token_content, owner=f"{self.user}:{self.user}", mode="600")

            self.output.emit("Writing probe runtime configuration on the Pi\n")
            self._write_remote_file(client, env_file_path, "\n".join(env_lines) + "\n", owner="root:root", mode="600")
            override = (
                "[Service]\n"
                f"User={self.user}\n"
                f"EnvironmentFile={env_file_path}\n"
                f"Environment=PI_PROBE_TOKEN_FILE={token_file_path}\n"
            )
            self.output.emit("Writing systemd override on the Pi\n")
            self._write_remote_file(client, f"/etc/systemd/system/{service_name}.service.d/override.conf", override, owner="root:root", mode="644")

            self.output.emit("Starting probe service\n")
            self._run_remote(client, f"systemctl daemon-reload && systemctl enable --now {service_name} && systemctl restart {service_name}", sudo=True)

            if self.tls_mode == "off":
                verify = f"curl -fsS -H {shlex.quote('Authorization: Bearer ' + self.token)} http://localhost:9821/metrics >/dev/null 2>/dev/null"
                dashboard_url = f"http://{self.host}:9821/metrics"
            else:
                if re.match(r'^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$', self.tls_cn):
                    verify = f"curl -fsS --cacert {shlex.quote(remote_cert_path)} -H {shlex.quote('Authorization: Bearer ' + self.token)} https://{self.tls_cn}:9821/metrics >/dev/null 2>/dev/null"
                else:
                    verify = f"curl -fsS --cacert {shlex.quote(remote_cert_path)} --resolve {shlex.quote(f'{self.tls_cn}:9821:127.0.0.1')} -H {shlex.quote('Authorization: Bearer ' + self.token)} https://{self.tls_cn}:9821/metrics >/dev/null 2>/dev/null"
                dashboard_url = f"https://{self.tls_cn}:9821/metrics"

            self.output.emit("Verifying probe\n")
            rc, _, _ = self._run_remote(
                client,
                f"for attempt in 1 2 3 4 5 6 7 8 9 10; do {verify} && exit 0; sleep 1; done; exit 1",
                check=False,
            )
            if rc != 0:
                self.output.emit("\nProbe verification failed. Recent service status:\n")
                _, out, err = self._run_remote(client, f"systemctl --no-pager --full status {service_name} | sed -n '1,20p'", sudo=True, check=False)
                self.output.emit(out + err)
                self.output.emit("\nRecent probe logs:\n")
                _, out, err = self._run_remote(client, f"journalctl -u {service_name} --no-pager -n 20", sudo=True, check=False)
                self.output.emit(out + err)
                self.done.emit(1)
                return

            self.output.emit("\nDeployment complete\n")
            self.output.emit(f"Dashboard URL: {dashboard_url}\n")
            if self.tls_mode == "self-signed":
                self.output.emit(f"Laptop CA cert path: {local_cert_out}\n")
            _, out, err = self._run_remote(client, f"systemctl --no-pager --full status {service_name} | sed -n '1,12p'", check=False)
            self.output.emit("Systemd status:\n")
            self.output.emit(out + err)
            self.done.emit(0)
        except Exception as exc:
            self.output.emit(f"\nInstall failed: {exc}\n")
            self.done.emit(1)
        finally:
            client.close()

    def _run_remote(self, client, command: str, *, sudo: bool = False, check: bool = True) -> tuple[int, str, str]:
        if sudo:
            command = f"sudo -S -p '' bash -lc {shlex.quote(command)}"
        stdin, stdout, stderr = client.exec_command(command, get_pty=sudo)
        if sudo:
            stdin.write(self.sudo_password + "\n")
            stdin.flush()
        stdin.channel.shutdown_write()
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        rc = stdout.channel.recv_exit_status()
        if check and rc != 0:
            msg = (out + err).strip() or f"Remote command failed with exit code {rc}"
            raise RuntimeError(msg)
        return rc, out, err

    def _write_remote_file(self, client, path: str, content: str, *, owner: str, mode: str) -> None:
        temp_path = f"/tmp/laptop-health-{uuid.uuid4().hex}"
        escaped_path = shlex.quote(path)
        escaped_temp = shlex.quote(temp_path)

        self.output.emit(f"  Uploading temporary file for {path}\n")
        sftp = client.open_sftp()
        try:
            with sftp.file(temp_path, "w") as handle:
                handle.write(content)
        finally:
            sftp.close()

        self.output.emit(f"  Installing {path}\n")
        self._run_remote(
            client,
            f"install -o {shlex.quote(owner.split(':', 1)[0])} -g {shlex.quote(owner.split(':', 1)[1])} -m {mode} {escaped_temp} {escaped_path}",
            sudo=True,
        )
        self.output.emit(f"  Cleaning up temporary file for {path}\n")
        self._run_remote(client, f"rm -f {escaped_temp}", check=False)


def _generate_token() -> str:
    import secrets

    return secrets.token_hex(32)


class ProbeDeployDialog(QDialog):
    def __init__(self, config: ProbeConfig, parent=None):
        super().__init__(parent)
        self._config = copy.deepcopy(config)
        self._thread: _DeployThread | None = None
        self._saved_token = ""
        self._saved_url = ""
        self._saved_cert = ""
        self._auto_close_pending = False

        self.setModal(True)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        host = parent.window() if parent is not None else None
        if host is not None:
            self.setGeometry(host.geometry())
        else:
            self.resize(980, 720)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scrim = QFrame()
        scrim.setObjectName("DeployScrim")
        scrim_lay = QVBoxLayout(scrim)
        scrim_lay.setContentsMargins(0, 0, 0, 0)
        scrim_lay.setSpacing(0)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addStretch(1)

        card = QFrame()
        card.setObjectName("DeployCard")
        card.setFixedWidth(760)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(12)

        hdr = QHBoxLayout()
        title = QLabel("Install / Reinstall Probe")
        title.setObjectName("DeployTitle")
        hdr.addWidget(title)
        hdr.addStretch(1)
        close_btn = QPushButton("✕")
        close_btn.setObjectName("DeployX")
        close_btn.clicked.connect(self.reject)
        hdr.addWidget(close_btn)
        lay.addLayout(hdr)

        subtitle = QLabel("Run the probe deployment inside the app. Passwords are used only for this session.")
        subtitle.setObjectName("DeploySubtitle")
        subtitle.setWordWrap(True)
        lay.addWidget(subtitle)

        intro = QFrame()
        intro.setObjectName("DeployHintCard")
        intro_l = QVBoxLayout(intro)
        intro_l.setContentsMargins(12, 10, 12, 10)
        intro_l.setSpacing(4)
        intro_title = QLabel("Before you start")
        intro_title.setObjectName("DeployHintTitle")
        intro_l.addWidget(intro_title)
        intro_body = QLabel(
            "Use the Pi's IP or hostname, choose a friendly probe name for the dashboard card, "
            "and use self-signed TLS unless you intentionally want plain HTTP on your LAN."
        )
        intro_body.setObjectName("DeployHintBody")
        intro_body.setWordWrap(True)
        intro_l.addWidget(intro_body)
        lay.addWidget(intro)

        self.status_card = QFrame()
        self.status_card.setObjectName("DeployStatusCard")
        status_l = QVBoxLayout(self.status_card)
        status_l.setContentsMargins(12, 10, 12, 10)
        status_l.setSpacing(4)
        self.status_badge = QLabel("Ready")
        self.status_badge.setObjectName("DeployStatusBadge")
        status_l.addWidget(self.status_badge)
        self.status_text = QLabel("Fill in the probe details, then start the install.")
        self.status_text.setObjectName("DeployStatusText")
        self.status_text.setWordWrap(True)
        status_l.addWidget(self.status_text)
        lay.addWidget(self.status_card)

        form = QFormLayout()
        form.setSpacing(10)

        self.host_input = QLineEdit(_extract_host(config.url) or "")
        self.host_input.setPlaceholderText("192.0.2.51 or raspberrypi.local")
        form.addRow(self._label_row("Pi hostname or IP", self._help_host), self.host_input)

        self.name_input = QLineEdit(config.name or "Raspberry Pi")
        self.name_input.setPlaceholderText("Kitchen Pi, Office Pi, Bench Pi")
        form.addRow(self._label_row("Probe name", self._help_name), self.name_input)

        import getpass
        self.user_input = QLineEdit(getpass.getuser())
        self.user_input.setPlaceholderText("Usually pi, aron, or your own SSH username")
        form.addRow(self._label_row("Pi SSH user", self._help_user), self.user_input)

        self.tls_self_signed = QCheckBox("Use self-signed TLS")
        self.tls_self_signed.setChecked(True)
        self.tls_self_signed.toggled.connect(self._toggle_tls)
        form.addRow(self._label_row("TLS mode", self._help_tls), self.tls_self_signed)

        self.tls_host_input = QLineEdit(_extract_host(config.url) or "")
        self.tls_host_input.setPlaceholderText("Must match what this laptop will connect to")
        form.addRow(self._label_row("Hostname or IP for HTTPS", self._help_tls_host), self.tls_host_input)

        self.generate_token = QCheckBox("Generate a new token")
        self.generate_token.setChecked(True)
        self.generate_token.toggled.connect(self._toggle_generate_token)
        form.addRow(self._label_row("Token setup", self._help_token), self.generate_token)

        self.token_input = QLineEdit("")
        self.token_input.setEchoMode(QLineEdit.Password)
        self.token_input.setEnabled(False)
        self.token_input.setPlaceholderText("Generated automatically for install")
        form.addRow(self._label_row("Probe token", self._help_token), self.token_input)

        self.show_token = QCheckBox("Show token")
        self.show_token.setEnabled(False)
        self.show_token.toggled.connect(
            lambda checked: self.token_input.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)
        )
        form.addRow("", self.show_token)

        self.ssh_password_input = QLineEdit("")
        self.ssh_password_input.setEchoMode(QLineEdit.Password)
        self.ssh_password_input.setPlaceholderText("Password for SSH login to the Pi")
        form.addRow(self._label_row("SSH password", self._help_ssh_password), self.ssh_password_input)

        self.show_ssh_password = QCheckBox("Show SSH password")
        self.show_ssh_password.toggled.connect(
            lambda checked: self.ssh_password_input.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)
        )
        form.addRow("", self.show_ssh_password)

        self.sudo_password_input = QLineEdit("")
        self.sudo_password_input.setEchoMode(QLineEdit.Password)
        self.sudo_password_input.setPlaceholderText("Leave blank to reuse SSH password")
        form.addRow(self._label_row("sudo password", self._help_sudo_password), self.sudo_password_input)

        self.show_sudo_password = QCheckBox("Show sudo password")
        self.show_sudo_password.toggled.connect(
            lambda checked: self.sudo_password_input.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)
        )
        form.addRow("", self.show_sudo_password)

        lay.addLayout(form)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setObjectName("DeployLog")
        lay.addWidget(self.log, 1)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("ActionBtn")
        self.cancel_btn.clicked.connect(self.reject)
        actions.addWidget(self.cancel_btn)
        self.start_btn = QPushButton("Start Install")
        self.start_btn.setObjectName("ActionBtn")
        self.start_btn.clicked.connect(self._start)
        actions.addWidget(self.start_btn)
        lay.addLayout(actions)

        row.addWidget(card)
        row.addStretch(1)
        scrim_lay.addStretch(1)
        scrim_lay.addLayout(row)
        scrim_lay.addStretch(1)
        root.addWidget(scrim)

        self.setStyleSheet(
            """
            QFrame#DeployScrim {
                background: rgba(0, 0, 0, 0.55);
            }
            QFrame#DeployCard {
                background: rgba(10, 14, 22, 0.92);
                border: 1px solid rgba(255,255,255,0.14);
                border-left: 6px solid rgba(96,165,250,0.95);
                border-radius: 16px;
            }
            QFrame#DeployHintCard {
                background: rgba(255,255,255,0.05);
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 12px;
            }
            QFrame#DeployStatusCard {
                background: rgba(96,165,250,0.10);
                border: 1px solid rgba(96,165,250,0.20);
                border-radius: 12px;
            }
            QLabel#DeployTitle {
                color: rgba(255,255,255,0.96);
                font-weight: 700;
                font-size: 18px;
            }
            QLabel#DeployHintTitle {
                color: rgba(255,255,255,0.96);
                font-weight: 700;
                font-size: 12px;
            }
            QLabel#DeployHintBody {
                color: rgba(248,251,255,0.76);
                font-size: 12px;
            }
            QLabel#DeployStatusBadge {
                color: rgba(230,242,255,0.98);
                background: rgba(96,165,250,0.22);
                border: 1px solid rgba(96,165,250,0.34);
                border-radius: 999px;
                padding: 3px 10px;
                font-size: 11px;
                font-weight: 700;
                max-width: 120px;
            }
            QLabel#DeployStatusText {
                color: rgba(248,251,255,0.84);
                font-size: 12px;
            }
            QLabel#DeploySubtitle, QLabel, QCheckBox {
                color: rgba(248,251,255,0.92);
                font-size: 12px;
            }
            QPushButton#DeployHelpBtn {
                color: rgba(191,219,254,0.92);
                background: rgba(96,165,250,0.12);
                border: 1px solid rgba(96,165,250,0.28);
                padding: 1px 8px;
                border-radius: 999px;
                min-width: 0px;
                font-size: 11px;
                font-weight: 700;
            }
            QPushButton#DeployHelpBtn:hover {
                background: rgba(96,165,250,0.20);
                border: 1px solid rgba(96,165,250,0.40);
            }
            QLineEdit {
                color: rgba(248,251,255,0.96);
                background: rgba(255,255,255,0.08);
                border: 1px solid rgba(255,255,255,0.14);
                border-radius: 10px;
                padding: 7px 12px;
                font-size: 12px;
                font-weight: 600;
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
            QTextEdit#DeployLog {
                background: rgba(10, 14, 22, 0.52);
                color: rgba(255,255,255,0.88);
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 12px;
                padding: 10px;
                font-family: monospace;
                font-size: 12px;
            }
            QPushButton#DeployX {
                color: rgba(255,255,255,0.75);
                background: transparent;
                border: 0px;
                padding: 4px 8px;
                border-radius: 10px;
                font-size: 14px;
            }
            QPushButton#DeployX:hover {
                background: rgba(255,255,255,0.10);
                color: rgba(255,255,255,0.92);
            }
            QPushButton#ActionBtn {
                color: rgba(255,255,255,0.92);
                background: rgba(255,255,255,0.08);
                border: 1px solid rgba(255,255,255,0.14);
                padding: 7px 12px;
                border-radius: 10px;
                min-width: 120px;
            }
            QPushButton#ActionBtn:hover {
                background: rgba(255,255,255,0.12);
                border: 1px solid rgba(255,255,255,0.18);
            }
            """
        )

        self._toggle_generate_token(True)
        self._set_status("Ready", "Fill in the probe details, then start the install.", "blue")

    def _label_row(self, text: str, handler) -> QWidget:
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        lbl = QLabel(text)
        row.addWidget(lbl)
        btn = QPushButton("?")
        btn.setObjectName("DeployHelpBtn")
        btn.clicked.connect(handler)
        row.addWidget(btn)
        row.addStretch(1)
        return box

    def _toggle_tls(self, checked: bool) -> None:
        self.tls_host_input.setEnabled(checked)

    def _toggle_generate_token(self, checked: bool) -> None:
        self.token_input.setEnabled(not checked)
        self.show_token.setEnabled(not checked)
        if checked:
            self.token_input.clear()
            self.show_token.setChecked(False)

    def _append(self, text: str) -> None:
        self.log.moveCursor(QTextCursor.End)
        self.log.insertPlainText(text)
        self.log.moveCursor(QTextCursor.End)
        self._update_status_from_output(text)

    def _set_status(self, badge: str, text: str, accent: str) -> None:
        styles = {
            "blue": (
                "rgba(96,165,250,0.10)",
                "rgba(96,165,250,0.20)",
                "rgba(96,165,250,0.22)",
                "rgba(230,242,255,0.98)",
            ),
            "orange": (
                "rgba(251,146,60,0.12)",
                "rgba(251,146,60,0.22)",
                "rgba(251,146,60,0.20)",
                "rgba(255,241,224,0.98)",
            ),
            "green": (
                "rgba(52,211,153,0.12)",
                "rgba(52,211,153,0.24)",
                "rgba(52,211,153,0.18)",
                "rgba(220,255,238,0.98)",
            ),
            "red": (
                "rgba(248,113,113,0.12)",
                "rgba(248,113,113,0.24)",
                "rgba(248,113,113,0.18)",
                "rgba(255,234,234,0.98)",
            ),
        }
        bg, border, pill_bg, pill_fg = styles.get(accent, styles["blue"])
        self.status_card.setStyleSheet(
            f"background: {bg}; border: 1px solid {border}; border-radius: 12px;"
        )
        self.status_badge.setStyleSheet(
            f"color: {pill_fg}; background: {pill_bg}; border: 1px solid {border}; border-radius: 999px; padding: 3px 10px; font-size: 11px; font-weight: 700;"
        )
        self.status_badge.setText(badge)
        self.status_text.setText(text)

    def _update_status_from_output(self, text: str) -> None:
        lower = text.lower()
        if "starting deploy" in lower:
            self._set_status("Starting", "Opening the install session and preparing deployment.", "blue")
        elif "installing probe on" in lower:
            self._set_status("Connecting", "Connecting to the Pi and preparing remote directories.", "blue")
        elif "password:" in lower:
            self._set_status("Authenticating", "Waiting for SSH or sudo authentication to complete.", "orange")
        elif "generating self-signed certificate" in lower:
            self._set_status("TLS Setup", "Generating the HTTPS certificate on the Pi.", "blue")
        elif "uploading provided tls" in lower:
            self._set_status("TLS Setup", "Uploading the provided certificate and key.", "blue")
        elif "copied certificate to" in lower:
            self._set_status("Certificate Copied", "Copied the probe certificate back to this laptop.", "blue")
        elif "writing probe token on the pi" in lower:
            self._set_status("Saving Token", "Writing the probe token file on the Pi.", "blue")
        elif "writing probe runtime configuration on the pi" in lower:
            self._set_status("Saving Config", "Writing the probe runtime configuration file on the Pi.", "blue")
        elif "writing systemd override on the pi" in lower:
            self._set_status("Configuring Service", "Writing the systemd override for the probe service.", "blue")
        elif "created symlink" in lower or "started pi-probe.service" in lower:
            self._set_status("Service Starting", "The probe service is being enabled and started.", "blue")
        elif "dashboard url:" in lower:
            self._set_status("Verifying", "The probe is up. Final verification and local settings save are running.", "green")
        elif "probe verification failed" in lower or "install failed" in lower:
            self._set_status("Failed", "Install did not complete. Check the log output below.", "red")
        elif "saved probe settings locally for the app" in lower:
            self._set_status("Complete", "Probe installed successfully and app settings were saved.", "green")

    def _show_help(self, title: str, message: str) -> None:
        PromptDialog(self, title, message, accent="blue", ok_text="Close").exec()

    def _help_host(self) -> None:
        self._show_help(
            "Pi Hostname Or IP",
            "Enter the address this laptop uses to reach the Pi.\n\n"
            "Examples:\n"
            "192.0.2.51\n"
            "raspberrypi.local\n\n"
            "If you are unsure, use the Pi's LAN IP address.",
        )

    def _help_name(self) -> None:
        self._show_help(
            "Probe Name",
            "This is the custom label shown in Laptop Health.\n\n"
            "Examples:\n"
            "Kitchen Pi\n"
            "Office Pi\n"
            "Bench Pi\n\n"
            "It does not need to match the Pi hostname.",
        )

    def _help_user(self) -> None:
        self._show_help(
            "Pi SSH User",
            "This is the SSH login used to connect to the Pi.\n\n"
            "Examples:\n"
            "pi\n"
            "aron\n\n"
            "It must be a user that can run sudo on the Pi.",
        )

    def _help_tls(self) -> None:
        self._show_help(
            "TLS Mode",
            "Use self-signed TLS for the normal secure setup.\n\n"
            "Use plain HTTP only if you intentionally do not want encryption on your LAN.",
        )

    def _help_tls_host(self) -> None:
        self._show_help(
            "HTTPS Hostname Or IP",
            "This must match the exact host value this laptop will use in the probe URL.\n\n"
            "Examples:\n"
            "If the URL will be https://192.0.2.51:9821/metrics then enter 192.0.2.51\n"
            "If the URL will be https://raspberrypi.local:9821/metrics then enter raspberrypi.local",
        )

    def _help_token(self) -> None:
        self._show_help(
            "Probe Token",
            "The token is the shared secret between Laptop Health and the Pi probe.\n\n"
            "Recommended:\n"
            "Leave 'Generate a new token' enabled and let the app create one.\n\n"
            "Only enter your own token if you are reconnecting to an existing probe.",
        )

    def _help_ssh_password(self) -> None:
        self._show_help(
            "SSH Password",
            "This is the password used to log in to the Pi over SSH.\n\n"
            "The app uses it only for this install session.",
        )

    def _help_sudo_password(self) -> None:
        self._show_help(
            "sudo Password",
            "This is the password needed for privileged commands on the Pi.\n\n"
            "If your sudo password is the same as your SSH password, leave this blank.",
        )

    def _start(self) -> None:
        host = self.host_input.text().strip()
        user = self.user_input.text().strip()
        tls_mode = "self-signed" if self.tls_self_signed.isChecked() else "off"
        tls_cn = self.tls_host_input.text().strip() if self.tls_self_signed.isChecked() else host
        token = self.token_input.text().strip() if not self.generate_token.isChecked() else _generate_token()
        ssh_password = self.ssh_password_input.text()
        sudo_password = self.sudo_password_input.text()

        if not host or not user:
            self._append("Host and SSH user are required.\n")
            return
        if self.tls_self_signed.isChecked() and not tls_cn:
            self._append("HTTPS hostname or IP is required for self-signed TLS.\n")
            return
        if not token:
            self._append("Probe token is required.\n")
            return

        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        self._auto_close_pending = False
        self.log.clear()
        self._set_status("Starting", "Launching the probe install workflow.", "blue")
        self._append("Starting deploy...\n\n")

        self._saved_token = token
        self._saved_url = f"https://{tls_cn}:9821/metrics" if tls_mode == "self-signed" else f"http://{host}:9821/metrics"
        self._saved_cert = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "probe", "probe.crt")) if tls_mode == "self-signed" else ""

        self._thread = _DeployThread(
            host=host,
            user=user,
            tls_mode=tls_mode,
            tls_cn=tls_cn,
            token=token,
            ssh_password=ssh_password,
            sudo_password=sudo_password,
        )
        self._thread.output.connect(self._append)
        self._thread.done.connect(self._finish)
        self._thread.start()

    def _finish(self, rc: int) -> None:
        self.cancel_btn.setEnabled(True)
        self.start_btn.setEnabled(True)
        if rc == 0:
            saved = copy.deepcopy(self._config)
            if not saved.id:
                saved = new_probe_config(name=self.name_input.text().strip() or "Raspberry Pi")
            saved.enabled = True
            saved.name = self.name_input.text().strip() or "Raspberry Pi"
            saved.url = self._saved_url
            saved.token = self._saved_token
            saved.ca_cert_path = self._saved_cert
            upsert_probe_config(saved)
            self._append("\nSaved probe settings locally for the app.\n")
            self._set_status("Complete", "Probe installed successfully. This window will close automatically.", "green")
            self.start_btn.setEnabled(False)
            self.cancel_btn.setText("Close")
            self._auto_close_pending = True
            QTimer.singleShot(1800, self._close_if_pending)
        else:
            self._append(f"\nInstall failed with exit code {rc}.\n")
            self._set_status("Failed", "Install failed. Review the log output and retry.", "red")

    def _close_if_pending(self) -> None:
        if self._auto_close_pending and self.isVisible():
            self.accept()


def _extract_host(url: str) -> str:
    m = re.match(r"^https?://([^/:]+)", url or "")
    return m.group(1) if m else ""
