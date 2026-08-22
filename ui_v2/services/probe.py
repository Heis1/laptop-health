from __future__ import annotations

import json
import os
import secrets
import shutil
import ssl
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


PROBE_CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".config", "laptop-health", "probes.json")
LEGACY_PROBE_CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".config", "laptop-health", "probe.json")
LEGACY_PROBE_TOKEN_PATH = os.path.join(os.path.expanduser("~"), ".config", "laptop-health", "probe.token")
SECRET_TOOL_SERVICE = "laptop-health"
PIHOLE_CACHE_TTL_S = 120.0
PIHOLE_RATE_LIMIT_BACKOFF_S = 180.0
MAX_REMOTE_JSON_BYTES = 512 * 1024
_PIHOLE_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_PIHOLE_BACKOFF_UNTIL: dict[str, float] = {}


def _require_https(url: str, label: str) -> None:
    if not url.lower().startswith("https://"):
        raise ValueError(f"{label} must use HTTPS. Update it in Probe settings and add the required CA certificate.")


@dataclass
class ProbeConfig:
    id: str
    enabled: bool = False
    name: str = "Raspberry Pi"
    url: str = ""
    token: str = ""
    ca_cert_path: str = ""
    pihole_enabled: bool = False
    pihole_url: str = ""
    pihole_password: str = ""


def _probe_config_dir() -> str:
    return os.path.dirname(PROBE_CONFIG_PATH)


def _ensure_config_dir() -> None:
    config_dir = _probe_config_dir()
    os.makedirs(config_dir, mode=0o700, exist_ok=True)
    try:
        os.chmod(config_dir, 0o700)
    except OSError:
        pass


def _secret_tool_available() -> bool:
    return shutil.which("secret-tool") is not None


def secret_store_required() -> bool:
    return _secret_tool_available()


def _secret_tool_account(secret_kind: str, probe_id: str) -> str:
    return f"{secret_kind}:{probe_id}"


def _load_secret_from_secret_tool(secret_kind: str, probe_id: str) -> str:
    try:
        res = subprocess.run(
            ["secret-tool", "lookup", "service", SECRET_TOOL_SERVICE, "account", _secret_tool_account(secret_kind, probe_id)],
            text=True,
            capture_output=True,
            check=False,
        )
    except Exception:
        return ""
    if res.returncode != 0:
        return ""
    return (res.stdout or "").strip()


def _save_secret_to_secret_tool(secret_kind: str, probe_id: str, value: str) -> bool:
    try:
        if not value:
            subprocess.run(
                ["secret-tool", "clear", "service", SECRET_TOOL_SERVICE, "account", _secret_tool_account(secret_kind, probe_id)],
                text=True,
                capture_output=True,
                check=False,
            )
            return True
        res = subprocess.run(
            ["secret-tool", "store", "--label", f"Laptop Health {secret_kind} ({probe_id})", "service", SECRET_TOOL_SERVICE, "account", _secret_tool_account(secret_kind, probe_id)],
            input=value,
            text=True,
            capture_output=True,
            check=False,
        )
        return res.returncode == 0
    except Exception:
        return False


def _load_probe_token(probe_id: str) -> str:
    if _secret_tool_available():
        token = _load_secret_from_secret_tool("pi-probe", probe_id)
        if token:
            return token
    return ""


def _save_probe_token(probe_id: str, token: str) -> None:
    token = token.strip()
    if not _secret_tool_available():
        raise RuntimeError("secret-tool is required to store probe credentials securely")
    _save_secret_to_secret_tool("pi-probe", probe_id, token)


def _remove_probe_token(probe_id: str) -> None:
    _save_probe_token(probe_id, "")


def _load_pihole_password(probe_id: str) -> str:
    if _secret_tool_available():
        password = _load_secret_from_secret_tool("pihole-password", probe_id)
        if password:
            return password
    return ""


def _save_pihole_password(probe_id: str, password: str) -> None:
    password = password.strip()
    if not _secret_tool_available():
        raise RuntimeError("secret-tool is required to store Pi-hole credentials securely")
    _save_secret_to_secret_tool("pihole-password", probe_id, password)


