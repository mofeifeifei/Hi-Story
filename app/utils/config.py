from __future__ import annotations

from copy import deepcopy
import json
import sys
from pathlib import Path
from typing import Any


def _app_root_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def _resource_root_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parents[2]


ROOT_DIR = _app_root_dir()
RESOURCE_DIR = _resource_root_dir()
CONFIG_PATH = ROOT_DIR / "config.json"
DATA_DIR = ROOT_DIR / "data"
INDEX_DB_PATH = DATA_DIR / "index.db"
WORKS_DIR = DATA_DIR / "works"
LEGACY_DB_PATH = DATA_DIR / "novels.db"
PROMPTS_DIR = RESOURCE_DIR / "app" / "prompts"


DEFAULT_CONFIG: dict[str, Any] = {
    "provider": "OpenAI",
    "model_provider": "OpenAI",
    "protocol": "openai_compatible",
    "base_url": "https://api.openai.com/v1",
    "balance_url": "",
    "wire_api": "chat_completions",
    "requires_openai_auth": True,
    "api_key": "",
    "default_model": "gpt-4o-mini",
    "review_model": "",
    "model_reasoning_effort": "",
    "supports_reasoning": None,
    "supports_response_format": None,
    "disable_response_storage": True,
    "model_context_window": 1000000,
    "model_auto_compact_token_limit": 900000,
    "network_access": "enabled",
    "windows_wsl_setup_acknowledged": True,
    "agent_models": {
        "planner": "",
        "writer": "",
        "reviewer": "",
        "reviser": "",
        "memory": "",
        "title": "",
    },
    "temperature": 0.8,
    "timeout": 300,
    "max_retries": 2,
    "max_output_tokens": 12000,
    "long_text_max_output_tokens": 12000,
    "use_system_proxy": False,
    "proxy_url": "",
    "mock_mode": True,
    "ai": {
        "default_channel": "legacy",
        "channels": {},
    },
}

AGENT_MODEL_KEYS = ("planner", "writer", "reviewer", "reviser", "memory", "title")
CHANNEL_PROTOCOLS = {"openai_compatible", "anthropic"}


def normalize_ai_channel_id(value: Any) -> str:
    """Keep channel IDs stable and safe to use as JSON keys and URL values."""
    text = str(value or "").strip().lower().replace("_", "-")
    cleaned: list[str] = []
    last_dash = False
    for char in text:
        if char.isalnum() and char.isascii():
            cleaned.append(char)
            last_dash = False
        elif not last_dash:
            cleaned.append("-")
            last_dash = True
    result = "".join(cleaned).strip("-")
    return result or "legacy"


def _legacy_protocol(config: dict[str, Any]) -> str:
    value = str(config.get("protocol") or "").strip().lower()
    if value in CHANNEL_PROTOCOLS:
        return value
    provider = str(config.get("model_provider") or config.get("provider") or "").strip().lower()
    return "anthropic" if provider in {"claude", "anthropic"} else "openai_compatible"


def _agent_model_defaults(value: Any) -> dict[str, str]:
    raw = value if isinstance(value, dict) else {}
    return {key: str(raw.get(key) or "").strip() for key in AGENT_MODEL_KEYS}


def _legacy_channel(config: dict[str, Any]) -> dict[str, Any]:
    profile = {
        key: deepcopy(config.get(key, default))
        for key, default in DEFAULT_CONFIG.items()
        if key != "ai"
    }
    profile["name"] = str(config.get("channel_name") or config.get("provider") or "默认通道").strip()
    profile["protocol"] = _legacy_protocol(config)
    profile["agent_models"] = _agent_model_defaults(config.get("agent_models"))
    return profile


