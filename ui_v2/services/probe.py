from __future__ import annotations

import json
import os
import secrets
import shutil
import ssl
import subprocess
import urllib.request
from dataclasses import dataclass
from typing import Any


PROBE_CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".config", "laptop-health", "probes.json")
LEGACY_PROBE_CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".config", "laptop-health", "probe.json")
PROBE_TOKENS_PATH = os.path.join(os.path.expanduser("~"), ".config", "laptop-health", "probe_tokens.json")
LEGACY_PROBE_TOKEN_PATH = os.path.join(os.path.expanduser("~"), ".config", "laptop-health", "probe.token")
SECRET_TOOL_SERVICE = "laptop-health"


@dataclass
class ProbeConfig:
    id: str
    enabled: bool = False
    name: str = "Raspberry Pi"
    url: str = ""
    token: str = ""
    ca_cert_path: str = ""


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


def _secret_tool_account(probe_id: str) -> str:
    return f"pi-probe:{probe_id}"


def _load_token_from_secret_tool(probe_id: str) -> str:
    try:
        res = subprocess.run(
            ["secret-tool", "lookup", "service", SECRET_TOOL_SERVICE, "account", _secret_tool_account(probe_id)],
            text=True,
            capture_output=True,
            check=False,
        )
    except Exception:
        return ""
    if res.returncode != 0:
        return ""
    return (res.stdout or "").strip()


def _save_token_to_secret_tool(probe_id: str, token: str) -> bool:
    try:
        if not token:
            subprocess.run(
                ["secret-tool", "clear", "service", SECRET_TOOL_SERVICE, "account", _secret_tool_account(probe_id)],
                text=True,
                capture_output=True,
                check=False,
            )
            return True
        res = subprocess.run(
            ["secret-tool", "store", "--label", f"Laptop Health Probe Token ({probe_id})", "service", SECRET_TOOL_SERVICE, "account", _secret_tool_account(probe_id)],
            input=token,
            text=True,
            capture_output=True,
            check=False,
        )
        return res.returncode == 0
    except Exception:
        return False


def _load_token_map_from_file() -> dict[str, str]:
    try:
        with open(PROBE_TOKENS_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        data = {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v).strip() for k, v in data.items() if str(v).strip()}


def _save_token_map_to_file(tokens: dict[str, str]) -> None:
    _ensure_config_dir()
    payload = {str(k): str(v).strip() for k, v in tokens.items() if str(v).strip()}
    with open(PROBE_TOKENS_PATH, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
    try:
        os.chmod(PROBE_TOKENS_PATH, 0o600)
    except OSError:
        pass


def _load_probe_token(probe_id: str) -> str:
    if _secret_tool_available():
        token = _load_token_from_secret_tool(probe_id)
        if token:
            return token
    return _load_token_map_from_file().get(probe_id, "")


def _save_probe_token(probe_id: str, token: str) -> None:
    token = token.strip()
    if _secret_tool_available():
        _save_token_to_secret_tool(probe_id, token)
    tokens = _load_token_map_from_file()
    if token:
        tokens[probe_id] = token
    else:
        tokens.pop(probe_id, None)
    _save_token_map_to_file(tokens)


def _remove_probe_token(probe_id: str) -> None:
    _save_probe_token(probe_id, "")


def _new_probe_id() -> str:
    return f"probe-{secrets.token_hex(6)}"


def new_probe_config(*, name: str = "Raspberry Pi") -> ProbeConfig:
    return ProbeConfig(id=_new_probe_id(), enabled=False, name=name, url="", token="", ca_cert_path="")


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

    current_ids = {cfg.id for cfg in configs}
    existing_tokens = _load_token_map_from_file()
    for cfg in configs:
        _save_probe_token(cfg.id, cfg.token)
    for probe_id in list(existing_tokens):
        if probe_id not in current_ids:
            _remove_probe_token(probe_id)

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
    for path in (PROBE_CONFIG_PATH, PROBE_TOKENS_PATH, LEGACY_PROBE_CONFIG_PATH, LEGACY_PROBE_TOKEN_PATH):
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


def fetch_probe_snapshot(config: ProbeConfig) -> dict[str, Any]:
    url = config.url.strip()
    if not url:
        raise ValueError("Probe URL is empty")

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
        payload = json.loads(response.read().decode("utf-8", errors="replace"))

    if not isinstance(payload, dict):
        raise ValueError("Probe response was not a JSON object")
    return payload


def metric_as_float(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except Exception:
            return None
    return None
