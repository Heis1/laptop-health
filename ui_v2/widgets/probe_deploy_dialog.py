from __future__ import annotations

import base64
import copy
import hashlib
import os
import re
import shlex
import socket
import uuid

from PySide6.QtCore import QThread, Qt, Signal, QTimer
from PySide6.QtGui import QGuiApplication, QTextCursor
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

from ui_v2.services.probe import ProbeConfig, new_probe_config, secret_store_required, upsert_probe_config
from ui_v2.widgets.prompt_dialog import PromptDialog


class _DeployThread(QThread):
    output = Signal(str)
    done = Signal(int)

    def __init__(self, *, host: str, user: str, bind_host: str, port: int, tls_mode: str, tls_cn: str, token: str, ssh_password: str, sudo_password: str):
        super().__init__()
        self.host = host
        self.user = user
        self.bind_host = bind_host
        self.port = port
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
        client.set_missing_host_key_policy(paramiko.RejectPolicy())

        try:
            self.output.emit(f"Installing probe on {self.user}@{self.host}\n")
            connect_kwargs = {
                "hostname": self.host,
                "username": self.user,
                "timeout": 15,
                "look_for_keys": True,
                "allow_agent": True,
            }
            if self.ssh_password:
                connect_kwargs["password"] = self.ssh_password
            client.connect(**connect_kwargs)

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
            env_lines = [f"PI_PROBE_HOST={self.bind_host}", f"PI_PROBE_PORT={self.port}"]
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
                verify = f"curl -fsS -H {shlex.quote('Authorization: Bearer ' + self.token)} http://localhost:{self.port}/metrics >/dev/null 2>/dev/null"
                dashboard_url = f"http://{self.host}:{self.port}/metrics"
            else:
                if re.match(r'^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$', self.tls_cn):
                    verify = f"curl -fsS --cacert {shlex.quote(remote_cert_path)} -H {shlex.quote('Authorization: Bearer ' + self.token)} https://{self.tls_cn}:{self.port}/metrics >/dev/null 2>/dev/null"
                else:
                    verify = f"curl -fsS --cacert {shlex.quote(remote_cert_path)} --resolve {shlex.quote(f'{self.tls_cn}:{self.port}:127.0.0.1')} -H {shlex.quote('Authorization: Bearer ' + self.token)} https://{self.tls_cn}:{self.port}/metrics >/dev/null 2>/dev/null"
                dashboard_url = f"https://{self.tls_cn}:{self.port}/metrics"

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
        except paramiko.BadHostKeyException as exc:
            self.output.emit(
                "\nInstall failed: SSH host key verification failed.\n"
                f"Host: {self.host}\n"
                f"Expected key type: {exc.expected_key.get_name()}\n"
                "Check your known_hosts entry for this device before retrying.\n"
            )
            self.done.emit(1)
        except paramiko.SSHException as exc:
            self.output.emit(
                "\nInstall failed: SSH host could not be verified.\n"
                f"Host: {self.host}\n"
                "Add the device to ~/.ssh/known_hosts first, then retry.\n"
                f"Details: {exc}\n"
            )
            self.done.emit(1)
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
        self._last_failure_summary = ""

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

        subtitle = QLabel(
            "Run the probe deployment inside the app. The target device must be a Linux system with SSH, sudo, and systemd. "
            "Passwords are used only for this session. On first connect, Laptop Health will ask you to trust the device SSH host key."
        )
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
            "leave the port at 9821 unless you need a different one, and use self-signed TLS unless you intentionally want plain HTTP on your LAN. "
            "This installer is intended for Raspberry Pi OS and other Debian-family Linux targets."
        )
        intro_body.setObjectName("DeployHintBody")
        intro_body.setWordWrap(True)
        intro_l.addWidget(intro_body)
        lay.addWidget(intro)

        self.secret_warning = QFrame()
        self.secret_warning.setObjectName("DeployWarningCard")
        secret_l = QVBoxLayout(self.secret_warning)
        secret_l.setContentsMargins(12, 10, 12, 10)
        secret_l.setSpacing(4)
        secret_title = QLabel("Desktop Secret Storage Required")
        secret_title.setObjectName("DeployWarningTitle")
        secret_l.addWidget(secret_title)
        secret_body = QLabel(
            "This install needs `secret-tool` / libsecret support so Laptop Health can save the probe token securely.\n\n"
            "Install `libsecret-tools`, then reopen this dialog."
        )
        secret_body.setObjectName("DeployWarningBody")
        secret_body.setWordWrap(True)
        secret_l.addWidget(secret_body)
        lay.addWidget(self.secret_warning)
        self.secret_warning.setVisible(not secret_store_required())

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

        self.port_input = QLineEdit(_extract_port(config.url) or "9821")
        self.port_input.setPlaceholderText("9821")
        form.addRow(self._label_row("Probe port", self._help_port), self.port_input)

        self.bind_host_input = QLineEdit("0.0.0.0")
        self.bind_host_input.setPlaceholderText("0.0.0.0")
        form.addRow(self._label_row("Bind address", self._help_bind_host), self.bind_host_input)

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
        self.ssh_password_input.setPlaceholderText("Leave blank to use SSH key or agent if available")
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
        self.copy_log_btn = QPushButton("Copy Install Log")
        self.copy_log_btn.setObjectName("ActionBtn")
        self.copy_log_btn.clicked.connect(self._copy_log)
        self.copy_log_btn.setEnabled(False)
        actions.addWidget(self.copy_log_btn)
        self.copy_log_btn.hide()

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
            QFrame#DeployWarningCard {
                background: rgba(248,113,113,0.10);
                border: 1px solid rgba(248,113,113,0.24);
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
            QLabel#DeployWarningTitle {
                color: rgba(255,234,234,0.98);
                font-weight: 700;
                font-size: 12px;
            }
            QLabel#DeployWarningBody {
                color: rgba(255,234,234,0.88);
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
        if secret_store_required():
            self._set_status("Ready", "Fill in the probe details, then start the install.", "blue")
        else:
            self.start_btn.setEnabled(False)
            self.start_btn.setToolTip("Install desktop secret storage first: sudo apt install libsecret-tools")
            self._set_status("Blocked", "Desktop secret storage is required before the app can save probe credentials.", "red")

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
        self.copy_log_btn.setEnabled(bool(self.log.toPlainText().strip()))
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
            self._set_status("Failed", "Install did not complete. The failure details are in the log panel below.", "red")
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
            "If the URL will be https://raspberrypi.local:9822/metrics then enter raspberrypi.local",
        )

    def _help_port(self) -> None:
        self._show_help(
            "Probe Port",
            "This is the TCP port the probe service will listen on.\n\n"
            "Default:\n"
            "9821\n\n"
            "Change it only if:\n"
            "you already use 9821 on that device, or you want multiple probe instances on the same Pi.\n\n"
            "Examples:\n"
            "9821\n"
            "9822",
        )

    def _help_bind_host(self) -> None:
        self._show_help(
            "Bind Address",
            "This controls which network address the probe service listens on.\n\n"
            "Recommended:\n"
            "Use 0.0.0.0 if this laptop needs to reach the probe over the LAN.\n\n"
            "Stronger restriction:\n"
            "Use a specific device IP if you want the probe exposed only on one interface.\n\n"
            "Examples:\n"
            "0.0.0.0\n"
            "192.0.2.51",
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
            "You can leave it blank if your SSH key or SSH agent already works for this device.\n\n"
            "The app uses the password only for this install session.",
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
        bind_host = self.bind_host_input.text().strip() or "0.0.0.0"
        port_text = self.port_input.text().strip()
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
        try:
            port = int(port_text or "9821")
        except ValueError:
            self._append("Probe port must be a number.\n")
            return
        if port < 1 or port > 65535:
            self._append("Probe port must be between 1 and 65535.\n")
            return
        if not token:
            self._append("Probe token is required.\n")
            return
        if not secret_store_required():
            self._append("Desktop secret storage is required before installing a probe.\n")
            self._append("Install `secret-tool` / libsecret support, then retry.\n")
            self._set_status("Blocked", "Desktop secret storage is required before the app can save probe credentials.", "red")
            return
        if not _ensure_host_trusted(self, host):
            self._append("SSH host trust was not established. Install cancelled.\n")
            self._set_status("Blocked", "Trust the device SSH host key before running the install.", "orange")
            return

        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        self._auto_close_pending = False
        self._last_failure_summary = ""
        self.log.clear()
        self.copy_log_btn.hide()
        self.copy_log_btn.setEnabled(False)
        self._set_status("Starting", "Launching the probe install workflow.", "blue")
        self._append("Starting deploy...\n\n")

        self._saved_token = token
        self._saved_url = f"https://{tls_cn}:{port}/metrics" if tls_mode == "self-signed" else f"http://{host}:{port}/metrics"
        self._saved_cert = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "probe", "probe.crt")) if tls_mode == "self-signed" else ""

        self._thread = _DeployThread(
            host=host,
            user=user,
            bind_host=bind_host,
            port=port,
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
            try:
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
            except Exception as exc:
                self._append(f"\nInstall completed on the Pi, but saving credentials locally failed: {exc}\n")
                self.copy_log_btn.show()
                self.copy_log_btn.setEnabled(bool(self.log.toPlainText().strip()))
                self._set_status("Failed", "The probe installed on the Pi, but the app could not save credentials locally.", "red")
        else:
            self._append(f"\nInstall failed with exit code {rc}.\n")
            self._last_failure_summary = self._summarize_failure()
            if self._last_failure_summary:
                self._append(f"\nFailure summary: {self._last_failure_summary}\n")
            self.copy_log_btn.show()
            self.copy_log_btn.setEnabled(bool(self.log.toPlainText().strip()))
            self._set_status("Failed", "Install failed. The details are shown below and can be copied with 'Copy Install Log'.", "red")

    def _summarize_failure(self) -> str:
        lines = [line.strip() for line in self.log.toPlainText().splitlines() if line.strip()]
        for line in reversed(lines):
            lower = line.lower()
            if lower.startswith("install failed:"):
                return line
            if "permission denied" in lower:
                return line
            if "verification failed" in lower:
                return line
            if "runtimeerror" in lower:
                return line
        return lines[-1] if lines else ""

    def _copy_log(self) -> None:
        text = self.log.toPlainText().strip()
        if not text:
            return
        if self._last_failure_summary:
            text = f"Failure summary: {self._last_failure_summary}\n\n{text}"
        QGuiApplication.clipboard().setText(text)
        self._set_status("Failed", "Install failed. The log has been copied to the clipboard.", "red")

    def _close_if_pending(self) -> None:
        if self._auto_close_pending and self.isVisible():
            self.accept()


def _extract_host(url: str) -> str:
    m = re.match(r"^https?://([^/:]+)", url or "")
    return m.group(1) if m else ""


def _extract_port(url: str) -> str:
    m = re.match(r"^https?://[^/:]+:(\d+)", url or "")
    return m.group(1) if m else ""


def _ssh_fingerprint_sha256(key) -> str:
    digest = hashlib.sha256(key.asbytes()).digest()
    return "SHA256:" + base64.b64encode(digest).decode("ascii").rstrip("=")


def _known_hosts_path() -> str:
    return os.path.join(os.path.expanduser("~"), ".ssh", "known_hosts")


def _host_is_known(host: str) -> bool:
    try:
        import paramiko
    except Exception:
        return False
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    return client.get_host_keys().lookup(host) is not None


def _fetch_remote_host_key(host: str, port: int = 22):
    import paramiko

    sock = socket.create_connection((host, port), timeout=8)
    transport = paramiko.Transport(sock)
    try:
        transport.start_client(timeout=8)
        return transport.get_remote_server_key()
    finally:
        transport.close()


def _store_host_key(host: str, key) -> None:
    import paramiko

    ssh_dir = os.path.join(os.path.expanduser("~"), ".ssh")
    os.makedirs(ssh_dir, mode=0o700, exist_ok=True)
    try:
        os.chmod(ssh_dir, 0o700)
    except OSError:
        pass

    path = _known_hosts_path()
    host_keys = paramiko.HostKeys()
    if os.path.exists(path):
        host_keys.load(path)
    host_keys.add(host, key.get_name(), key)
    host_keys.save(path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _ensure_host_trusted(parent, host: str) -> bool:
    if _host_is_known(host):
        return True

    try:
        key = _fetch_remote_host_key(host)
    except Exception as exc:
        PromptDialog(
            parent,
            "SSH Host Verification Failed",
            (
                f"Laptop Health could not fetch the SSH host key for {host}.\n\n"
                f"Details: {exc}\n\n"
                "Connect to the device once with ssh or fix the network issue, then retry."
            ),
            accent="red",
            ok_text="Close",
            cancel_text="Cancel",
        ).exec()
        return False

    prompt = PromptDialog(
        parent,
        "Trust SSH Host Key",
        (
            f"This device is not yet trusted in SSH known_hosts.\n\n"
            f"Host: {host}\n"
            f"Key type: {key.get_name()}\n"
            f"Fingerprint: {_ssh_fingerprint_sha256(key)}\n\n"
            "Only continue if this fingerprint matches the device you expect to manage."
        ),
        accent="blue",
        ok_text="Trust and Continue",
        cancel_text="Cancel",
    )
    if prompt.exec() != QDialog.Accepted:
        return False

    try:
        _store_host_key(host, key)
    except Exception as exc:
        PromptDialog(
            parent,
            "Failed To Save SSH Trust",
            (
                f"Laptop Health could not save the SSH host key for {host} into known_hosts.\n\n"
                f"Details: {exc}"
            ),
            accent="red",
            ok_text="Close",
            cancel_text="Cancel",
        ).exec()
        return False
    return True
