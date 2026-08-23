from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.utils.config import (
    AGENT_MODEL_KEYS,
    CHANNEL_PROTOCOLS,
    apply_default_ai_channel,
    ensure_ai_channels,
    normalize_ai_channel_id,
    resolve_ai_channel,
)


ALLOWED_CONFIG_KEYS = {
    "provider",
    "model_provider",
    "protocol",
    "base_url",
    "balance_url",
    "wire_api",
    "requires_openai_auth",
    "api_key",
    "default_model",
    "review_model",
    "agent_models",
    "temperature",
    "model_reasoning_effort",
    "supports_reasoning",
    "supports_response_format",
    "disable_response_storage",
    "model_context_window",
    "model_auto_compact_token_limit",
    "network_access",
    "windows_wsl_setup_acknowledged",
    "timeout",
    "max_retries",
    "max_output_tokens",
    "long_text_max_output_tokens",
    "use_system_proxy",
    "proxy_url",
    "mock_mode",
    "ai",
}

API_KEY_MASK = "********"
MODEL_DISCOVERY_KEYS = {
    "channel_id",
    "channel",
    "provider",
    "model_provider",
    "protocol",
    "base_url",
    "requires_openai_auth",
    "api_key",
    "timeout",
    "max_retries",
    "use_system_proxy",
    "proxy_url",
    "supports_reasoning",
    "supports_response_format",
}
BALANCE_QUERY_KEYS = {
    "channel_id",
    "channel",
    "provider",
    "model_provider",
    "protocol",
    "base_url",
    "balance_url",
    "requires_openai_auth",
    "api_key",
    "timeout",
    "use_system_proxy",
    "proxy_url",
}