def _normalize_channel(raw: Any, fallback: dict[str, Any], channel_id: str) -> dict[str, Any]:
    source = raw if isinstance(raw, dict) else {}
    profile = deepcopy(fallback)
    profile.update({key: deepcopy(value) for key, value in source.items() if key != "ai"})
    profile["name"] = str(source.get("name") or profile.get("name") or channel_id).strip()
    protocol = str(source.get("protocol") or profile.get("protocol") or "openai_compatible").strip().lower()
    if protocol not in CHANNEL_PROTOCOLS:
        protocol = "openai_compatible"
    profile["protocol"] = protocol
    profile["agent_models"] = _agent_model_defaults(source.get("agent_models", profile.get("agent_models")))
    return profile


def ensure_ai_channels(config: dict[str, Any]) -> dict[str, Any]:
    """Normalize the multi-channel config while preserving legacy fields."""
    fallback = _legacy_channel(config)
    raw_ai = config.get("ai") if isinstance(config.get("ai"), dict) else {}
    raw_channels = raw_ai.get("channels") if isinstance(raw_ai.get("channels"), dict) else {}
    channels: dict[str, dict[str, Any]] = {}
    for raw_id, raw_channel in raw_channels.items():
        channel_id = normalize_ai_channel_id(raw_id)
        channels[channel_id] = _normalize_channel(raw_channel, fallback, channel_id)
    if not channels:
        channels["legacy"] = _normalize_channel(fallback, fallback, "legacy")
    requested = normalize_ai_channel_id(raw_ai.get("default_channel") or "legacy")
    default_channel = requested if requested in channels else next(iter(channels))
    config["ai"] = {"default_channel": default_channel, "channels": channels}
    return config


def apply_default_ai_channel(config: dict[str, Any]) -> dict[str, Any]:
    ensure_ai_channels(config)
    channel_id = str(config["ai"]["default_channel"])
    channel = config["ai"]["channels"][channel_id]
    for key in DEFAULT_CONFIG:
        if key == "ai" or key not in channel:
            continue
        config[key] = deepcopy(channel[key])
    return config


def resolve_ai_channel(config: dict[str, Any], channel_id: str | None = None) -> dict[str, Any]:
    """Return an isolated runtime config for one complete AI channel."""
    runtime = deepcopy(config)
    ensure_ai_channels(runtime)
    requested = normalize_ai_channel_id(channel_id or runtime["ai"]["default_channel"])
    if requested not in runtime["ai"]["channels"]:
        raise ValueError(f"AI 通道不存在：{requested}")
    channel = runtime["ai"]["channels"][requested]
    for key in DEFAULT_CONFIG:
        if key == "ai" or key not in channel:
            continue
        runtime[key] = deepcopy(channel[key])
    runtime["active_channel_id"] = requested
    return runtime


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    if not path.exists():
        config = deepcopy(DEFAULT_CONFIG)
        for template_path in [ROOT_DIR / "config.template.json", RESOURCE_DIR / "config.template.json"]:
            if template_path.exists():
                with template_path.open("r", encoding="utf-8") as f:
                    loaded_template = json.load(f)
                config.update(loaded_template)
                config["agent_models"] = {
                    **DEFAULT_CONFIG["agent_models"],
                    **loaded_template.get("agent_models", {}),
                }
                break
        ensure_ai_channels(config)
        apply_default_ai_channel(config)
        save_config(config, path)
        return config

    with path.open("r", encoding="utf-8") as f:
        loaded = json.load(f)

    config = deepcopy(DEFAULT_CONFIG)
    config.update(loaded)
    config["agent_models"] = {**DEFAULT_CONFIG["agent_models"], **loaded.get("agent_models", {})}
    ensure_ai_channels(config)
    apply_default_ai_channel(config)
    return config


def save_config(config: dict[str, Any], path: Path = CONFIG_PATH) -> None:
    config = deepcopy(config)
    ensure_ai_channels(config)
    apply_default_ai_channel(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def load_prompt(file_name: str) -> str:
    path = PROMPTS_DIR / file_name
    with path.open("r", encoding="utf-8") as f:
        return f.read().strip()


def parse_bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError(f"无法解析布尔值: {value}")
