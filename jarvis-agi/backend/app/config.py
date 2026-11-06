import os
from dataclasses import dataclass
from pathlib import Path


def _enabled(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    pairing_code: str
    token_secret: str
    data_dir: Path
    local_ollama_enabled: bool
    local_ollama_base_url: str
    local_ollama_model: str
    cloud_fallback_enabled: bool
    deepseek_api_key: str
    deepseek_base_url: str
    deepseek_model: str
    gateway_discovery_enabled: bool
    gateway_discovery_name: str
    gateway_discovery_url: str
    gateway_discovery_address: str


def settings() -> Settings:
    data_dir = Path(os.getenv("DATA_DIR", "./data")).expanduser().resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    return Settings(
        pairing_code=os.getenv("PAIRING_CODE", "development-pairing-code"),
        token_secret=os.getenv("TOKEN_SECRET", "development-token-secret-change-me"),
        data_dir=data_dir,
        local_ollama_enabled=_enabled("LOCAL_OLLAMA_ENABLED", True),
        local_ollama_base_url=os.getenv("LOCAL_OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1").rstrip("/"),
        local_ollama_model=os.getenv("LOCAL_OLLAMA_MODEL", "deepseek-r1:7b"),
        cloud_fallback_enabled=_enabled("CLOUD_FALLBACK_ENABLED", False),
        deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", ""),
        deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/"),
        deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-reasoner"),
        gateway_discovery_enabled=_enabled("GATEWAY_DISCOVERY_ENABLED", False),
        gateway_discovery_name=os.getenv("GATEWAY_DISCOVERY_NAME", "WhiteRabbit Gateway").strip(),
        gateway_discovery_url=os.getenv("GATEWAY_DISCOVERY_URL", "").strip().rstrip("/"),
        gateway_discovery_address=os.getenv("GATEWAY_DISCOVERY_ADDRESS", "").strip(),
    )
