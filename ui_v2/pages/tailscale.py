from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtCore import QThreadPool, QTimer, Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from ui_v2.services.tailscale import TailscaleNode, TailscaleStatus, get_tailscale_status, set_tailscale_enabled
from ui_v2.theme import current_theme_mode
from ui_v2.widgets.cards import MetricCard
from ui_v2.workers import Worker


def _bytes(value: int) -> str:
    units = ("B", "KB", "MB", "GB", "TB")
    amount = float(max(0, value))
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            return f"{amount:.0f} {unit}" if unit == "B" else f"{amount:.1f} {unit}"
        amount /= 1024
    return "0 B"


def _last_seen(value: str) -> str:
    if not value:
        return "No recent activity reported"
    try:
        when = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        seconds = max(0, int((datetime.now(timezone.utc) - when).total_seconds()))
        if seconds < 60:
            return "Seen just now"
        if seconds < 3600:
            return f"Seen {seconds // 60}m ago"
        if seconds < 86400:
            return f"Seen {seconds // 3600}h ago"
        return f"Seen {seconds // 86400}d ago"
    except (TypeError, ValueError):
        return f"Last activity: {value}"


class TailscaleNodeRow(QFrame):
    def __init__(self, node: TailscaleNode):
        super().__init__()
        self.setObjectName("Card")
        self.setProperty("accent", "green" if node.online else "orange")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)

        top = QHBoxLayout()
        name = QLabel(f"{node.name}{' (this device)' if node.is_self else ''}")
        name.setObjectName("CardTitle")
        top.addWidget(name)
        top.addStretch(1)
        if node.key_expired:
            state_text = "KEY EXPIRED"
        elif not node.authorized:
            state_text = "UNAUTHORIZED"
        elif node.online:
            state_text = "ONLINE"
        else:
            state_text = "OFFLINE"
        state = QLabel(state_text)
        state.setObjectName("Badge")
        top.addWidget(state)
        layout.addLayout(top)

        address = QLabel(" • ".join(node.ips) or node.dns_name or "No Tailscale address reported")
        address.setObjectName("CardSub")
        address.setWordWrap(True)
        address.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(address)

        if node.direct_address:
            connection = f"Direct: {node.direct_address}"
        elif node.relay:
            connection = f"DERP relay: {node.relay}"
        elif node.active:
            connection = "Active connection"
        else:
            connection = "No active path"
        details = [connection, _last_seen(node.last_seen)]
        if node.os_name:
            details.append(node.os_name)
        if node.exit_node:
            details.append("Exit node available")
        if node.subnet_routes:
            details.append("Routes: " + ", ".join(node.subnet_routes))
        if node.tags:
            details.append("Tags: " + ", ".join(node.tags))
        details.append(f"↑ {_bytes(node.tx_bytes)}  ↓ {_bytes(node.rx_bytes)}")
        meta = QLabel(" • ".join(details))
        meta.setObjectName("CardSub")
        meta.setWordWrap(True)
        layout.addWidget(meta)