def sanitize_config_update(current: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    unknown = sorted(set(body) - ALLOWED_CONFIG_KEYS)
    if unknown:
        raise ValueError("配置包含不支持的字段：" + "、".join(unknown))

    config = dict(current)
    for key in ALLOWED_CONFIG_KEYS:
        if key == "ai":
            continue
        if key in body:
            if key == "api_key" and body[key] == API_KEY_MASK:
                continue
            config[key] = body[key]

    config["provider"] = _text(config.get("provider"), "OpenAI")
    config["model_provider"] = _text(config.get("model_provider"), config["provider"])
    config["protocol"] = _choice(config.get("protocol"), CHANNEL_PROTOCOLS, "openai_compatible")
    config["base_url"] = _text(config.get("base_url"))
    config["balance_url"] = _text(config.get("balance_url"))
    config["wire_api"] = _choice(config.get("wire_api"), {"responses", "chat_completions"}, "chat_completions")
    config["requires_openai_auth"] = _bool(config.get("requires_openai_auth", True), "requires_openai_auth")
    config["api_key"] = _text(config.get("api_key"))
    config["default_model"] = _text(config.get("default_model"))
    config["review_model"] = _text(config.get("review_model"))
    config["agent_models"] = _agent_models(config.get("agent_models"))
    config["temperature"] = _number(config.get("temperature"), "temperature", 0.0, 2.0, 0.8)
    config["model_reasoning_effort"] = _text(config.get("model_reasoning_effort"))
    config["supports_reasoning"] = _optional_bool(config.get("supports_reasoning"), "supports_reasoning")
    config["supports_response_format"] = _optional_bool(
        config.get("supports_response_format"),
        "supports_response_format",
    )
    config["disable_response_storage"] = _bool(config.get("disable_response_storage", True), "disable_response_storage")
    config["model_context_window"] = _integer(config.get("model_context_window"), "model_context_window", 4096, 4000000, 1000000)
    config["model_auto_compact_token_limit"] = _integer(
        config.get("model_auto_compact_token_limit"),
        "model_auto_compact_token_limit",
        1024,
        int(config["model_context_window"]),
        min(900000, int(config["model_context_window"])),
    )
    config["network_access"] = _text(config.get("network_access"), "enabled")
    config["windows_wsl_setup_acknowledged"] = _bool(
        config.get("windows_wsl_setup_acknowledged", True),
        "windows_wsl_setup_acknowledged",
    )
    config["timeout"] = _integer(config.get("timeout"), "timeout", 10, 1800, 300)
    config["max_retries"] = _integer(config.get("max_retries"), "max_retries", 0, 5, 2)
    config["max_output_tokens"] = _integer(config.get("max_output_tokens"), "max_output_tokens", 512, 64000, 12000)
    config["long_text_max_output_tokens"] = _integer(
        config.get("long_text_max_output_tokens"),
        "long_text_max_output_tokens",
        4096,
        64000,
        12000,
    )
    config["use_system_proxy"] = _bool(config.get("use_system_proxy", False), "use_system_proxy")
    config["proxy_url"] = _text(config.get("proxy_url"))
    config["mock_mode"] = _bool(config.get("mock_mode", True), "mock_mode")
    if "ai" in body:
        config["ai"] = _sanitize_ai_config(current, body.get("ai"))
    ensure_ai_channels(config)
    apply_default_ai_channel(config)
    return config


def public_config(config: dict[str, Any]) -> dict[str, Any]:
    ensure_ai_channels(config)
    result = {
        "provider": config.get("provider", ""),
        "model_provider": config.get("model_provider", ""),
        "protocol": config.get("protocol", "openai_compatible"),
        "base_url": config.get("base_url", ""),
        "balance_url": config.get("balance_url", ""),
        "wire_api": config.get("wire_api", ""),
        "requires_openai_auth": bool(config.get("requires_openai_auth", True)),
        "api_key": API_KEY_MASK if config.get("api_key") else "",
        "default_model": config.get("default_model", ""),
        "review_model": config.get("review_model", ""),
        "agent_models": config.get("agent_models", {}),
        "temperature": float(config.get("temperature", 0.8) or 0.8),
        "model_reasoning_effort": config.get("model_reasoning_effort", ""),
        "supports_reasoning": config.get("supports_reasoning"),
        "supports_response_format": config.get("supports_response_format"),
        "disable_response_storage": bool(config.get("disable_response_storage", True)),
        "model_context_window": int(config.get("model_context_window", 1000000) or 1000000),
        "model_auto_compact_token_limit": int(config.get("model_auto_compact_token_limit", 900000) or 900000),
        "network_access": config.get("network_access", "enabled"),
        "windows_wsl_setup_acknowledged": bool(config.get("windows_wsl_setup_acknowledged", True)),
        "mock_mode": bool(config.get("mock_mode", True)),
        "timeout": int(config.get("timeout", 300) or 300),
        "max_retries": int(config.get("max_retries", 2) or 0),
        "max_output_tokens": int(config.get("max_output_tokens", 12000) or 12000),
        "long_text_max_output_tokens": int(config.get("long_text_max_output_tokens", 12000) or 12000),
        "use_system_proxy": bool(config.get("use_system_proxy", False)),
        "proxy_url": config.get("proxy_url", ""),
    }
    result["ai"] = _public_ai_config(config)
    return result


def model_discovery_config(current: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    unknown = sorted(set(body) - MODEL_DISCOVERY_KEYS)
    if unknown:
        raise ValueError("模型查询包含不支持的字段：" + "、".join(unknown))
    return _temporary_channel_config(current, body, MODEL_DISCOVERY_KEYS)


def balance_query_config(current: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    unknown = sorted(set(body) - BALANCE_QUERY_KEYS)
    if unknown:
        raise ValueError("余额查询包含不支持的字段：" + "、".join(unknown))
    return _temporary_channel_config(current, body, BALANCE_QUERY_KEYS)


def reveal_api_key(config: dict[str, Any], channel_id: str | None = None) -> str:
    """Return a key only for the explicit eye-button action."""
    runtime = resolve_ai_channel(config, channel_id)
    return str(runtime.get("api_key") or "")


def _sanitize_ai_config(current: dict[str, Any], value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("AI 通道配置必须是对象。")
    base = ensure_ai_channels(deepcopy(current)).get("ai", {})
    current_channels = base.get("channels") if isinstance(base.get("channels"), dict) else {}
    raw_channels = value.get("channels")
    if not isinstance(raw_channels, dict) or not raw_channels:
        raise ValueError("至少需要保留一个 AI 通道。")
    channels: dict[str, dict[str, Any]] = {}
    channel_keys = ALLOWED_CONFIG_KEYS - {"ai"}
    for raw_id, raw_channel in raw_channels.items():
        if not isinstance(raw_channel, dict):
            raise ValueError(f"AI 通道 {raw_id} 配置格式错误。")
        channel_id = normalize_ai_channel_id(raw_id)
        existing = current_channels.get(channel_id) if isinstance(current_channels, dict) else None
        fallback = deepcopy(existing) if isinstance(existing, dict) else deepcopy(current)
        meta = {
            "name": _text(raw_channel.get("name"), channel_id),
            "protocol": _choice(raw_channel.get("protocol"), CHANNEL_PROTOCOLS, "openai_compatible"),
        }
        patch = {key: raw_channel[key] for key in raw_channel if key in channel_keys}
        unknown = sorted(set(raw_channel) - channel_keys - {"name", "protocol", "api_key_configured"})
        if unknown:
            raise ValueError(f"AI 通道 {channel_id} 包含不支持的字段：{'、'.join(unknown)}")
        if "api_key" not in raw_channel or raw_channel.get("api_key") == API_KEY_MASK:
            patch.pop("api_key", None)
        # Validate and normalize the channel as an isolated legacy-shaped
        # config. Reusing fallback.ai here would re-apply the old default
        # channel after the patch and silently undo the new channel values.
        seed = deepcopy(fallback)
        seed["ai"] = {"default_channel": "legacy", "channels": {}}
        seed.update(patch)
        channel = sanitize_config_update(seed, {})
        channel.pop("ai", None)
        channel.update(meta)
        channels[channel_id] = channel
    requested = normalize_ai_channel_id(value.get("default_channel") or base.get("default_channel"))
    if requested not in channels:
        raise ValueError("默认 AI 通道不存在，请先选择一个已保存的通道。")
    return {"default_channel": requested, "channels": channels}


def _public_ai_config(config: dict[str, Any]) -> dict[str, Any]:
    ai = ensure_ai_channels(deepcopy(config)).get("ai", {})
    channels = ai.get("channels") if isinstance(ai.get("channels"), dict) else {}
    public_channels: dict[str, dict[str, Any]] = {}
    for channel_id, channel in channels.items():
        safe = deepcopy(channel)
        key = str(safe.get("api_key") or "")
        safe["api_key"] = API_KEY_MASK if key else ""
        safe["api_key_configured"] = bool(key)
        public_channels[channel_id] = safe
    return {
        "default_channel": ai.get("default_channel", "legacy"),
        "channels": public_channels,
    }


def _temporary_channel_config(
    current: dict[str, Any],
    body: dict[str, Any],
    allowed: set[str],
) -> dict[str, Any]:
    channel_id = str(body.get("channel_id") or "").strip()
    runtime = resolve_ai_channel(current, channel_id or None)
    # The temporary request must keep the selected channel active. Otherwise
    # sanitize_config_update() would apply the persisted default channel again.
    selected_id = str(runtime.get("active_channel_id") or "legacy")
    if isinstance(runtime.get("ai"), dict):
        runtime["ai"]["default_channel"] = selected_id
    raw_channel = body.get("channel") if isinstance(body.get("channel"), dict) else None
    patch = {
        key: value
        for key, value in (raw_channel or {}).items()
        if key in ALLOWED_CONFIG_KEYS and key != "ai"
    } if raw_channel is not None else {
        key: body[key] for key in allowed if key in body and key not in {"channel_id", "channel"}
    }
    patch.pop("name", None)
    if patch.get("api_key") in {None, "", API_KEY_MASK}:
        patch.pop("api_key", None)
    patch.pop("ai", None)
    return sanitize_config_update(runtime, patch)


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _choice(value: Any, allowed: set[str], default: str) -> str:
    text = _text(value, default)
    if text not in allowed:
        raise ValueError(f"配置 wire_api 只支持：{', '.join(sorted(allowed))}")
    return text


def _bool(value: Any, label: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off"}:
            return False
    raise ValueError(f"配置 {label} 必须是布尔值。")


def _optional_bool(value: Any, label: str) -> bool | None:
    if value in (None, "", "auto"):
        return None
    return _bool(value, label)


def _integer(value: Any, label: str, minimum: int, maximum: int, default: int) -> int:
    try:
        number = int(value if value not in (None, "") else default)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"配置 {label} 必须是整数。") from exc
    if number < minimum or number > maximum:
        raise ValueError(f"配置 {label} 必须在 {minimum} 到 {maximum} 之间。")
    return number


def _number(value: Any, label: str, minimum: float, maximum: float, default: float) -> float:
    try:
        number = float(value if value not in (None, "") else default)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"配置 {label} 必须是数字。") from exc
    if number < minimum or number > maximum:
        raise ValueError(f"配置 {label} 必须在 {minimum:g} 到 {maximum:g} 之间。")
    return number


def _agent_models(value: Any) -> dict[str, str]:
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise ValueError("配置 agent_models 必须是对象。")
    return {name: _text(value.get(name)) for name in AGENT_MODEL_KEYS}
