"""Configuração de infraestrutura e segredos (lidos do arquivo .env / variáveis de ambiente).

Preferências de negócio (perfil do vendedor, pesos da pontuação, política de contato) ficam
no banco, na tabela `settings`, e podem ser editadas pela interface. Veja app/settings_store.py.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

try:  # python-dotenv é opcional em tempo de teste
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env", override=False)
except ImportError:  # pragma: no cover
    pass


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        raise SystemExit(f"Variável {name} precisa ser um número inteiro (valor atual: {raw!r}).")


def _str(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass
class Config:
    database_path: Path = field(default_factory=lambda: PROJECT_ROOT / _str("DATABASE_PATH", "data/prospecta.db"))
    admin_token: str = field(default_factory=lambda: _str("ADMIN_TOKEN"))
    host: str = field(default_factory=lambda: _str("HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: _int("PORT", 8000))
    timezone: str = field(default_factory=lambda: _str("APP_TIMEZONE", "America/Sao_Paulo"))

    # Google Places API (New)
    google_api_key: str = field(default_factory=lambda: _str("GOOGLE_PLACES_API_KEY"))
    google_textsearch_monthly_limit: int = field(default_factory=lambda: _int("GOOGLE_TEXTSEARCH_MONTHLY_LIMIT", 900))
    google_details_monthly_limit: int = field(default_factory=lambda: _int("GOOGLE_DETAILS_MONTHLY_LIMIT", 900))
    google_cache_days: int = field(default_factory=lambda: _int("GOOGLE_CACHE_DAYS", 30))

    # IA opcional (API do Claude). Sem chave, o sistema usa regras e modelos de mensagem.
    anthropic_api_key: str = field(default_factory=lambda: _str("ANTHROPIC_API_KEY"))
    ai_model: str = field(default_factory=lambda: _str("AI_MODEL", "claude-haiku-5-5"))

    # Análise de sites
    site_user_agent: str = field(
        default_factory=lambda: _str(
            "SITE_ANALYSIS_USER_AGENT",
            "ProspectaBot/1.0 (analise de presenca digital; visita unica a pagina inicial)",
        )
    )
    site_timeout_seconds: int = field(default_factory=lambda: _int("SITE_TIMEOUT_SECONDS", 10))

    # Limite simples de requisições por token (por minuto)
    api_rate_limit_per_minute: int = field(default_factory=lambda: _int("API_RATE_LIMIT_PER_MINUTE", 240))

    @property
    def has_google(self) -> bool:
        return bool(self.google_api_key)

    @property
    def has_ai(self) -> bool:
        return bool(self.anthropic_api_key)


def load_config() -> Config:
    return Config()