def _remove_pihole_password(probe_id: str) -> None:
    _save_pihole_password(probe_id, "")


def _new_probe_id() -> str:
    return f"probe-{secrets.token_hex(6)}"


def new_probe_config(*, name: str = "Raspberry Pi") -> ProbeConfig:
    return ProbeConfig(
        id=_new_probe_id(),
        enabled=False,
        name=name,
        url="",
        token="",
        ca_cert_path="",
        pihole_enabled=False,
        pihole_url="",
        pihole_password="",
    )


def _legacy_env_probe() -> ProbeConfig | None:
    url = (os.getenv("LAPTOP_HEALTH_PI_PROBE_URL") or "").strip()
    if not url:
        return None
    return ProbeConfig(
        id="env-default",
        enabled=True,
        name=(os.getenv("LAPTOP_HEALTH_PI_PROBE_NAME") or "Raspberry Pi").strip() or "Raspberry Pi",
        url=url,
        token=(os.getenv("LAPTOP_HEALTH_PI_PROBE_TOKEN") or "").strip(),
        ca_cert_path=(os.getenv("LAPTOP_HEALTH_PI_PROBE_CA_CERT") or "").strip(),
        pihole_enabled=False,
        pihole_url="",
        pihole_password="",
    )


def _load_legacy_single_probe() -> ProbeConfig | None:
    env_probe = _legacy_env_probe()
    try:
        with open(LEGACY_PROBE_CONFIG_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return env_probe

    if not isinstance(data, dict):
        return env_probe

    probe = ProbeConfig(
        id=_new_probe_id(),
        enabled=bool(data.get("enabled", env_probe.enabled if env_probe else False)),
        name=str(data.get("name", env_probe.name if env_probe else "Raspberry Pi") or "Raspberry Pi"),
        url=str(data.get("url", env_probe.url if env_probe else "") or "").strip(),
        token=(env_probe.token if env_probe else ""),
        ca_cert_path=str(data.get("ca_cert_path", env_probe.ca_cert_path if env_probe else "") or "").strip(),
        pihole_enabled=bool(data.get("pihole_enabled", False)),
        pihole_url=str(data.get("pihole_url", "") or "").strip(),
        pihole_password="",
    )
    if not probe.token:
        try:
            with open(LEGACY_PROBE_TOKEN_PATH, "r", encoding="utf-8") as handle:
                probe.token = handle.read().strip()
        except Exception:
            stored_token = str(data.get("token", "") or "").strip()
            probe.token = stored_token
    return probe


def load_probe_configs() -> list[ProbeConfig]:
    config_file_present = False
    try:
        with open(PROBE_CONFIG_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        config_file_present = True
    except Exception:
        data = None

    if isinstance(data, dict):
        items = data.get("probes", [])
    elif isinstance(data, list):
        items = data
    else:
        items = None

    probes: list[ProbeConfig] = []
    if isinstance(items, list):
        for raw in items:
            if not isinstance(raw, dict):
                continue
            probe_id = str(raw.get("id") or _new_probe_id())
            probes.append(
                ProbeConfig(
                    id=probe_id,
                    enabled=bool(raw.get("enabled", False)),
                    name=str(raw.get("name", "Raspberry Pi") or "Raspberry Pi"),
                    url=str(raw.get("url", "") or "").strip(),
                    token=_load_probe_token(probe_id),
                    ca_cert_path=str(raw.get("ca_cert_path", "") or "").strip(),
                    pihole_enabled=bool(raw.get("pihole_enabled", False)),
                    pihole_url=str(raw.get("pihole_url", "") or "").strip(),
                    pihole_password=_load_pihole_password(probe_id),
                )
            )

    if config_file_present:
        return probes

    legacy = _load_legacy_single_probe()
    if legacy is None:
        return []
    save_probe_configs([legacy])
    return [legacy]


def save_probe_configs(configs: list[ProbeConfig]) -> None:
    _ensure_config_dir()
    payload = {
        "probes": [
            {
                "id": cfg.id,
                "enabled": bool(cfg.enabled),
                "name": cfg.name,
                "url": cfg.url,
                "ca_cert_path": cfg.ca_cert_path,
                "pihole_enabled": bool(cfg.pihole_enabled),
                "pihole_url": cfg.pihole_url,
            }
            for cfg in configs
        ]
    }
    with open(PROBE_CONFIG_PATH, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
    try:
        os.chmod(PROBE_CONFIG_PATH, 0o600)
    except OSError:
        pass

    for cfg in configs:
        _save_probe_token(cfg.id, cfg.token)
        _save_pihole_password(cfg.id, cfg.pihole_password)

    for legacy_path in (LEGACY_PROBE_CONFIG_PATH, LEGACY_PROBE_TOKEN_PATH):
        try:
            os.remove(legacy_path)
        except FileNotFoundError:
            pass
        except OSError:
            pass


def clear_probe_configs() -> None:
    for cfg in load_probe_configs():
        _remove_probe_token(cfg.id)
        _remove_pihole_password(cfg.id)
    for path in (PROBE_CONFIG_PATH, LEGACY_PROBE_CONFIG_PATH, LEGACY_PROBE_TOKEN_PATH):
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        except OSError:
            pass


def upsert_probe_config(config: ProbeConfig) -> list[ProbeConfig]:
    configs = load_probe_configs()
    for index, existing in enumerate(configs):
        if existing.id == config.id:
            configs[index] = config
            save_probe_configs(configs)
            return configs
    configs.append(config)
    save_probe_configs(configs)
    return configs


def remove_probe_config(probe_id: str) -> list[ProbeConfig]:
    configs = [cfg for cfg in load_probe_configs() if cfg.id != probe_id]
    save_probe_configs(configs)
    return configs


def enabled_probe_configs() -> list[ProbeConfig]:
    return [cfg for cfg in load_probe_configs() if cfg.enabled and cfg.url.strip()]


def load_probe_config() -> ProbeConfig:
    configs = load_probe_configs()
    if configs:
        return configs[0]
    return new_probe_config()


def save_probe_config(config: ProbeConfig) -> None:
    upsert_probe_config(config)


def clear_probe_config() -> None:
    clear_probe_configs()


def _read_json_response_limited(response, *, limit: int = MAX_REMOTE_JSON_BYTES) -> dict[str, Any]:
    raw = response.read(limit + 1)
    if len(raw) > limit:
        raise ValueError(f"Remote response exceeded {limit} bytes")
    payload = json.loads(raw.decode("utf-8", errors="replace"))
    if not isinstance(payload, dict):
        raise ValueError("Remote response was not a JSON object")
    return payload


def fetch_probe_snapshot(config: ProbeConfig) -> dict[str, Any]:
    url = config.url.strip()
    if not url:
        raise ValueError("Probe URL is empty")
    _require_https(url, "Probe URL")

    req = urllib.request.Request(url)
    if config.token:
        req.add_header("Authorization", f"Bearer {config.token}")

    context = None
    if url.lower().startswith("https://"):
        if config.ca_cert_path:
            context = ssl.create_default_context(cafile=config.ca_cert_path)
        else:
            context = ssl.create_default_context()

    with urllib.request.urlopen(req, timeout=2.5, context=context) as response:
        return _read_json_response_limited(response)


def _ssl_context_for_url(config: ProbeConfig, url: str):
    if not url.lower().startswith("https://"):
        return None
    if config.ca_cert_path:
        return ssl.create_default_context(cafile=config.ca_cert_path)
    return ssl.create_default_context()


def _request_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    context=None,
    timeout: float = 5.0,
) -> dict[str, Any]:
    body = None
    req_headers = dict(headers or {})
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=body, headers=req_headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout, context=context) as response:
        return _read_json_response_limited(response)


def _normalize_pihole_url(url: str) -> str:
    base = url.strip().rstrip("/")
    if not base:
        return ""
    if "/admin/api.php" in base or base.endswith("/api") or "/api/" in base:
        return base
    if base.endswith("/admin"):
        return f"{base}/api.php"
    return f"{base}/admin/api.php"


def _pihole_api_root(url: str) -> str:
    base = url.strip().rstrip("/")
    if "/admin/api.php" in base:
        return base[: base.index("/admin/api.php")]
    if base.endswith("/api"):
        return base[:-4]
    return base


def _parse_top_map(payload: dict[str, Any], *possible_keys: str) -> list[str]:
    for key in possible_keys:
        data = payload.get(key)
        if isinstance(data, dict):
            items = sorted(data.items(), key=lambda item: item[1], reverse=True)[:3]
            return [f"{name} ({count})" for name, count in items]
    return []


def fetch_pihole_stats(config: ProbeConfig) -> dict[str, Any]:
    if not config.pihole_enabled:
        raise ValueError("Pi-hole stats are disabled for this probe")

    now = time.time()
    cached = _PIHOLE_CACHE.get(config.id)
    if cached is not None:
        cached_at, cached_payload = cached
        if now - cached_at < PIHOLE_CACHE_TTL_S:
            return cached_payload

    blocked_until = _PIHOLE_BACKOFF_UNTIL.get(config.id, 0.0)
    if blocked_until > now:
        if cached is not None:
            return cached[1]
        wait_s = max(1, int(blocked_until - now))
        raise RuntimeError(f"Pi-hole temporarily rate-limited. Retry in about {wait_s}s.")

    base_url = _normalize_pihole_url(config.pihole_url)
    if not base_url:
        raise ValueError("Pi-hole URL is empty")
    _require_https(base_url, "Pi-hole URL")

    context = _ssl_context_for_url(config, config.pihole_url)
    api_root = _pihole_api_root(config.pihole_url)
    headers: dict[str, str] = {}

    if config.pihole_password:
        auth = _request_json(
            f"{api_root}/api/auth",
            method="POST",
            payload={"password": config.pihole_password},
            context=context,
        )
        session = auth.get("session") if isinstance(auth.get("session"), dict) else {}
        sid = str(session.get("sid") or "").strip()
        csrf = str(session.get("csrf") or "").strip()
        if sid:
            headers["X-FTL-SID"] = sid
        if csrf:
            headers["X-FTL-CSRF"] = csrf

    summary = {}
    errors: list[str] = []
    for candidate_url, candidate_headers in (
        (f"{api_root}/api/stats/summary", headers),
        (f"{base_url}?summaryRaw", {}),
    ):
        try:
            summary = _request_json(candidate_url, headers=candidate_headers, context=context)
            if summary:
                break
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                _PIHOLE_BACKOFF_UNTIL[config.id] = time.time() + PIHOLE_RATE_LIMIT_BACKOFF_S
                if cached is not None:
                    return cached[1]
                raise RuntimeError("Pi-hole returned HTTP 429 Too Many Requests") from exc
            errors.append(str(exc))
        except Exception as exc:
            errors.append(str(exc))
    if not summary:
        raise RuntimeError(errors[-1] if errors else "Unable to fetch Pi-hole summary")

    status = None
    if "status" in summary:
        status = str(summary.get("status") or "").strip()
    elif "blocking" in summary:
        blocking = summary.get("blocking")
        if isinstance(blocking, str):
            lowered = blocking.strip().lower()
            if lowered in {"enabled", "true", "on", "active"}:
                status = "enabled"
            elif lowered in {"disabled", "false", "off", "inactive"}:
                status = "disabled"
        else:
            status = "enabled" if bool(blocking) else "disabled"
    elif "dns_queries_today" in summary or "ads_blocked_today" in summary or "queries" in summary:
        status = "enabled"

    result = {
        "status": status or "unknown",
        "queries_today": metric_as_float(summary.get("dns_queries_today") or summary.get("queries")),
        "ads_blocked_today": metric_as_float(summary.get("ads_blocked_today") or summary.get("blocked")),
        "blocked_percent": metric_as_float(summary.get("ads_percentage_today") or summary.get("blocked_percent")),
        "unique_clients": metric_as_float(summary.get("unique_clients") or summary.get("clients")),
        "top_clients": _parse_top_map(summary, "top_sources", "clients", "top_clients"),
        "top_domains": _parse_top_map(summary, "top_ads", "top_queries", "domains", "top_domains"),
    }
    _PIHOLE_CACHE[config.id] = (time.time(), result)
    _PIHOLE_BACKOFF_UNTIL.pop(config.id, None)
    return result


def metric_as_float(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except Exception:
            return None
    return None
