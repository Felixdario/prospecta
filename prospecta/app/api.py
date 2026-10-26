"""API REST (Starlette). Todas as rotas /api exigem token Bearer, exceto /api/health."""
from __future__ import annotations

import csv
import hmac
import io
import logging
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any, Callable

from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .messages import VARIANTS
from .pipeline import CHANNELS, EVENT_TYPES, MANUAL_EVENT_TYPES, PRIORITIES, STATUSES
from .repository import NotFound
from .schemas import (AnalyzeIn, ConsentIn, InteractionIn, LeadPatch, MaintenanceIn, ManualLeadIn, MessageIn, SearchIn,
                      SettingsIn, StatusIn, SuppressionIn, TaskIn, TaskPatch, validate_scoring)
from .segments import all_segments, detect_segment
from .services import BusinessError, ContactBlocked, Services, today_local
from .site_analysis import KIND_LABELS
from .sources.places import PlacesError, QuotaExceeded

log = logging.getLogger("prospecta.api")
ADMIN = "admin"


@dataclass
class Principal:
    name: str
    scopes: set[str]

    @property
    def is_admin(self) -> bool:
        return ADMIN in self.scopes

    def has(self, scope: str) -> bool:
        return self.is_admin or scope in self.scopes


@dataclass
class Ctx:
    request: Request
    principal: Principal
    body: Any
    svc: Services

    @property
    def actor(self) -> str:
        return "usuario" if self.principal.name == ADMIN else f"token:{self.principal.name}"

    def path_int(self, name: str) -> int:
        return int(self.request.path_params[name])

    @property
    def query(self):
        return self.request.query_params


