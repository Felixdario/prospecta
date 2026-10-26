"""Validação das entradas da API (Pydantic)."""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .messages import VARIANTS
from .pipeline import CHANNELS, MANUAL_EVENT_TYPES, STATUSES

VariantName = Literal[tuple(VARIANTS)]  # type: ignore[valid-type]
StatusName = Literal[tuple(STATUSES)]  # type: ignore[valid-type]
ManualEvent = Literal[MANUAL_EVENT_TYPES]  # type: ignore[valid-type]
Channel = Literal[CHANNELS]  # type: ignore[valid-type]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class FiltersIn(Strict):
    website: Literal["todos", "sem_site", "sem_site_proprio", "com_site"] = "todos"
    min_rating: Optional[float] = Field(None, ge=0, le=5)
    min_reviews: Optional[int] = Field(None, ge=0, le=100000)
    max_reviews: Optional[int] = Field(None, ge=0, le=1000000)
    require_phone: bool = True
    only_mobile: bool = False


class SearchIn(Strict):
    segment: str = Field(min_length=2, max_length=80)
    city: str = Field(min_length=2, max_length=80)
    state: Optional[str] = Field(None, max_length=30)
    regions: list[str] = Field(default_factory=list, max_length=10)
    max_results: int = Field(40, ge=1, le=300)
    filters: FiltersIn = Field(default_factory=FiltersIn)
    use_ai: bool = False

    @field_validator("regions")
    @classmethod
    def _regions(cls, v: list[str]) -> list[str]:
        out = [r.strip() for r in v if r and r.strip()]
        if any(len(r) > 60 for r in out):
            raise ValueError("Cada bairro/região deve ter no máximo 60 caracteres")
        return out


class LeadPatch(Strict):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    category: Optional[str] = Field(None, max_length=120)
    segment: Optional[str] = Field(None, max_length=40)
    address: Optional[str] = Field(None, max_length=300)
    neighborhood: Optional[str] = Field(None, max_length=120)
    city: Optional[str] = Field(None, max_length=120)
    state: Optional[str] = Field(None, max_length=40)
    phone: Optional[str] = Field(None, max_length=40)
    website: Optional[str] = Field(None, max_length=300)
    notes: Optional[str] = Field(None, max_length=5000)
    responsible_name: Optional[str] = Field(None, max_length=120)
    preview_ready: Optional[bool] = None
    preview_url: Optional[str] = Field(None, max_length=300)
    suggested_message: Optional[str] = Field(None, max_length=2000)


class ManualLeadIn(Strict):
    name: str = Field(min_length=1, max_length=200)
    phone: Optional[str] = Field(None, max_length=40)
    website: Optional[str] = Field(None, max_length=300)
    category: Optional[str] = Field(None, max_length=120)
    address: Optional[str] = Field(None, max_length=300)
    neighborhood: Optional[str] = Field(None, max_length=120)
    city: Optional[str] = Field(None, max_length=120)
    state: Optional[str] = Field(None, max_length=40)
    notes: Optional[str] = Field(None, max_length=5000)


class AnalyzeIn(Strict):
    use_ai: bool = False
    refresh_site: bool = False


class MessageIn(Strict):
    variant: Optional[VariantName] = None
    use_ai: bool = False


class StatusIn(Strict):
    status: StatusName
    note: Optional[str] = Field(None, max_length=500)


class InteractionIn(Strict):
    type: ManualEvent
    channel: Optional[Channel] = None
    summary: Optional[str] = Field(None, max_length=1000)
    message_text: Optional[str] = Field(None, max_length=2000)
    override_reason: Optional[str] = Field(None, max_length=300)


class ConsentIn(Strict):
    status: Literal["nao_registrado", "opt_in", "opt_out"]
    note: str = Field("", max_length=500)


class TaskIn(Strict):
    title: str = Field(min_length=2, max_length=200)
    due_date: date


class TaskPatch(Strict):
    done: bool


class SuppressionIn(Strict):
    kind: Literal["phone", "place_id", "domain"]
    value: str = Field(min_length=3, max_length=200)
    reason: str = Field("", max_length=300)


class SellerIn(Strict):
    nome: str = Field(min_length=2, max_length=80)
    primeiro_nome: str = Field(min_length=2, max_length=40)
    experiencia: str = Field("", max_length=60)
    empresa: str = Field("", max_length=80)


class ContactPolicyIn(Strict):
    daily_limit: int = Field(ge=1, le=200)
    min_days_between_contacts: int = Field(ge=1, le=60)
    max_unanswered_attempts: int = Field(ge=1, le=5)
    business_hours: list[int] = Field(min_length=2, max_length=2)
    business_days: list[int] = Field(min_length=1, max_length=7)

    @model_validator(mode="after")
    def _check(self):
        start, end = self.business_hours
        if not (0 <= start < end <= 24):
            raise ValueError("Horário comercial inválido")
        if any(d < 0 or d > 6 for d in self.business_days):
            raise ValueError("Dias da semana vão de 0 (segunda) a 6 (domingo)")
        return self


class PipelineIn(Strict):
    auto_message_min_priority: Literal["alta", "media", "baixa", "nenhuma"] = "alta"
    analyze_sites: bool = True


class SettingsIn(Strict):
    seller: Optional[SellerIn] = None
    contact_policy: Optional[ContactPolicyIn] = None
    pipeline: Optional[PipelineIn] = None
    scoring: Optional[dict] = None


class MaintenanceIn(Strict):
    mode: Literal["report", "purge", "refresh"] = "report"


def validate_scoring(cfg: dict) -> dict:
    """Valida a configuração de pontuação mesclada com o padrão."""
    from .scoring import DEFAULT_SCORING, merge_config

    merged = merge_config(DEFAULT_SCORING, cfg)
    th = merged["thresholds"]
    if not (0 < th["media"] < th["alta"] <= 100):
        raise ValueError("Limites inválidos: é preciso 0 < média < alta ≤ 100")

    def walk(value, path=""):
        if isinstance(value, dict):
            for k, v in value.items():
                walk(v, f"{path}.{k}" if path else k)
        elif isinstance(value, list):
            for i, v in enumerate(value):
                walk(v, f"{path}[{i}]")
        elif isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"Valor não numérico em {path}")
        elif not -100 <= value <= 100000:
            raise ValueError(f"Valor fora do intervalo em {path}")

    walk(merged)
    return cfg
