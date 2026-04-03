from __future__ import annotations

import base64
import hashlib
import os
import re
import shlex
import socket

from PySide6.QtCore import QThread, Qt, Signal, QTimer
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from ui_v2.services.probe import ProbeConfig, remove_probe_config
from ui_v2.widgets.prompt_dialog import PromptDialog


class _RemoveThread(QThread):
    output = Signal(str)
    done = Signal(int)

    def __init__(self, *, probe: ProbeConfig, host: str, user: str, ssh_password: str, sudo_password: str):
        super().__init__()
        self.probe = probe
        self.host = host
        self.user = user
        self.ssh_password = ssh_password
        self.sudo_password = sudo_password or ssh_password

    def run(self) -> None:
        try:
            import paramiko
        except Exception as exc:
            self.output.emit(f"Remove failed: Paramiko is unavailable: {exc}\n")
            self.done.emit(1)
            return

        install_dir = "/opt/pi-probe"
        service_name = "pi-probe"
        env_file_path = "/etc/pi-probe.env"
        token_file_path = "/etc/pi-probe.token"

        client = paramiko.SSHClient()
        client.load_system_host_keys()
        client.set_missing_host_key_policy(paramiko.RejectPolicy())

        try:
            self.output.emit(f"Removing probe from {self.user}@{self.host}\n")
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

            self.output.emit("Stopping and disabling probe service\n")
            self._run_remote(client, f"systemctl disable --now {service_name} >/dev/null 2>&1 || true", sudo=True)

            self.output.emit("Removing service files\n")
            self._run_remote(
                client,
                " && ".join(
                    [
                        f"rm -f /etc/systemd/system/{service_name}.service",
                        f"rm -f /etc/systemd/system/{service_name}.service.d/override.conf",
                        f"rmdir /etc/systemd/system/{service_name}.service.d >/dev/null 2>&1 || true",
                        f"rm -f {shlex.quote(env_file_path)} {shlex.quote(token_file_path)}",
                        f"rm -rf {shlex.quote(install_dir)}",
                        "systemctl daemon-reload",
                    ]
                ),
                sudo=True,
            )

            self.output.emit("\nRemote probe uninstall complete\n")
            self.done.emit(0)
        except paramiko.BadHostKeyException as exc:
            self.output.emit(
                "\nRemove failed: SSH host key verification failed.\n"
                f"Host: {self.host}\n"
                f"Expected key type: {exc.expected_key.get_name()}\n"
                "Check your known_hosts entry for this device before retrying.\n"
            )
            self.done.emit(1)
        except paramiko.SSHException as exc:
            self.output.emit(
                "\nRemove failed: SSH host could not be verified.\n"
                f"Host: {self.host}\n"
                "Add the device to ~/.ssh/known_hosts first, then retry.\n"
                f"Details: {exc}\n"
            )
            self.done.emit(1)
        except Exception as exc:
            self.output.emit(f"\nRemove failed: {exc}\n")
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


