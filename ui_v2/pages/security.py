from __future__ import annotations

from html import escape
from importlib import metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import urllib.error
import urllib.request

from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtWidgets import QDialog, QGridLayout, QHBoxLayout, QLabel, QPushButton, QTextBrowser, QVBoxLayout, QWidget

from ui_v2.services.probe import enabled_probe_configs, secret_store_required
from ui_v2.services.updates import get_update_summary, list_upgradable
from ui_v2.theme import current_theme_mode, qss
from ui_v2.widgets.cards import MetricCard


SECURITY_PREFS_PATH = Path.home() / ".config" / "laptop-health" / "security_prefs.json"
DEPENDENCY_AUDIT_CACHE_PATH = Path.home() / ".cache" / "laptop-health" / "dependency_audit.json"
NETWORK_DISCOVERY_REVIEW_REVISION = "network-discovery-v1"
OSV_QUERY_BATCH_URL = "https://api.osv.dev/v1/querybatch"
OSV_MAX_BATCH_QUERIES = 1000
DEPENDENCY_AUDIT_SCOPE = "installed-software-v2"


def _pinned_requirements(requirements_path: Path) -> list[tuple[str, str]]:
    """Return exact PyPI pins from the build requirements file."""
    requirements: list[tuple[str, str]] = []
    try:
        lines = requirements_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return requirements
    for line in lines:
        value = line.split("#", 1)[0].strip()
        if "==" not in value:
            continue
        name, version = (part.strip() for part in value.split("==", 1))
        if name and version:
            requirements.append((name, version))
    return requirements


