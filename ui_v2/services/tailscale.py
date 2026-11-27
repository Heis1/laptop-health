from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any

import system


@dataclass
class TailscaleNode:
    name: str
    node_id: str = ""
    dns_name: str = ""
    ips: list[str] = field(default_factory=list)
    os_name: str = ""
    is_self: bool = False
    online: bool = False
    active: bool = False
    relay: str = ""
    direct_address: str = ""
    tx_bytes: int = 0
    rx_bytes: int = 0
    exit_node: bool = False
    subnet_routes: list[str] = field(default_factory=list)
    last_seen: str = ""
    key_expired: bool = False
    authorized: bool = True
    tags: list[str] = field(default_factory=list)


@dataclass
class TailscaleStatus:
    installed: bool
    backend_state: str = ""
    self_node: TailscaleNode | None = None
    peers: list[TailscaleNode] = field(default_factory=list)
    error: str = ""

    @property
    def connected(self) -> bool:
        return self.backend_state.lower() == "running" and self.self_node is not None

    @property
    def nodes(self) -> list[TailscaleNode]:
        """Every node visible to the local Tailscale client, including this one."""
        return ([self.self_node] if self.self_node is not None else []) + self.peers


def _run_tailscale(*args: str, timeout: float = 8.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["tailscale", *args],
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def _as_strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _node_from_payload(raw: dict[str, Any], *, is_self: bool = False) -> TailscaleNode:
    addresses = _as_strings(raw.get("TailscaleIPs"))
    if not addresses:
        addresses = _as_strings(raw.get("AllowedIPs"))
    return TailscaleNode(
        name=str(raw.get("HostName") or raw.get("DNSName") or "Unknown node").rstrip("."),
        node_id=str(raw.get("ID") or raw.get("NodeID") or ""),
        dns_name=str(raw.get("DNSName") or "").rstrip("."),
        ips=addresses,
        os_name=str(raw.get("OS") or ""),
        is_self=is_self,
        online=bool(raw.get("Online", False)),
        active=bool(raw.get("Active", False)),
        relay=str(raw.get("Relay") or ""),
        direct_address=str(raw.get("CurAddr") or ""),
        tx_bytes=int(raw.get("TxBytes") or 0),
        rx_bytes=int(raw.get("RxBytes") or 0),
        exit_node=bool(raw.get("ExitNode", False) or raw.get("ExitNodeOption", False)),
        subnet_routes=_as_strings(raw.get("PrimaryRoutes")),
        last_seen=str(raw.get("LastSeen") or raw.get("LastHandshake") or raw.get("LastWrite") or ""),
        key_expired=bool(raw.get("Expired", False) or raw.get("KeyExpired", False)),
        authorized=not bool(raw.get("MachineAuthorized") is False),
        tags=_as_strings(raw.get("Tags")),
    )


def get_tailscale_status() -> TailscaleStatus:
    if shutil.which("tailscale") is None:
        return TailscaleStatus(False, error="Tailscale is not installed")
    try:
        result = _run_tailscale("status", "--json")
    except subprocess.TimeoutExpired:
        return TailscaleStatus(True, error="Timed out while waiting for the Tailscale daemon")
    except OSError as exc:
        return TailscaleStatus(True, error=str(exc))

    if result.returncode != 0:
        return TailscaleStatus(True, error=(result.stderr or result.stdout or "Tailscale status failed").strip())
    try:
        payload = json.loads(result.stdout)
    except (TypeError, ValueError) as exc:
        return TailscaleStatus(True, error=f"Could not read Tailscale status: {exc}")
    if not isinstance(payload, dict):
        return TailscaleStatus(True, error="Tailscale returned an unexpected status format")

    self_raw = payload.get("Self")
    self_node = _node_from_payload(self_raw, is_self=True) if isinstance(self_raw, dict) else None
    peers_raw = payload.get("Peer", {})
    peer_values = peers_raw.values() if isinstance(peers_raw, dict) else peers_raw if isinstance(peers_raw, list) else []
    peers = [_node_from_payload(peer) for peer in peer_values if isinstance(peer, dict)]
    peers.sort(key=lambda peer: (not peer.online, peer.name.lower()))
    return TailscaleStatus(True, str(payload.get("BackendState") or ""), self_node, peers)


def set_tailscale_enabled(enabled: bool) -> tuple[bool, str]:
    tailscale = shutil.which("tailscale")
    if tailscale is None:
        return False, "Tailscale is not installed"
    privilege_tool = system.preferred_privilege_tool()
    if privilege_tool is None:
        return False, "Administrator authorisation (pkexec or sudo) is required to change Tailscale state"
    try:
        # `tailscale up` and `tailscale down` change machine-wide network
        # state.  Invoking them as the desktop user usually fails silently
        # from the UI because the local API requires administrator authority.
        # Ask Polkit only after the user presses the button.
        code, stdout, stderr = system.run_privileged(
            privilege_tool, [tailscale, "up" if enabled else "down"], timeout_s=30.0
        )
    except Exception as exc:
        return False, str(exc)
    if code == 124:
        return False, "Tailscale did not finish the request in time"
    output = (stderr or stdout or "").strip()
    if code != 0:
        return False, output or "Tailscale could not apply that change"
    return True, output or ("Tailscale is starting" if enabled else "Tailscale is off")
