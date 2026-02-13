from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _load_api_key_from_file(path_value: str, key_names: tuple[str, ...]) -> str:
    path = Path(path_value).expanduser()
    if not path.exists() or not path.is_file():
        return ""

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return ""

    for key_name in key_names:
        value = data.get(key_name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _read_json_file(path: Path) -> dict:
    try:
        content = path.read_text(encoding="utf-8")
        data = json.loads(content)
        if isinstance(data, dict):
            return data
    except Exception:
        return {}
    return {}


def _resolve_existing_file(path_value: str) -> Path | None:
    raw = (path_value or "").strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    if path.exists() and path.is_file():
        return path.resolve()
    return None


def _is_google_service_account(path: Path) -> bool:
    data = _read_json_file(path)
    return str(data.get("type", "")).strip().lower() == "service_account"


def _extract_project_id(path: Path) -> str:
    data = _read_json_file(path)
    return str(data.get("project_id", "")).strip()


def _discover_google_credentials_file() -> Path | None:
    cwd = Path.cwd()
    candidates = []
    patterns = ("ipssi-*.json", "*service-account*.json", "*credentials*.json")
    for pattern in patterns:
        candidates.extend(cwd.glob(pattern))

    unique_candidates = []
    seen = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except Exception:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        unique_candidates.append(resolved)

    for candidate in unique_candidates:
        if candidate.exists() and candidate.is_file() and _is_google_service_account(candidate):
            return candidate
    return None


@dataclass(frozen=True)
class Settings:
    llm_provider: str
    llm_model: str

    openai_api_key: str
    openai_model: str

    anthropic_api_key: str
    anthropic_model: str

    google_api_key: str
    google_model: str

    google_application_credentials: str
    vertex_project_id: str
    vertex_location: str
    vertex_model: str

    app_host: str
    app_port: int
    max_history_messages: int

    @property
    def llm_enabled(self) -> bool:
        return self.llm_provider in {"openai", "anthropic", "gemini", "vertex"}


def get_settings() -> Settings:
    provider_pref = os.getenv("LLM_PROVIDER", "auto").strip().lower()

    # OpenAI API Key
    env_key = os.getenv("OPENAI_API_KEY", "").strip()
    key_file = os.getenv("OPENAI_API_KEY_FILE", "").strip()
    file_key = (    
        _load_api_key_from_file(key_file, ("openai_api_key", "OPENAI_API_KEY", "api_key"))
        if key_file
        else ""
    )
    openai_api_key = env_key or file_key

    # Anthropic API Key
    anthropic_api_key_env = os.getenv("ANTHROPIC_API_KEY", "").strip()
    anthropic_api_key_file = os.getenv("ANTHROPIC_API_KEY_FILE", "").strip()
    anthropic_api_key_from_file = (
        _load_api_key_from_file(
            anthropic_api_key_file,
            ("anthropic_api_key", "ANTHROPIC_API_KEY", "api_key"),
        )
        if anthropic_api_key_file
        else ""
    )
    anthropic_api_key = anthropic_api_key_env or anthropic_api_key_from_file

    # Google API Key
    google_api_key_env = os.getenv("GOOGLE_API_KEY", "").strip()
    google_api_key_file = os.getenv("GOOGLE_API_KEY_FILE", "").strip()
    google_api_key_from_file = (
        _load_api_key_from_file(
            google_api_key_file,
            ("google_api_key", "GOOGLE_API_KEY", "gemini_api_key", "api_key"),
        )
        if google_api_key_file
        else ""
    )
    google_api_key = google_api_key_env or google_api_key_from_file

    google_path_env = (
        os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
        or os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
    )
    google_path = _resolve_existing_file(google_path_env) if google_path_env else None
    if google_path is None:
        google_path = _discover_google_credentials_file()

    google_credentials = str(google_path) if google_path else ""

    vertex_project_id = os.getenv("VERTEX_PROJECT_ID", "").strip()
    if not vertex_project_id and google_path is not None:
        vertex_project_id = _extract_project_id(google_path)

    vertex_location = os.getenv("VERTEX_LOCATION", "us-central1").strip()
    openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
    anthropic_model = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022").strip()
    google_model = os.getenv("GOOGLE_MODEL", "gemini-1.5-flash").strip()
    vertex_model = os.getenv("VERTEX_MODEL", "gemini-1.5-flash-002").strip()

    # Determine provider based on preference or available keys
    if provider_pref == "openai":
        llm_provider = "openai" if openai_api_key else "none"
    elif provider_pref == "anthropic":
        llm_provider = "anthropic" if anthropic_api_key else "none"
    elif provider_pref == "gemini":
        llm_provider = "gemini" if google_api_key else "none"
    elif provider_pref == "vertex":
        llm_provider = "vertex" if google_credentials else "none"
    elif provider_pref == "none":
        llm_provider = "none"
    else:
        # Auto-detection: prefer in order - gemini, anthropic, vertex, openai
        if google_api_key:
            llm_provider = "gemini"
        elif anthropic_api_key:
            llm_provider = "anthropic"
        elif google_credentials:
            llm_provider = "vertex"
        elif openai_api_key:
            llm_provider = "openai"
        else:
            llm_provider = "none"

    # Set model based on provider
    if llm_provider == "openai":
        llm_model = openai_model
    elif llm_provider == "anthropic":
        llm_model = anthropic_model
    elif llm_provider == "gemini":
        llm_model = google_model
    elif llm_provider == "vertex":
        llm_model = vertex_model
    else:
        llm_model = "heuristic-only"

    return Settings(
        llm_provider=llm_provider,
        llm_model=llm_model,
        openai_api_key=openai_api_key,
        openai_model=openai_model,
        anthropic_api_key=anthropic_api_key,
        anthropic_model=anthropic_model,
        google_api_key=google_api_key,
        google_model=google_model,
        google_application_credentials=google_credentials,
        vertex_project_id=vertex_project_id,
        vertex_location=vertex_location,
        vertex_model=vertex_model,
        app_host=os.getenv("APP_HOST", "127.0.0.1").strip(),
        app_port=int(os.getenv("APP_PORT", "8000").strip()),
        max_history_messages=int(os.getenv("MAX_HISTORY_MESSAGES", "40").strip()),
    )