def _load_cached_dependency_audit() -> dict | None:
    try:
        data = json.loads(DEPENDENCY_AUDIT_CACHE_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("scope") != DEPENDENCY_AUDIT_SCOPE:
            return None
        return data
    except (OSError, ValueError):
        return None


def _save_dependency_audit(audit: dict) -> None:
    try:
        DEPENDENCY_AUDIT_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        DEPENDENCY_AUDIT_CACHE_PATH.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
        os.chmod(DEPENDENCY_AUDIT_CACHE_PATH, 0o600)
    except OSError:
        pass


def _optional_command_updates(command: str, arguments: list[str]) -> dict:
    """List updates for an optional package source without changing the system."""
    executable = shutil.which(command)
    if not executable:
        return {"source": command, "state": "not_installed", "updates": []}
    try:
        result = subprocess.run(
            [executable, *arguments], capture_output=True, check=False, text=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        return {"source": command, "state": "unavailable", "updates": []}
    if result.returncode:
        return {"source": command, "state": "unavailable", "updates": []}
    updates = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return {"source": command, "state": "updates" if updates else "current", "updates": updates}


def _command_lines(command: str, arguments: list[str]) -> list[str] | None:
    executable = shutil.which(command)
    if not executable:
        return []
    try:
        result = subprocess.run([executable, *arguments], capture_output=True, check=False, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode:
        return None
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _python_packages(requirements: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Inventory packages installed in the interpreter that runs Laptop Health."""
    packages = {name.lower(): (name, version) for name, version in requirements}
    for distribution in metadata.distributions():
        name = distribution.metadata.get("Name")
        if name and distribution.version:
            packages[name.lower()] = (name, distribution.version)
    python = shutil.which("python3")
    if python:
        try:
            result = subprocess.run(
                [python, "-m", "pip", "list", "--user", "--format=json"],
                capture_output=True, check=False, text=True, timeout=30,
            )
            for item in json.loads(result.stdout) if result.returncode == 0 else []:
                name, version = item.get("name"), item.get("version")
                if name and version:
                    packages[name.lower()] = (name, version)
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    return sorted(packages.values(), key=lambda item: item[0].lower())


def _unmanaged_desktop_launchers() -> list[str]:
    """Identify user desktop launchers that point outside managed package locations."""
    applications = Path.home() / ".local" / "share" / "applications"
    unmanaged: list[str] = []
    try:
        entries = list(applications.glob("*.desktop"))
    except OSError:
        return unmanaged
    managed_prefixes = ("/usr/", "/bin/", "/snap/", "/var/lib/flatpak/")
    for entry in entries:
        if entry.stem == "laptop-health":
            continue
        try:
            exec_line = next((line[5:] for line in entry.read_text(errors="ignore").splitlines() if line.startswith("Exec=")), "")
        except OSError:
            continue
        executable = exec_line.split(" ", 1)[0].strip().strip('"')
        if executable and executable.startswith("/") and not executable.startswith(managed_prefixes):
            unmanaged.append(f"{entry.stem}: {executable}")
    for directory in (Path.home() / ".local" / "bin", Path.home() / "Applications"):
        try:
            candidates = list(directory.iterdir())
        except OSError:
            continue
        for candidate in candidates:
            try:
                if candidate.name == "laptop-health":
                    continue
                if candidate.is_file() and os.access(candidate, os.X_OK):
                    unmanaged.append(str(candidate))
            except OSError:
                continue
    return sorted(set(unmanaged))


def _installed_software_sources() -> list[dict]:
    """Return current update state for the supported system package sources."""
    summary = get_update_summary()
    apt_updates = list_upgradable() if summary.total is not None else []
    if summary.total is None:
        apt_state = "unavailable"
    elif summary.held or (summary.security or 0) > 0 or summary.reboot_required:
        apt_state = "attention"
    elif summary.total:
        apt_state = "updates"
    else:
        apt_state = "current"
    apt = {
        "source": "APT",
        "state": apt_state,
        "updates": [item.get("name", "package") for item in apt_updates],
        "security_updates": int(summary.security or 0),
        "held": int(summary.held or 0),
        "reboot_required": bool(summary.reboot_required),
        "installed": len(_command_lines("dpkg-query", ["-W", "-f=${binary:Package}\\n"]) or []),
    }
    flatpak = _optional_command_updates("flatpak", ["remote-ls", "--updates", "--columns=application,version"])
    flatpak["installed"] = len(_command_lines("flatpak", ["list", "--app", "--runtime", "--columns=application"]) or [])
    snap = _optional_command_updates("snap", ["refresh", "--list"])
    snap["installed"] = len(_command_lines("snap", ["list"]) or [])
    return [apt, flatpak, snap, _firmware_updates(), _container_images()]


def _container_images() -> dict:
    """Inventory local container images; image CVE scanning needs a dedicated scanner."""
    for command in ("docker", "podman"):
        if not shutil.which(command):
            continue
        images = _command_lines(command, ["images", "--format", "{{.Repository}}:{{.Tag}}"])
        if images is not None:
            return {
                "source": "Containers",
                "state": "review" if images else "current",
                "updates": images,
                "installed": len(images),
            }
    return {"source": "Containers", "state": "not_installed", "updates": []}


def _firmware_updates() -> dict:
    """Read fwupd's update state without installing firmware or changing settings."""
    executable = shutil.which("fwupdmgr")
    if not executable:
        return {"source": "Firmware", "state": "not_installed", "updates": []}
    try:
        result = subprocess.run(
            [executable, "get-updates", "--json"], capture_output=True, check=False, text=True, timeout=45
        )
        data = json.loads(result.stdout) if result.stdout.strip() else {}
    except (OSError, ValueError, subprocess.SubprocessError):
        return {"source": "Firmware", "state": "unavailable", "updates": []}
    if data.get("Error"):
        return {"source": "Firmware", "state": "unavailable", "updates": []}
    releases = []
    for device in data.get("Devices", []):
        for release in device.get("Releases", []):
            releases.append(f"{device.get('Name', 'device')}: {release.get('Version', 'update')}")
    return {"source": "Firmware", "state": "updates" if releases else "current", "updates": releases}


def _audit_dependencies(requirements_path: Path) -> dict:
    """Assess installed software and audit this application's pinned PyPI packages with OSV."""
    build_requirements = _pinned_requirements(requirements_path)
    python_packages = _python_packages(build_requirements)
    sources = _installed_software_sources()
    unmanaged = _unmanaged_desktop_launchers()
    if not python_packages:
        return {"status": "review", "detail": "No Python packages were found", "sources": sources, "unmanaged": unmanaged}

    try:
        vulnerabilities = []
        seen_advisory_ids: set[tuple[str, str]] = set()
        for start in range(0, len(python_packages), OSV_MAX_BATCH_QUERIES):
            batch = python_packages[start : start + OSV_MAX_BATCH_QUERIES]
            payload = {
                "queries": [
                    {"package": {"ecosystem": "PyPI", "name": name}, "version": version}
                    for name, version in batch
                ]
            }
            request = urllib.request.Request(
                OSV_QUERY_BATCH_URL,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json", "User-Agent": "Laptop-Health/1.0"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                results = json.loads(response.read().decode("utf-8")).get("results", [])
            if len(results) != len(batch):
                raise ValueError("OSV returned an incomplete audit result")
            for (name, version), result in zip(batch, results):
                for vulnerability in result.get("vulns", []):
                    advisory_ids = {str(vulnerability.get("id", "unknown advisory"))}
                    advisory_ids.update(str(alias) for alias in vulnerability.get("aliases", []))
                    advisory_keys = {(name, advisory_id) for advisory_id in advisory_ids}
                    if seen_advisory_ids.intersection(advisory_keys):
                        continue
                    seen_advisory_ids.update(advisory_keys)
                    vulnerabilities.append({
                        "id": vulnerability.get("id", "unknown advisory"),
                        "aliases": vulnerability.get("aliases", []),
                        "package": name,
                        "version": version,
                        "summary": vulnerability.get("summary", ""),
                        "details": vulnerability.get("details", ""),
                        "references": vulnerability.get("references", []),
                        "affected": vulnerability.get("affected", []),
                    })
        audit = {
            "scope": DEPENDENCY_AUDIT_SCOPE,
            "status": "vulnerable" if vulnerabilities else "clean",
            "checked_at": time.time(),
            "package_count": len(python_packages),
            "build_package_count": len(build_requirements),
            "sources": sources,
            "unmanaged": unmanaged,
            "vulnerabilities": vulnerabilities,
        }
        source_states = {source["state"] for source in audit["sources"]}
        if audit["status"] == "clean" and ("attention" in source_states or "updates" in source_states or "review" in source_states or "unavailable" in source_states or unmanaged):
            audit["status"] = "review"
        _save_dependency_audit(audit)
        return audit
    except (OSError, ValueError, urllib.error.URLError):
        cached = _load_cached_dependency_audit()
        if cached:
            cached["cached"] = True
            cached["sources"] = sources
            cached["unmanaged"] = unmanaged
            cached_states = {source["state"] for source in sources}
            if cached.get("status") == "clean" and (
                "attention" in cached_states or "updates" in cached_states or "review" in cached_states or "unavailable" in cached_states or unmanaged
            ):
                cached["status"] = "review"
            return cached
        return {
            "status": "review",
            "detail": "PyPI advisory service could not be reached; system package-source checks are shown below",
            "package_count": len(python_packages),
            "build_package_count": len(build_requirements),
            "sources": sources,
            "unmanaged": unmanaged,
            "vulnerabilities": [],
        }


def _group_vulnerabilities(vulnerabilities: list[dict]) -> list[dict]:
    """Group OSV's lightweight batch results into readable package-level findings."""
    grouped: dict[tuple[str, str], dict] = {}
    for vulnerability in vulnerabilities:
        key = (str(vulnerability.get("package", "package")), str(vulnerability.get("version", "")))
        finding = grouped.setdefault(key, {"package": key[0], "version": key[1], "ids": [], "summaries": [], "affected": []})
        advisory_id = str(vulnerability.get("id", "unknown advisory"))
        if advisory_id not in finding["ids"]:
            finding["ids"].append(advisory_id)
        summary = vulnerability.get("summary") or vulnerability.get("details")
        if summary and summary not in finding["summaries"]:
            finding["summaries"].append(str(summary))
        finding["affected"].extend(vulnerability.get("affected", []))
    return sorted(grouped.values(), key=lambda item: (item["package"].lower(), item["version"]))


class DependencyAuditWorker(QThread):
    audit_ready = Signal(object)

    def __init__(self, requirements_path: Path, parent=None):
        super().__init__(parent)
        self.requirements_path = requirements_path

    def run(self) -> None:
        self.audit_ready.emit(_audit_dependencies(self.requirements_path))


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
        self.dependency_details_btn = QPushButton("View status")
        self.dependency_details_btn.setObjectName("ActionButton")
        self.dependency_details_btn.setEnabled(False)
        self.dependency_details_btn.clicked.connect(self._show_dependency_advisories)
        self.dependencies = MetricCard(
            "Installed software", "Checking", "APT, Flatpak, Snap, Python packages, and user launchers", "blue", right_widget=self.dependency_details_btn
        )
        self._dependency_worker: DependencyAuditWorker | None = None
        self._dependency_audit_status: str | None = None
        self._dependency_audit: dict = {}
        self._dependency_refresh_timer = QTimer(self)
        self._dependency_refresh_timer.setInterval(60 * 60 * 1000)
        self._dependency_refresh_timer.timeout.connect(self._run_scheduled_dependency_audit)
        self._dependency_refresh_timer.start()
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
        self.score = MetricCard("Security score", "—", "Calculating current local posture", "blue")
        grid.addWidget(self.score, 2, 0, 1, 2)
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
        self._refresh_dependency_audit(requirement)
        if self._network_review_acknowledged():
            self.network.set_values("Acknowledged", "No new discovery guidance since your review", "green")
            self.network_review_btn.setText("View acknowledgement")
        else:
            self.network.set_values("Review", "Confirm safe and authorised scan use", "orange")
            self.network_review_btn.setText("Review details")
        self._update_score(insecure)
        bullets = [
            "1. Replace HTTP Probe and Pi-hole URLs with HTTPS, then add your local CA certificate in Probe settings.",
            "2. Apply system security updates regularly, particularly the Linux kernel and OpenSSL.",
            "3. Use Quiet discovery on networks you own. Detailed scans should only be run with permission.",
        ]
        self.guidance.setText("\n".join(bullets))
        self.assessed_at.setText(f"Last assessed {time.strftime('%H:%M:%S')} • {len(configs)} active probe(s)")

    def _update_score(self, insecure) -> None:
        score = 100
        if insecure:
            score -= min(45, len(insecure) * 30)
        if not secret_store_required():
            score -= 20
        if self._dependency_audit_status == "vulnerable":
            score -= 30
        elif self._dependency_audit_status in {"review", "unavailable"}:
            score -= 15
        if not self._network_review_acknowledged():
            score -= 5
        score = max(0, score)
        if score >= 90:
            score_label, score_accent = "Strong", "green"
        elif score >= 75:
            score_label, score_accent = "Good", "blue"
        elif score >= 55:
            score_label, score_accent = "Needs attention", "orange"
        else:
            score_label, score_accent = "High risk", "red"
        self.score.set_values(f"{score}/100", f"{score_label} • based on transport, keyring, dependencies, and reviews", score_accent)

    def _refresh_dependency_audit(self, requirements_path: Path) -> None:
        if self._dependency_worker and self._dependency_worker.isRunning():
            return
        self.dependencies.set_values("Checking", "Inventorying APT, Flatpak, Snap, Python, and user launchers", "blue")
        self.dependency_details_btn.setEnabled(True)
        self._dependency_worker = DependencyAuditWorker(requirements_path, self)
        self._dependency_worker.audit_ready.connect(self._show_dependency_audit)
        self._dependency_worker.finished.connect(self._dependency_worker.deleteLater)
        self._dependency_worker.start()

    def _run_scheduled_dependency_audit(self) -> None:
        """Refresh vulnerability information hourly while Laptop Health is running."""
        requirements_path = Path(__file__).resolve().parents[2] / "requirements-build.txt"
        self._refresh_dependency_audit(requirements_path)

    def _show_dependency_audit(self, audit: dict) -> None:
        self._dependency_worker = None
        self._dependency_audit = audit
        status = audit.get("status")
        self._dependency_audit_status = "unavailable" if audit.get("cached") and status == "clean" else status
        sources = audit.get("sources", [])
        unmanaged = audit.get("unmanaged", [])
        source_updates = [source for source in sources if source.get("state") in {"attention", "updates"}]
        source_unavailable = [source for source in sources if source.get("state") == "unavailable"]
        if status == "clean":
            count = audit.get("package_count", 0)
            if audit.get("cached"):
                self.dependencies.set_values(
                    "Cached",
                    f"No pending updates recorded; OSV checked {count} installed Python package(s)",
                    "orange",
                )
            else:
                self.dependencies.set_values(
                    "Current",
                    f"No pending APT, Flatpak, or Snap updates; OSV checked {count} installed Python package(s)",
                    "green",
                )
        elif status == "vulnerable":
            vulnerabilities = audit.get("vulnerabilities", [])
            self.dependency_details_btn.setEnabled(bool(vulnerabilities))
            findings = _group_vulnerabilities(vulnerabilities)
            first = findings[0] if findings else {}
            extra = f" across {len(findings)} package(s)" if len(findings) > 1 else ""
            suffix = " • cached result" if audit.get("cached") else ""
            self.dependencies.set_values(
                "Advisories found",
                f"{first.get('package', 'package')} {first.get('version', '')}: {len(first.get('ids', []))} OSV advisory ID(s){extra}{suffix}",
                "red",
            )
        elif status == "review":
            update_count = sum(len(source.get("updates", [])) for source in source_updates)
            attention = next((source for source in source_updates if source.get("state") == "attention"), None)
            if attention and attention.get("security_updates"):
                detail = f"APT has {attention['security_updates']} pending security update(s); review details"
            elif update_count:
                detail = f"{update_count} pending update(s) across installed software sources; review details"
            elif source_unavailable:
                detail = f"Could not check {', '.join(source['source'] for source in source_unavailable)} updates"
            elif unmanaged:
                detail = f"{len(unmanaged)} user launcher(s) point to unmanaged software; review details"
            else:
                detail = audit.get("detail", "Installed software needs review")
            label = "Updates available" if source_updates else "Partial assessment"
            self.dependencies.set_values(label, detail, "orange")
        else:
            self.dependencies.set_values("Unavailable", audit.get("detail", "OSV audit could not be reached"), "orange")
        configs = enabled_probe_configs()
        self._update_score([cfg for cfg in configs if not cfg.url.lower().startswith("https://")])

    def _show_dependency_advisories(self) -> None:
        vulnerabilities = self._dependency_audit.get("vulnerabilities", [])
        sources = self._dependency_audit.get("sources", [])
        if not vulnerabilities and not sources:
            return
        dialog = QDialog(self)
        dialog.setObjectName("SecurityAdvisoryDialog")
        dialog.setWindowTitle("Installed software assessment")
        dialog.setMinimumWidth(680)
        mode = current_theme_mode()
        if mode == "light":
            surface, text, border = "#f3efe7", "#1b2430", "#d9cab3"
        else:
            surface, text, border = "#0b1220", "#e8f0ff", "#1a2a41"
        dialog.setStyleSheet(
            qss(mode)
            + f"""
            QDialog#SecurityAdvisoryDialog {{ background: {surface}; color: {text}; border: 1px solid {border}; }}
            QDialog#SecurityAdvisoryDialog QLabel {{ color: {text}; }}
            QDialog#SecurityAdvisoryDialog QTextBrowser {{ background: {surface}; color: {text}; border: 1px solid {border}; }}
            """
        )
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(22, 20, 22, 20)
        title = QLabel("Installed software assessment")
        title.setObjectName("PageTitle")
        layout.addWidget(title)
        remediation = QLabel(
            "APT, Flatpak, and Snap use their own update metadata. OSV advisories below apply only to "
            "installed Python packages; Linux distributions may backport fixes without changing upstream versions."
        )
        remediation.setObjectName("InspectorSub")
        remediation.setWordWrap(True)
        layout.addWidget(remediation)
        details = QTextBrowser()
        details.setOpenExternalLinks(True)
        details.setReadOnly(True)
        parts = []
        if sources:
            parts.append("<h3>Package-source status</h3><ul>")
            for source in sources:
                name = escape(str(source.get("source", "source")))
                state = str(source.get("state", "unknown"))
                updates = source.get("updates", [])
                if state == "not_installed":
                    text = "not installed"
                elif state == "unavailable":
                    text = "could not be checked"
                elif state == "current":
                    text = "no pending updates"
                elif state == "review":
                    text = f"{source.get('installed', len(updates))} image(s); dedicated image vulnerability scanning is not configured"
                else:
                    text = f"{source.get('installed', 0)} installed; {len(updates)} pending update(s)"
                    if source.get("security_updates"):
                        text += f"; {source['security_updates']} marked security"
                    if source.get("held"):
                        text += f"; {source['held']} held"
                    if source.get("reboot_required"):
                        text += "; restart required"
                package_list = f"<br>{escape(', '.join(map(str, updates[:30])))}" if updates else ""
                parts.append(f"<li><b>{name}</b>: {escape(text)}{package_list}</li>")
            parts.append("</ul>")
        unmanaged = self._dependency_audit.get("unmanaged", [])
        if unmanaged:
            parts.append("<h3>Unmanaged user launchers</h3><p>These executables are outside APT, Flatpak, and Snap, so update and advisory coverage cannot be verified automatically.</p><ul>")
            parts.extend(f"<li>{escape(item)}</li>" for item in unmanaged[:100])
            parts.append("</ul>")
        if vulnerabilities:
            parts.append("<h3>PyPI advisories for installed Python packages</h3>")
        for finding in _group_vulnerabilities(vulnerabilities):
            fixed_versions = []
            for affected in finding.get("affected", []):
                for version_range in affected.get("ranges", []):
                    fixed_versions.extend(
                        event["fixed"] for event in version_range.get("events", []) if event.get("fixed")
                    )
            fixed = ", ".join(dict.fromkeys(fixed_versions))
            recommendation = (
                f"Update this Python package to at least <b>{fixed}</b>, if compatible."
                if fixed
                else "OSV did not return a fixed version in this batch result; open the linked advisory before updating."
            )
            links = [
                f'<a href="https://osv.dev/vulnerability/{escape(advisory_id, quote=True)}">{escape(advisory_id)}</a>'
                for advisory_id in finding["ids"]
            ]
            summary = escape(finding["summaries"][0]) if finding["summaries"] else "OSV returned advisory identifiers without summaries."
            parts.append(
                f"<h3>{escape(finding['package'])} {escape(finding['version'])} — {len(finding['ids'])} advisory ID(s)</h3>"
                f"<p>{summary}</p><p><b>Recommended action:</b> {recommendation}</p><p>{' • '.join(links)}</p>"
            )
        details.setHtml("".join(parts))
        layout.addWidget(details, 1)
        close = QPushButton("Close")
        close.setObjectName("ActionButton")
        close.clicked.connect(dialog.accept)
        layout.addWidget(close)
        dialog.exec()