class ApiError(Exception):
    def __init__(self, status: int, message: str, extra: dict | None = None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.extra = extra or {}


class RateLimiter:
    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self.hits: dict[str, deque] = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self.lock:
            q = self.hits[key]
            while q and now - q[0] > 60:
                q.popleft()
            if len(q) >= self.per_minute:
                return False
            q.append(now)
            return True


def _authenticate(request: Request, svc: Services) -> Principal:
    header = request.headers.get("authorization", "")
    token = header[7:].strip() if header.lower().startswith("bearer ") else ""
    if not token:
        raise ApiError(401, "Informe o token de acesso (cabeçalho Authorization: Bearer <token>).")
    admin = svc.config.admin_token
    if admin and hmac.compare_digest(token, admin):
        return Principal(ADMIN, {ADMIN})
    info = svc.repo.verify_token(token)
    if not info:
        raise ApiError(401, "Token inválido ou revogado.")
    return Principal(info["name"], info["scopes"])


def endpoint(scope: str, handler: Callable[[Ctx], Any], audit_reads: bool = False) -> Callable:
    async def view(request: Request) -> Response:
        svc: Services = request.app.state.services
        limiter: RateLimiter = request.app.state.limiter
        principal: Principal | None = None
        status = 500
        try:
            principal = await run_in_threadpool(_authenticate, request, svc)
            if not principal.has(scope):
                raise ApiError(403, f"Este token não tem a permissão '{scope}'.")
            if not limiter.allow(principal.name):
                raise ApiError(429, "Muitas requisições. Aguarde um minuto.")
            body = None
            if request.method in ("POST", "PUT", "PATCH") and "application/json" in request.headers.get("content-type", ""):
                try:
                    body = await request.json()
                except ValueError:
                    raise ApiError(400, "JSON inválido no corpo da requisição.")
            elif request.method == "POST" and "multipart/form-data" in request.headers.get("content-type", ""):
                form = await request.form()
                try:
                    upload = form.get("file")
                    body = {"file": await upload.read() if upload is not None and hasattr(upload, "read") else None}
                finally:
                    await form.close()
            result = await run_in_threadpool(handler, Ctx(request, principal, body, svc))
            response = result if isinstance(result, Response) else JSONResponse(result)
            status = response.status_code
            return response
        except ApiError as e:
            status = e.status
            return JSONResponse({"erro": e.message, **e.extra}, status_code=e.status)
        except ValidationError as e:
            status = 422
            details = [{"campo": ".".join(str(x) for x in err["loc"]), "motivo": err["msg"]} for err in e.errors()]
            return JSONResponse({"erro": "Dados inválidos", "detalhes": details}, status_code=422)
        except NotFound as e:
            status = 404
            return JSONResponse({"erro": str(e)}, status_code=404)
        except ContactBlocked as e:
            status = 409
            return JSONResponse({"erro": "Contato bloqueado pela política de contato", "bloqueios": e.blockers}, status_code=409)
        except BusinessError as e:
            status = e.status_code
            return JSONResponse({"erro": str(e)}, status_code=e.status_code)
        except QuotaExceeded as e:
            status = 429
            return JSONResponse({"erro": str(e)}, status_code=429)
        except PlacesError as e:
            status = 502
            return JSONResponse({"erro": str(e)}, status_code=502)
        except ValueError as e:
            status = 400
            return JSONResponse({"erro": str(e)}, status_code=400)
        except Exception:
            log.exception("Erro inesperado em %s %s", request.method, request.url.path)
            return JSONResponse({"erro": "Erro interno. Veja o log do servidor."}, status_code=500)
        finally:
            if principal is not None and (request.method != "GET" or audit_reads or not principal.is_admin):
                try:
                    await run_in_threadpool(svc.repo.audit, principal.name, request.method, request.url.path, status,
                                            str(request.query_params)[:300] or None)
                except Exception:
                    log.exception("Falha ao gravar auditoria")

    return view


# ---------------------------------------------------------------------------------------- handlers
def health(request: Request) -> JSONResponse:
    cfg = request.app.state.services.config
    return JSONResponse({"ok": True, "google_configurado": cfg.has_google, "ia_configurada": cfg.has_ai})


def meta(ctx: Ctx):
    cfg = ctx.svc.config
    return {
        "statuses": STATUSES, "priorities": PRIORITIES, "variants": VARIANTS, "event_types": EVENT_TYPES,
        "manual_event_types": list(MANUAL_EVENT_TYPES), "channels": list(CHANNELS), "segments": all_segments(),
        "presence_kinds": KIND_LABELS,
        "google_configurado": cfg.has_google, "ia_configurada": cfg.has_ai, "modelo_ia": cfg.ai_model if cfg.has_ai else None,
        "uso_google_mes": ctx.svc.repo.usage(),
        "limites_google": {"text_search_enterprise": cfg.google_textsearch_monthly_limit, "place_details_enterprise": cfg.google_details_monthly_limit},
        "cache_google_dias": cfg.google_cache_days,
        "voce": {"nome": ctx.principal.name, "escopos": sorted(ctx.principal.scopes)},
    }


def stats(ctx: Ctx):
    s = ctx.svc.repo.stats()
    s["tarefas_hoje"] = len(ctx.svc.repo.list_tasks(scope="today", today=today_local(ctx.svc.config.timezone)))
    s["contatos_hoje"] = ctx.svc.repo.sent_today(ctx.svc.config.timezone)
    s["limite_diario"] = ctx.svc.repo.settings()["contact_policy"]["daily_limit"]
    return s


def create_search(ctx: Ctx):
    data = SearchIn.model_validate(ctx.body or {})
    if not ctx.svc.config.has_google and ctx.svc._places_factory is None:
        raise ApiError(400, "Configure GOOGLE_PLACES_API_KEY no arquivo .env para pesquisar no Google. Enquanto isso, use a importação de planilha.")
    params = {"kind": "pesquisa", **data.model_dump()}
    job_id = ctx.svc.repo.create_job(params, ctx.actor)
    return JSONResponse(ctx.svc.repo.get_job(job_id), status_code=202)


def list_searches(ctx: Ctx):
    return {"items": ctx.svc.repo.list_jobs(int(ctx.query.get("limit", 20)))}


def get_search(ctx: Ctx):
    return ctx.svc.repo.get_job(ctx.path_int("job_id"))


def cancel_search(ctx: Ctx):
    job = ctx.svc.repo.get_job(ctx.path_int("job_id"))
    if job["status"] not in ("na_fila", "executando"):
        raise ApiError(400, "A pesquisa já terminou.")
    if job["status"] == "na_fila":
        ctx.svc.repo.update_job(job["id"], status="cancelada", stage="Cancelada antes de iniciar", cancel_requested=1)
    else:
        ctx.svc.repo.update_job(job["id"], cancel_requested=1)
    return ctx.svc.repo.get_job(job["id"])


LIST_FILTERS = ("q", "status", "priority", "segment", "source", "presence", "city", "min_score", "has_phone", "search_id", "sort", "page", "page_size")


def list_leads(ctx: Ctx):
    f = {k: ctx.query.get(k) for k in LIST_FILTERS if ctx.query.get(k) not in (None, "")}
    items, total = ctx.svc.repo.list_leads(f)
    return {"items": items, "total": total, "page": int(f.get("page") or 1), "page_size": int(f.get("page_size") or 50)}


def create_lead(ctx: Ctx):
    data = ManualLeadIn.model_validate(ctx.body or {})
    payload = data.model_dump(exclude={"notes"})
    payload["segment"] = detect_segment(data.category, data.name).key
    if ctx.svc.repo.suppression_matches({"website": data.website, "phone_e164": None, "place_id": None}):
        raise ApiError(409, "Empresa na lista de supressão.")
    lead_id, is_new = ctx.svc.repo.upsert_lead(payload, "manual", ctx.actor, website_known=True)
    if data.notes:
        ctx.svc.repo.update_lead(lead_id, {"notes": data.notes})
    ctx.svc.analyze(lead_id, ctx.actor)
    return JSONResponse({"id": lead_id, "novo": is_new, **ctx.svc.lead_detail(lead_id)}, status_code=201 if is_new else 200)


def get_lead(ctx: Ctx):
    return ctx.svc.lead_detail(ctx.path_int("lead_id"))


def patch_lead(ctx: Ctx):
    data = LeadPatch.model_validate(ctx.body or {})
    fields = data.model_dump(exclude_unset=True)
    lead_id = ctx.path_int("lead_id")
    ctx.svc.repo.update_lead(lead_id, fields)
    if fields:
        changed = ", ".join(sorted(fields))
        ctx.svc.repo.add_event(lead_id, ctx.actor, "nota", f"Dados editados: {changed}")
    if {"website", "phone", "segment"} & set(fields):
        ctx.svc.analyze(lead_id, ctx.actor)
    return ctx.svc.lead_detail(lead_id)


def delete_lead(ctx: Ctx):
    lead_id = ctx.path_int("lead_id")
    suppress = ctx.query.get("suppress") in ("1", "true", "sim")
    lead = ctx.svc.repo.get_lead(lead_id)
    if suppress:
        ctx.svc.repo.suppress_lead(lead, "Excluído a pedido, não contatar", ctx.actor)
    ctx.svc.repo.delete_lead(lead_id)
    return {"excluido": lead_id, "suprimido": suppress}


def analyze_lead(ctx: Ctx):
    data = AnalyzeIn.model_validate(ctx.body or {})
    lead_id = ctx.path_int("lead_id")
    ctx.svc.analyze(lead_id, ctx.actor, use_ai=data.use_ai, refresh_site=data.refresh_site)
    return ctx.svc.lead_detail(lead_id)


def score_lead_view(ctx: Ctx):
    lead_id = ctx.path_int("lead_id")
    ctx.svc.analyze(lead_id, ctx.actor)
    lead = ctx.svc.repo.get_lead(lead_id)
    return {"id": lead_id, "score": lead["score"], "priority": lead["priority"], "breakdown": lead["score_breakdown"]}


def generate_message(ctx: Ctx):
    data = MessageIn.model_validate(ctx.body or {})
    lead_id = ctx.path_int("lead_id")
    result = ctx.svc.generate_message(lead_id, ctx.actor, data.variant, data.use_ai)
    return {**result, **ctx.svc.lead_detail(lead_id)}


def change_status(ctx: Ctx):
    data = StatusIn.model_validate(ctx.body or {})
    lead_id = ctx.path_int("lead_id")
    ctx.svc.change_status(lead_id, data.status, ctx.actor, data.note, ctx.principal.is_admin)
    return ctx.svc.lead_detail(lead_id)


def contact_check_view(ctx: Ctx):
    return ctx.svc.check_contact(ctx.path_int("lead_id"))


def add_interaction(ctx: Ctx):
    data = InteractionIn.model_validate(ctx.body or {})
    if data.type == "mensagem_enviada" and not ctx.principal.has("contacts:record"):
        raise ApiError(403, "Registrar envio de mensagem exige a permissão 'contacts:record' (envio é feito por uma pessoa).")
    lead_id = ctx.path_int("lead_id")
    ctx.svc.record_interaction(lead_id, data.type, ctx.actor, data.summary, data.channel, data.override_reason,
                               ctx.principal.is_admin, data.message_text)
    return ctx.svc.lead_detail(lead_id)


def set_consent(ctx: Ctx):
    data = ConsentIn.model_validate(ctx.body or {})
    lead_id = ctx.path_int("lead_id")
    ctx.svc.set_consent(lead_id, data.status, data.note, ctx.actor)
    return ctx.svc.lead_detail(lead_id)


def refresh_lead(ctx: Ctx):
    lead_id = ctx.path_int("lead_id")
    ctx.svc.refresh_from_google(lead_id, ctx.actor)
    return ctx.svc.lead_detail(lead_id)


def create_task(ctx: Ctx):
    data = TaskIn.model_validate(ctx.body or {})
    task_id = ctx.svc.repo.create_task(ctx.path_int("lead_id"), data.title, data.due_date.isoformat(), ctx.actor)
    return JSONResponse({"id": task_id}, status_code=201)


def list_tasks(ctx: Ctx):
    scope = ctx.query.get("scope", "open")
    if scope not in ("open", "today", "overdue", "all"):
        raise ApiError(400, "scope deve ser open, today, overdue ou all")
    return {"items": ctx.svc.repo.list_tasks(scope=scope, today=today_local(ctx.svc.config.timezone))}


def patch_task(ctx: Ctx):
    data = TaskPatch.model_validate(ctx.body or {})
    return ctx.svc.repo.set_task_done(ctx.path_int("task_id"), data.done, ctx.actor)


EXPORT_COLUMNS = [
    ("id", "id"), ("empresa", "name"), ("categoria", "category"), ("segmento", "segment"), ("endereco", "address"),
    ("bairro", "neighborhood"), ("cidade", "city"), ("uf", "state"), ("telefone", "phone"), ("tipo_telefone", "phone_kind"),
    ("site", "website"), ("presenca_digital", "presence_kind"), ("link_google_maps", "maps_url"), ("nota", "rating"),
    ("avaliacoes", "reviews_count"), ("pontuacao", "score"), ("prioridade", "priority"), ("justificativa", None),
    ("status", "status"), ("consentimento", "consent_status"), ("ultimo_contato", "last_contact_at"),
    ("qtd_contatos", "contact_count"), ("mensagem_sugerida", "suggested_message"), ("responsavel", "responsible_name"),
    ("observacoes", "notes"), ("origem", "source"), ("coletado_em", "created_at"), ("dados_google_em", "google_fetched_at"),
]


def export_csv(ctx: Ctx):
    f = {k: ctx.query.get(k) for k in LIST_FILTERS if ctx.query.get(k) not in (None, "")}
    leads = ctx.svc.repo.iter_leads_for_export(f)
    sep = "," if ctx.query.get("sep") == "comma" else ";"
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=sep)
    writer.writerow([c for c, _ in EXPORT_COLUMNS])
    for lead in leads:
        row = []
        for _, key in EXPORT_COLUMNS:
            if key is None:
                row.append((lead.get("score_breakdown") or {}).get("summary", ""))
            elif key == "status":
                row.append(STATUSES.get(lead["status"], lead["status"]))
            elif key == "rating" and lead.get("rating") is not None:
                row.append(str(lead["rating"]).replace(".", ",") if sep == ";" else lead["rating"])
            else:
                v = lead.get(key)
                row.append("" if v is None else v)
        writer.writerow(row)
    content = "﻿" + buf.getvalue()
    return Response(content.encode("utf-8"), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="leads-{today_local(ctx.svc.config.timezone)}.csv"'})


def import_csv(ctx: Ctx):
    raw = (ctx.body or {}).get("file")
    if not raw:
        raise ApiError(400, "Envie o arquivo CSV no campo 'file' (multipart/form-data).")
    if len(raw) > 10_000_000:
        raise ApiError(413, "Arquivo maior que 10 MB.")
    return ctx.svc.import_csv(raw, ctx.actor)


def list_suppression(ctx: Ctx):
    return {"items": ctx.svc.repo.list_suppression()}


def add_suppression(ctx: Ctx):
    data = SuppressionIn.model_validate(ctx.body or {})
    ctx.svc.repo.add_suppression(data.kind, data.value, data.reason, ctx.actor)
    return JSONResponse({"ok": True}, status_code=201)


def remove_suppression(ctx: Ctx):
    ctx.svc.repo.remove_suppression(ctx.path_int("sup_id"))
    return {"ok": True}


def get_settings(ctx: Ctx):
    from .scoring import DEFAULT_SCORING, merge_config

    s = ctx.svc.repo.settings()
    s["scoring_efetivo"] = merge_config(DEFAULT_SCORING, s["scoring"])
    return s


def put_settings(ctx: Ctx):
    data = SettingsIn.model_validate(ctx.body or {})
    for key in ("seller", "contact_policy", "pipeline"):
        value = getattr(data, key)
        if value is not None:
            ctx.svc.repo.save_setting(key, value.model_dump())
    if data.scoring is not None:
        ctx.svc.repo.save_setting("scoring", validate_scoring(data.scoring))
        ctx.svc.rescore_all(ctx.actor)
    return get_settings(ctx)


def audit_log(ctx: Ctx):
    return {"items": ctx.svc.repo.audit_entries(int(ctx.query.get("limit", 200)))}


def google_cache(ctx: Ctx):
    data = MaintenanceIn.model_validate(ctx.body or {})
    return ctx.svc.google_cache_maintenance(data.mode, ctx.actor)


def list_tokens(ctx: Ctx):
    return {"items": ctx.svc.repo.list_tokens()}


def routes() -> list[Route]:
    E = endpoint
    return [
        Route("/api/health", health, methods=["GET"]),
        Route("/api/meta", E("leads:read", meta), methods=["GET"]),
        Route("/api/stats", E("leads:read", stats), methods=["GET"]),
        Route("/api/searches", E("search:run", create_search), methods=["POST"]),
        Route("/api/searches", E("leads:read", list_searches), methods=["GET"]),
        Route("/api/searches/{job_id:int}", E("leads:read", get_search), methods=["GET"]),
        Route("/api/searches/{job_id:int}/cancel", E("search:run", cancel_search), methods=["POST"]),
        Route("/api/leads", E("leads:read", list_leads), methods=["GET"]),
        Route("/api/leads", E("leads:write", create_lead), methods=["POST"]),
        Route("/api/leads/{lead_id:int}", E("leads:read", get_lead), methods=["GET"]),
        Route("/api/leads/{lead_id:int}", E("leads:write", patch_lead), methods=["PATCH"]),
        Route("/api/leads/{lead_id:int}", E(ADMIN, delete_lead), methods=["DELETE"]),
        Route("/api/leads/{lead_id:int}/analyze", E("leads:write", analyze_lead), methods=["POST"]),
        Route("/api/leads/{lead_id:int}/score", E("leads:write", score_lead_view), methods=["POST"]),
        Route("/api/leads/{lead_id:int}/message", E("leads:write", generate_message), methods=["POST"]),
        Route("/api/leads/{lead_id:int}/status", E("leads:write", change_status), methods=["POST"]),
        Route("/api/leads/{lead_id:int}/contact-check", E("leads:read", contact_check_view), methods=["GET"]),
        Route("/api/leads/{lead_id:int}/interactions", E("leads:write", add_interaction), methods=["POST"]),
        Route("/api/leads/{lead_id:int}/consent", E("leads:write", set_consent), methods=["POST"]),
        Route("/api/leads/{lead_id:int}/refresh", E("search:run", refresh_lead), methods=["POST"]),
        Route("/api/leads/{lead_id:int}/tasks", E("leads:write", create_task), methods=["POST"]),
        Route("/api/tasks", E("leads:read", list_tasks), methods=["GET"]),
        Route("/api/tasks/{task_id:int}", E("leads:write", patch_task), methods=["PATCH"]),
        Route("/api/export.csv", E("export", export_csv, audit_reads=True), methods=["GET"]),
        Route("/api/import", E("leads:write", import_csv), methods=["POST"]),
        Route("/api/suppression", E("leads:read", list_suppression), methods=["GET"]),
        Route("/api/suppression", E("leads:write", add_suppression), methods=["POST"]),
        Route("/api/suppression/{sup_id:int}", E(ADMIN, remove_suppression), methods=["DELETE"]),
        Route("/api/settings", E("leads:read", get_settings), methods=["GET"]),
        Route("/api/settings", E(ADMIN, put_settings), methods=["PUT"]),
        Route("/api/audit", E(ADMIN, audit_log), methods=["GET"]),
        Route("/api/maintenance/google-cache", E(ADMIN, google_cache), methods=["POST"]),
        Route("/api/tokens", E(ADMIN, list_tokens), methods=["GET"]),
    ]
