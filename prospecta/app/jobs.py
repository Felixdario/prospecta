"""Fila de pesquisas e análises em segundo plano.

A fila fica no próprio banco (tabela search_jobs) e um único worker processa um trabalho por
vez. Isso evita rajadas de chamadas à API e permite acompanhar o progresso pela interface.
Se o servidor reiniciar no meio de um trabalho, ele é marcado como "interrompida".
Para muitos usuários ou servidores separados, a mesma interface pode migrar para RQ/Celery.
"""
from __future__ import annotations

import logging
import threading
from collections import Counter
from datetime import datetime, timedelta, timezone

from .db import utcnow
from .countries import build_query, get_country
from .phones import normalize_phone
from .services import Services, should_auto_message
from .site_analysis import classify_url
from .sources.places import PlacesError, QuotaExceeded, map_place

log = logging.getLogger("prospecta.jobs")

MAX_RESULTS_TOTAL = 300


class Cancelled(Exception):
    pass


def build_queries(params: dict) -> list[str]:
    country = params.get("country") or "BR"
    regions = [r.strip() for r in params.get("regions") or [] if r.strip()]
    if regions:
        return [build_query(params["segment"], params["city"], params.get("state"), r, country) for r in regions]
    return [build_query(params["segment"], params["city"], params.get("state"), None, country)]


def discard_reason(data: dict, filters: dict, country: str = "BR") -> str | None:
    """Aplica os filtros de qualificação ao resultado bruto. Retorna o motivo do descarte ou None."""
    if (data.get("business_status") or "OPERATIONAL") != "OPERATIONAL":
        return "fechada"
    kind = classify_url(data.get("website"))[0]
    wf = filters.get("website", "todos")
    if wf == "sem_site" and kind != "sem_site":
        return "tem_site"
    if wf == "sem_site_proprio" and kind == "proprio":
        return "tem_site_proprio"
    if wf == "com_site" and kind != "proprio":
        return "sem_site_proprio"
    rating, reviews = data.get("rating"), data.get("reviews_count") or 0
    if filters.get("min_rating") and (rating is None or rating < float(filters["min_rating"])):
        return "nota_abaixo_do_minimo"
    if filters.get("min_reviews") and reviews < int(filters["min_reviews"]):
        return "poucas_avaliacoes"
    if filters.get("max_reviews") and reviews > int(filters["max_reviews"]):
        return "avaliacoes_acima_do_maximo"
    phone = normalize_phone(data.get("phone"), data.get("country") or country, data.get("phone_international"))
    if filters.get("require_phone") and not (phone and phone.e164):
        return "sem_telefone"
    # Nos EUA/Canadá não dá para saber pelo número se é celular: o filtro só vale onde é possível identificar.
    if filters.get("only_mobile") and phone and phone.kind != "indefinido" and phone.kind != "celular":
        return "telefone_nao_celular"
    if filters.get("only_mobile") and not phone:
        return "telefone_nao_celular"
    return None


