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
    "base_url": "https://api.openai.com/v1",
    "wire_api": "chat_completions",
    "requires_openai_auth": True,
    "api_key": "",
    "default_model": "gpt-4o-mini",
    "review_model": "",
    "model_reasoning_effort": "",
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
    },
    "temperature": 0.8,
    "timeout": 300,
    "max_retries": 2,
    "max_output_tokens": 12000,
    "use_system_proxy": False,
    "proxy_url": "",
    "mock_mode": True,
}


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
        save_config(config, path)
        return config

    with path.open("r", encoding="utf-8") as f:
        loaded = json.load(f)

    config = deepcopy(DEFAULT_CONFIG)
    config.update(loaded)
    config["agent_models"] = {
        **DEFAULT_CONFIG["agent_models"],
        **loaded.get("agent_models", {}),
    }
    return config


def save_config(config: dict[str, Any], path: Path = CONFIG_PATH) -> None:
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