class ProbeRemoveDialog(QDialog):
    def __init__(self, probe: ProbeConfig, parent=None):
        super().__init__(parent)
        self._probe = probe
        self._thread: _RemoveThread | None = None
        self._auto_close_pending = False

        self.setModal(True)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        host = parent.window() if parent is not None else None
        if host is not None:
            self.setGeometry(host.geometry())
        else:
            self.resize(920, 680)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scrim = QFrame()
        scrim.setObjectName("RemoveScrim")
        scrim_lay = QVBoxLayout(scrim)
        scrim_lay.setContentsMargins(0, 0, 0, 0)
        scrim_lay.setSpacing(0)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addStretch(1)

        card = QFrame()
        card.setObjectName("RemoveCard")
        card.setFixedWidth(720)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(12)

        hdr = QHBoxLayout()
        title = QLabel("Remove Probe")
        title.setObjectName("RemoveTitle")
        hdr.addWidget(title)
        hdr.addStretch(1)
        close_btn = QPushButton("✕")
        close_btn.setObjectName("RemoveX")
        close_btn.clicked.connect(self.reject)
        hdr.addWidget(close_btn)
        lay.addLayout(hdr)

        subtitle = QLabel(
            "This removes the probe service from the monitored device and then removes the local app entry. "
            "If this is the first time you have connected to the device, Laptop Health will ask you to trust its SSH host key."
        )
        subtitle.setObjectName("RemoveSubtitle")
        subtitle.setWordWrap(True)
        lay.addWidget(subtitle)

        self.status_card = QFrame()
        self.status_card.setObjectName("RemoveStatusCard")
        status_l = QVBoxLayout(self.status_card)
        status_l.setContentsMargins(12, 10, 12, 10)
        status_l.setSpacing(4)
        self.status_badge = QLabel("Ready")
        self.status_badge.setObjectName("RemoveStatusBadge")
        status_l.addWidget(self.status_badge)
        self.status_text = QLabel("Confirm the host and credentials, then start the uninstall.")
        self.status_text.setObjectName("RemoveStatusText")
        self.status_text.setWordWrap(True)
        status_l.addWidget(self.status_text)
        lay.addWidget(self.status_card)

        form = QFormLayout()
        form.setSpacing(10)

        self.host_input = QLineEdit(_extract_host(probe.url))
        form.addRow("Pi hostname or IP", self.host_input)

        import getpass
        self.user_input = QLineEdit(getpass.getuser())
        form.addRow("Pi SSH user", self.user_input)

        self.ssh_password_input = QLineEdit("")
        self.ssh_password_input.setEchoMode(QLineEdit.Password)
        self.ssh_password_input.setPlaceholderText("Leave blank to use SSH key or agent if available")
        form.addRow("SSH password", self.ssh_password_input)

        self.sudo_password_input = QLineEdit("")
        self.sudo_password_input.setEchoMode(QLineEdit.Password)
        self.sudo_password_input.setPlaceholderText("Leave blank to reuse SSH password")
        form.addRow("sudo password", self.sudo_password_input)
        lay.addLayout(form)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setObjectName("RemoveLog")
        lay.addWidget(self.log, 1)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("ActionBtn")
        self.cancel_btn.clicked.connect(self.reject)
        actions.addWidget(self.cancel_btn)
        self.start_btn = QPushButton("Start Remove")
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
            QFrame#RemoveScrim {
                background: rgba(0, 0, 0, 0.55);
            }
            QFrame#RemoveCard {
                background: rgba(10, 14, 22, 0.92);
                border: 1px solid rgba(255,255,255,0.14);
                border-left: 6px solid rgba(248,113,113,0.95);
                border-radius: 16px;
            }
            QFrame#RemoveStatusCard {
                background: rgba(248,113,113,0.10);
                border: 1px solid rgba(248,113,113,0.20);
                border-radius: 12px;
            }
            QLabel#RemoveTitle {
                color: rgba(255,255,255,0.96);
                font-weight: 700;
                font-size: 18px;
            }
            QLabel#RemoveSubtitle, QLabel {
                color: rgba(248,251,255,0.92);
                font-size: 12px;
            }
            QLabel#RemoveStatusBadge {
                color: rgba(255,234,234,0.98);
                background: rgba(248,113,113,0.18);
                border: 1px solid rgba(248,113,113,0.24);
                border-radius: 999px;
                padding: 3px 10px;
                font-size: 11px;
                font-weight: 700;
                max-width: 120px;
            }
            QLabel#RemoveStatusText {
                color: rgba(248,251,255,0.84);
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
            }
            QLineEdit:focus {
                border: 1px solid rgba(248,113,113,0.75);
                background: rgba(255,255,255,0.12);
            }
            QTextEdit#RemoveLog {
                background: rgba(10, 14, 22, 0.52);
                color: rgba(255,255,255,0.88);
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 12px;
                padding: 10px;
                font-family: monospace;
                font-size: 12px;
            }
            QPushButton#RemoveX {
                color: rgba(255,255,255,0.75);
                background: transparent;
                border: 0px;
                padding: 4px 8px;
                border-radius: 10px;
                font-size: 14px;
            }
            QPushButton#RemoveX:hover {
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
        self._set_status("Ready", "Confirm the host and credentials, then start the uninstall.", "red")

    def _append(self, text: str) -> None:
        self.log.moveCursor(QTextCursor.End)
        self.log.insertPlainText(text)
        self.log.moveCursor(QTextCursor.End)
        self._update_status_from_output(text)

    def _set_status(self, badge: str, text: str, accent: str) -> None:
        styles = {
            "red": ("rgba(248,113,113,0.10)", "rgba(248,113,113,0.20)", "rgba(248,113,113,0.18)", "rgba(255,234,234,0.98)"),
            "orange": ("rgba(251,146,60,0.12)", "rgba(251,146,60,0.22)", "rgba(251,146,60,0.20)", "rgba(255,241,224,0.98)"),
            "green": ("rgba(52,211,153,0.12)", "rgba(52,211,153,0.24)", "rgba(52,211,153,0.18)", "rgba(220,255,238,0.98)"),
        }
        bg, border, pill_bg, pill_fg = styles.get(accent, styles["red"])
        self.status_card.setStyleSheet(f"background: {bg}; border: 1px solid {border}; border-radius: 12px;")
        self.status_badge.setStyleSheet(
            f"color: {pill_fg}; background: {pill_bg}; border: 1px solid {border}; border-radius: 999px; padding: 3px 10px; font-size: 11px; font-weight: 700;"
        )
        self.status_badge.setText(badge)
        self.status_text.setText(text)

    def _update_status_from_output(self, text: str) -> None:
        lower = text.lower()
        if "removing probe from" in lower:
            self._set_status("Connecting", "Connecting to the monitored device.", "orange")
        elif "stopping and disabling probe service" in lower:
            self._set_status("Stopping Service", "Stopping and disabling the probe service.", "orange")
        elif "removing service files" in lower:
            self._set_status("Removing Files", "Removing the probe service files from the device.", "orange")
        elif "remote probe uninstall complete" in lower:
            self._set_status("Complete", "Remote uninstall completed. Removing local app entry now.", "green")
        elif "remove failed" in lower:
            self._set_status("Failed", "Uninstall failed. Review the log output.", "red")

    def _start(self) -> None:
        host = self.host_input.text().strip()
        user = self.user_input.text().strip()
        ssh_password = self.ssh_password_input.text()
        sudo_password = self.sudo_password_input.text()
        if not host or not user:
            self._append("Host and SSH user are required.\n")
            return
        if not _ensure_host_trusted(self, host):
            self._append("SSH host trust was not established. Remove cancelled.\n")
            self._set_status("Blocked", "Trust the device SSH host key before running the uninstall.", "orange")
            return
        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        self.log.clear()
        self._set_status("Starting", "Launching the remote uninstall workflow.", "orange")
        self._append("Starting remove...\n\n")
        self._thread = _RemoveThread(
            probe=self._probe,
            host=host,
            user=user,
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
            remove_probe_config(self._probe.id)
            self._append("\nRemoved local probe entry.\n")
            self._set_status("Complete", "Probe removed from the monitored device and from Laptop Health.", "green")
            self.start_btn.setEnabled(False)
            self.cancel_btn.setText("Close")
            self._auto_close_pending = True
            QTimer.singleShot(1500, self._close_if_pending)
        else:
            self._append(f"\nRemove failed with exit code {rc}.\n")
            self._set_status("Failed", "Remote uninstall failed. Local entry was kept.", "red")

    def _close_if_pending(self) -> None:
        if self._auto_close_pending and self.isVisible():
            self.accept()


def _extract_host(url: str) -> str:
    m = re.match(r"^https?://([^/:]+)", url or "")
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
