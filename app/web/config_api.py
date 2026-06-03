from __future__ import annotations

from typing import Any


ALLOWED_CONFIG_KEYS = {
    "provider",
    "model_provider",
    "base_url",
    "wire_api",
    "requires_openai_auth",
    "api_key",
    "default_model",
    "review_model",
    "agent_models",
    "temperature",
    "model_reasoning_effort",
    "disable_response_storage",
    "model_context_window",
    "model_auto_compact_token_limit",
    "network_access",
    "windows_wsl_setup_acknowledged",
    "timeout",
    "max_retries",
    "max_output_tokens",
    "use_system_proxy",
    "proxy_url",
    "mock_mode",
}

AGENT_MODEL_KEYS = {"planner", "writer", "reviewer", "reviser", "memory"}


def sanitize_config_update(current: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    unknown = sorted(set(body) - ALLOWED_CONFIG_KEYS)
    if unknown:
        raise ValueError("配置包含不支持的字段：" + "、".join(unknown))

    config = dict(current)
    for key in ALLOWED_CONFIG_KEYS:
        if key in body:
            config[key] = body[key]

    config["provider"] = _text(config.get("provider"), "OpenAI")
    config["model_provider"] = _text(config.get("model_provider"), config["provider"])
    config["base_url"] = _text(config.get("base_url"))
    config["wire_api"] = _choice(config.get("wire_api"), {"responses", "chat_completions"}, "chat_completions")
    config["requires_openai_auth"] = _bool(config.get("requires_openai_auth", True), "requires_openai_auth")
    config["api_key"] = _text(config.get("api_key"))
    config["default_model"] = _text(config.get("default_model"))
    config["review_model"] = _text(config.get("review_model"))
    config["agent_models"] = _agent_models(config.get("agent_models"))
    config["temperature"] = _number(config.get("temperature"), "temperature", 0.0, 2.0, 0.8)
    config["model_reasoning_effort"] = _text(config.get("model_reasoning_effort"))
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
    config["use_system_proxy"] = _bool(config.get("use_system_proxy", False), "use_system_proxy")
    config["proxy_url"] = _text(config.get("proxy_url"))
    config["mock_mode"] = _bool(config.get("mock_mode", True), "mock_mode")
    return config


def public_config(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "provider": config.get("provider", ""),
        "model_provider": config.get("model_provider", ""),
        "base_url": config.get("base_url", ""),
        "wire_api": config.get("wire_api", ""),
        "requires_openai_auth": bool(config.get("requires_openai_auth", True)),
        "api_key": config.get("api_key", ""),
        "default_model": config.get("default_model", ""),
        "review_model": config.get("review_model", ""),
        "agent_models": config.get("agent_models", {}),
        "temperature": float(config.get("temperature", 0.8) or 0.8),
        "model_reasoning_effort": config.get("model_reasoning_effort", ""),
        "disable_response_storage": bool(config.get("disable_response_storage", True)),
        "model_context_window": int(config.get("model_context_window", 1000000) or 1000000),
        "model_auto_compact_token_limit": int(config.get("model_auto_compact_token_limit", 900000) or 900000),
        "network_access": config.get("network_access", "enabled"),
        "windows_wsl_setup_acknowledged": bool(config.get("windows_wsl_setup_acknowledged", True)),
        "mock_mode": bool(config.get("mock_mode", True)),
        "timeout": int(config.get("timeout", 300) or 300),
        "max_retries": int(config.get("max_retries", 2) or 0),
        "max_output_tokens": int(config.get("max_output_tokens", 12000) or 12000),
        "use_system_proxy": bool(config.get("use_system_proxy", False)),
        "proxy_url": config.get("proxy_url", ""),
    }


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