class Worker:
    def __init__(self, services: Services, poll_interval: float = 1.0):
        self.services = services
        self.repo = services.repo
        self.poll_interval = poll_interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self.repo.mark_interrupted_jobs()
        self._thread = threading.Thread(target=self._loop, name="prospecta-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                if not self.process_next():
                    self._stop.wait(self.poll_interval)
            except Exception:  # nunca derruba o worker
                log.exception("Erro inesperado no worker")
                self._stop.wait(self.poll_interval)

    def process_next(self) -> bool:
        job = self.repo.claim_next_job()
        if not job:
            return False
        try:
            if job["params"].get("kind") == "analise":
                self.run_analysis(job)
            else:
                self.run_search(job)
        except Cancelled:
            self.repo.update_job(job["id"], status="cancelada", stage="Cancelada pelo usuário", finished_at=utcnow())
        except Exception as e:
            log.exception("Falha na pesquisa %s", job["id"])
            self.repo.update_job(job["id"], status="falhou", stage="Falhou", error=str(e)[:500], finished_at=utcnow())
        return True

    def _check_cancel(self, job_id: int) -> None:
        if self.repo.job_cancel_requested(job_id):
            raise Cancelled()

    def _analyze_many(self, job: dict, lead_ids: list[int], use_ai: bool, started_label: str, force_refresh: bool = False) -> int:
        settings = self.repo.settings()
        min_priority = settings["pipeline"].get("auto_message_min_priority", "alta")
        high = 0
        week_ago = datetime.now(timezone.utc) - timedelta(days=7)
        for i, lead_id in enumerate(lead_ids, start=1):
            self._check_cancel(job["id"])
            self.repo.update_job(job["id"], stage=f"{started_label} {i}/{len(lead_ids)}", progress=i, total=len(lead_ids))
            try:
                lead = self.repo.get_lead(lead_id)
                analyzed = lead.get("site_analyzed_at")
                refresh = force_refresh or (bool(analyzed) and datetime.fromisoformat(analyzed) < week_ago)
                lead = self.services.analyze(lead_id, job["actor"], use_ai=False, refresh_site=refresh)
                if lead["priority"] == "alta":
                    high += 1
                if (should_auto_message(lead["priority"], min_priority) and lead.get("phone_e164")
                        and lead["status"] in ("qualificado",) and not lead.get("suggested_message")):
                    self.services.generate_message(lead_id, job["actor"], use_ai=use_ai)
            except Exception as e:  # falha parcial: segue para o próximo lead
                log.warning("Falha ao analisar lead %s: %s", lead_id, e)
        return high

    def run_search(self, job: dict) -> None:
        p = job["params"]
        filters = p.get("filters") or {}
        max_total = max(1, min(MAX_RESULTS_TOTAL, int(p.get("max_results") or 20)))
        queries = build_queries(p)
        per_query = min(60, max_total)
        places = self.services.places()
        country = get_country(p.get("country"))
        reasons: Counter = Counter()
        saved_ids: list[int] = []
        found = new = updated = 0
        errors: list[str] = []
        for qi, query in enumerate(queries, start=1):
            if len(saved_ids) >= max_total:
                break
            self.repo.update_job(job["id"], stage=f"Buscando no Google: \"{query}\" ({qi}/{len(queries)})", api_calls=places.calls)
            try:
                for place in places.search_text(query, per_query, filters.get("min_rating") or None,
                                                language=country.places_language, region=country.code):
                    self._check_cancel(job["id"])
                    found += 1
                    data = map_place(place)
                    data["country"] = data.get("country") or country.code
                    reason = discard_reason(data, filters, country.code)
                    if not reason and data["country"] != country.code:
                        reason = "fora_do_pais"
                    if not reason:
                        phone = normalize_phone(data.get("phone"), data["country"], data.get("phone_international"))
                        if self.repo.suppression_matches({"place_id": data.get("place_id"), "phone_e164": phone.e164 if phone else None, "website": data.get("website")}):
                            reason = "lista_de_supressao"
                    if reason:
                        reasons[reason] += 1
                        continue
                    lead_id, is_new = self.services.save_place(place, job["actor"], job["id"], p["segment"], country.code, p.get("segment_group"))
                    if lead_id in saved_ids:
                        continue
                    self.repo.link_search_result(job["id"], lead_id, is_new)
                    saved_ids.append(lead_id)
                    new += is_new
                    updated += not is_new
                    self.repo.update_job(job["id"], found=found, saved_new=new, updated=updated,
                                         discarded=sum(reasons.values()), discard_reasons=dict(reasons), api_calls=places.calls)
                    if len(saved_ids) >= max_total:
                        break
            except QuotaExceeded as e:
                errors.append(str(e))
                break
            except PlacesError as e:
                errors.append(f"\"{query}\": {e}")
        self.repo.update_job(job["id"], found=found, saved_new=new, updated=updated, discarded=sum(reasons.values()),
                             discard_reasons=dict(reasons), api_calls=places.calls)
        high = self._analyze_many(job, saved_ids, bool(p.get("use_ai")), "Analisando presença digital") if saved_ids else 0
        if errors and not saved_ids:
            status, stage = "falhou", "Falhou"
        elif errors:
            status, stage = "concluida_com_erros", "Concluída com erros"
        else:
            status, stage = "concluida", "Concluída"
        self.repo.update_job(job["id"], status=status, stage=stage, high_priority=high, error=" | ".join(errors)[:1000] or None,
                             finished_at=utcnow(), progress=len(saved_ids), total=len(saved_ids))

    def run_analysis(self, job: dict) -> None:
        ids = [int(i) for i in job["params"].get("lead_ids", [])]
        high = self._analyze_many(job, ids, bool(job["params"].get("use_ai")), "Analisando",
                                  force_refresh=bool(job["params"].get("refresh_site")))
        self.repo.update_job(job["id"], status="concluida", stage="Concluída", high_priority=high, saved_new=0,
                             updated=len(ids), found=len(ids), finished_at=utcnow())