class TailscalePage(QWidget):
    def __init__(self):
        super().__init__()
        self.pool = QThreadPool()
        self._workers: list[object] = []
        self._refreshing = False
        self._changing_state = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)

        title = QLabel("Tailscale")
        title.setObjectName("PageTitle")
        outer.addWidget(title)
        subtitle = QLabel("Live status from this laptop's Tailscale client. Every node reported by the current tailnet map is listed below.")
        subtitle.setObjectName("InspectorSub")
        subtitle.setWordWrap(True)
        outer.addWidget(subtitle)

        actions = QHBoxLayout()
        self.toggle_btn = QPushButton("Turn On")
        self.toggle_btn.setObjectName("ActionButton")
        self.toggle_btn.clicked.connect(self._toggle)
        actions.addWidget(self.toggle_btn)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setObjectName("ActionButton")
        refresh_btn.clicked.connect(self.refresh_now)
        actions.addWidget(refresh_btn)
        actions.addStretch(1)
        self.updated = QLabel("Checking status…")
        self.updated.setObjectName("InspectorSub")
        actions.addWidget(self.updated)
        outer.addLayout(actions)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        self.state_card = MetricCard("Tailscale", "Checking", "Contacting local daemon", "blue")
        self.device_card = MetricCard("This device", "—", "No identity available", "blue")
        self.peers_card = MetricCard("Tailnet nodes", "—", "No node data available", "blue")
        self.routes_card = MetricCard("Local role", "—", "No route role reported", "blue")
        for index, card in enumerate((self.state_card, self.device_card, self.peers_card, self.routes_card)):
            card.setMinimumHeight(145)
            grid.addWidget(card, index // 2, (index % 2) * 2, 1, 2)
        outer.addLayout(grid)

        section = QLabel("All tailnet nodes")
        section.setObjectName("SectionTitle")
        outer.addWidget(section)
        self.nodes_scroll = QScrollArea()
        self.nodes_scroll.setWidgetResizable(True)
        self.nodes_scroll.setObjectName("TailscaleNodeScroll")
        self.nodes_host = QWidget()
        self.nodes_layout = QVBoxLayout(self.nodes_host)
        self.nodes_layout.setContentsMargins(2, 2, 2, 2)
        self.nodes_layout.setSpacing(10)
        self.nodes_layout.addStretch(1)
        self.nodes_scroll.setWidget(self.nodes_host)
        outer.addWidget(self.nodes_scroll, 1)
        self.apply_theme_mode(current_theme_mode())

        self.timer = QTimer(self)
        self.timer.setInterval(5000)
        self.timer.timeout.connect(self.refresh_now)
        # The page is constructed with the rest of the application, but should
        # not poll the local daemon until the user actually opens it.

    def apply_theme_mode(self, mode: str) -> None:
        """Keep the scroll viewport behind translucent node cards on-theme."""
        background = "#f2f6fb" if str(mode).lower() == "light" else "#0b1220"
        self.nodes_scroll.setStyleSheet(
            f"""
            QScrollArea#TailscaleNodeScroll {{
                background: {background};
                border: 0;
            }}
            QScrollArea#TailscaleNodeScroll > QWidget > QWidget {{
                background: {background};
            }}
            """
        )
        self.nodes_host.setStyleSheet(f"background: {background};")

    def refresh_now(self) -> None:
        if not self.isVisible():
            return
        if self._refreshing or self._changing_state:
            return
        self._refreshing = True
        worker = Worker(get_tailscale_status)
        self._workers.append(worker)

        def done(result):
            self._refreshing = False
            try:
                self._workers.remove(worker)
            except ValueError:
                pass
            if isinstance(result, Exception):
                self._apply_error(str(result))
            else:
                self._apply_status(result)

        worker.signals.finished.connect(done)
        self.pool.start(worker)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.timer.start()
        self.refresh_now()

    def hideEvent(self, event) -> None:
        self.timer.stop()
        super().hideEvent(event)

    def _toggle(self) -> None:
        enabled = self.toggle_btn.text() == "Turn On"
        self._changing_state = True
        self.toggle_btn.setEnabled(False)
        self.updated.setText("Applying Tailscale change…")
        worker = Worker(lambda: set_tailscale_enabled(enabled))
        self._workers.append(worker)

        def done(result):
            self._changing_state = False
            self.toggle_btn.setEnabled(True)
            try:
                self._workers.remove(worker)
            except ValueError:
                pass
            if isinstance(result, Exception):
                self.updated.setText(str(result))
            else:
                ok, message = result
                self.updated.setText(message if ok else f"Could not change Tailscale: {message}")
            self.refresh_now()

        worker.signals.finished.connect(done)
        self.pool.start(worker)

    def _clear_nodes(self) -> None:
        while self.nodes_layout.count() > 1:
            item = self.nodes_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()

    def _apply_error(self, message: str) -> None:
        self.state_card.set_values("Unavailable", message, "red")
        self.device_card.set_values("—", "Tailscale status unavailable", "blue")
        self.peers_card.set_values("—", "No node data available", "blue")
        self.routes_card.set_values("—", "No route data available", "blue")
        self.toggle_btn.setEnabled(False)
        self.updated.setText("Status check failed")
        self._clear_nodes()

    def _apply_status(self, status: TailscaleStatus) -> None:
        if not status.installed:
            self._apply_error(status.error)
            return
        if status.error:
            self.state_card.set_values("Offline", status.error, "orange")
            self.device_card.set_values("—", "Tailscale daemon is not reachable", "blue")
            self.peers_card.set_values("—", "Start Tailscale to see the tailnet", "blue")
            self.routes_card.set_values("—", "No route data available", "blue")
            self.toggle_btn.setText("Turn On")
            self.toggle_btn.setEnabled(True)
            self.updated.setText("Daemon unavailable")
            self._clear_nodes()
            return

        node = status.self_node
        connected = status.connected
        self.state_card.set_values("Connected" if connected else (status.backend_state or "Off"), "Tailscale tunnel is active" if connected else "Tailscale tunnel is not active", "green" if connected else "orange")
        self.toggle_btn.setText("Turn Off" if connected else "Turn On")
        self.toggle_btn.setEnabled(True)
        if node is not None:
            self.device_card.set_values(node.name, " • ".join(node.ips) or node.dns_name or "No Tailscale IP reported", "green" if connected else "blue")
            roles = []
            if node.exit_node:
                roles.append("Exit node")
            if node.subnet_routes:
                roles.append("Subnet routes: " + ", ".join(node.subnet_routes[:2]))
            self.routes_card.set_values(" • ".join(roles) or "Standard node", node.dns_name or "No MagicDNS name reported", "blue")
        else:
            self.device_card.set_values("—", "No local node identity reported", "blue")
            self.routes_card.set_values("—", "No route role reported", "blue")

        nodes = status.nodes
        online = sum(1 for item in nodes if item.online)
        active = sum(1 for item in nodes if item.active or item.direct_address or item.relay)
        offline = len(nodes) - online
        self.peers_card.set_values(
            f"{online}/{len(nodes)} online",
            f"{active} with an active path • {offline} offline",
            "green" if online else "blue",
        )
        self.updated.setText("Live • refreshes every 5 seconds")
        self._clear_nodes()
        if nodes:
            for item in nodes:
                self.nodes_layout.insertWidget(self.nodes_layout.count() - 1, TailscaleNodeRow(item))
        else:
            empty = QLabel("No nodes are currently reported by this tailnet.")
            empty.setObjectName("InspectorSub")
            self.nodes_layout.insertWidget(0, empty)
