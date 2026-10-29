"""Regras de negócio: análise, pontuação, mensagens, status, contatos e manutenção."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable
from zoneinfo import ZoneInfo

from . import ai as ai_mod
from .config import Config
from .db import utcnow
from .channels import (CHANNEL_LABELS, WRITTEN_CHANNELS, best_channel, channel_options, facebook_page, instagram_search_url, messenger_url,
                       recommend_channels)
from .messages import (CHANNELS as MESSAGE_CHANNELS, COLD_VARIANTS, PROSPECTING_VARIANTS, VARIANTS, choose_variant, has_blocking,
                       lint_message, render_template, variant_incompatibility)
from .countries import get_country
from .phones import Phone, normalize_phone, whatsapp_link
from .pipeline import (CLOSED_STATUSES, EVENT_TYPES, STATUS_ORDER, STATUSES, auto_advance, contact_check,
                       contact_stats, next_action)
from .repository import Repo, clean_emails
from .scoring import score_lead
from .segments import detect_segment
from .site_analysis import Fetcher, analyze_website, make_requests_fetcher
from .sources.csv_import import parse_csv
from .sources.places import PlacesClient, QuotaExceeded, SKU_DETAILS, SKU_TEXT_SEARCH, map_place


class BusinessError(Exception):
    status_code = 400


class ContactBlocked(BusinessError):
    status_code = 409

    def __init__(self, blockers: list[str]):
        super().__init__("Contato bloqueado: " + " ".join(blockers))
        self.blockers = blockers


class Forbidden(BusinessError):
    status_code = 403


PRIORITY_RANK = {"alta": 3, "media": 2, "baixa": 1}
SUPPRESSION_BLOCKER_HINTS = ("pediu para não ser contatada", "lista de supressão", "Sem nenhum canal", "fictício")
EVENT_CHANNEL = {"ligacao": "telefone", "formulario": "formulario_site"}


class Services:
    def __init__(self, repo: Repo, config: Config, places_factory: Callable[[], PlacesClient] | None = None,
                 fetcher: Fetcher | None = None, writer: ai_mod.ClaudeWriter | None = None):
        self.repo = repo
        self.config = config
        self._places_factory = places_factory
        self.fetcher = fetcher if fetcher is not None else make_requests_fetcher(config.site_user_agent, config.site_timeout_seconds)
        if writer is None and config.has_ai:
            writer = ai_mod.ClaudeWriter(config.anthropic_api_key, config.ai_model)
        self.writer = writer

    # ------------------------------------------------------------------ Google
    def places(self) -> PlacesClient:
        if self._places_factory:
            return self._places_factory()

        def guard(sku: str) -> None:
            limit = self.config.google_textsearch_monthly_limit if sku == SKU_TEXT_SEARCH else self.config.google_details_monthly_limit
            if self.repo.consume_quota(sku, limit) < 0:
                raise QuotaExceeded(f"Limite mensal de {limit} chamadas ({sku}) atingido. Ajuste no .env se quiser pagar pelo excedente.")

        return PlacesClient(self.config.google_api_key, guard)

    def save_place(self, place: dict, actor: str, search_id: int | None, segment_hint: str | None = None,
                   country_hint: str | None = None, segment_group: str | None = None) -> tuple[int, bool]:
        data = map_place(place)
        data["country"] = data.get("country") or country_hint or "BR"
        seg = detect_segment(segment_hint, data.get("category"), google_types=data.pop("types", None), preferred=segment_group)
        data["segment"] = seg.key
        return self.repo.upsert_lead(data, "google_places", actor, search_id)

    def refresh_from_google(self, lead_id: int, actor: str) -> dict:
        lead = self.repo.get_lead(lead_id)
        if not lead.get("place_id"):
            raise BusinessError("Lead sem place_id do Google: não é possível atualizar pela API.")
        country = get_country(lead.get("country"))
        place = self.places().get_details(lead["place_id"], language=country.places_language, region=country.code)
        self.save_place(place, actor, None, lead.get("segment"), country.code)
        self.repo.add_event(lead_id, actor, "atualizacao_dados", "Dados atualizados pela Google Places API")
        return self.analyze(lead_id, actor, refresh_site=False)

    # ------------------------------------------------------------------ análise e pontuação
    def analyze(self, lead_id: int, actor: str, use_ai: bool = False, refresh_site: bool = False) -> dict:
        lead = self.repo.get_lead(lead_id)
        settings = self.repo.settings()
        updates: dict = {}
        analysis = lead.get("site_analysis")
        kind = (analysis or {}).get("kind")
        if kind != "desconhecido" and (analysis is None or refresh_site):
            fetcher = self.fetcher if settings["pipeline"].get("analyze_sites", True) else None
            analysis = analyze_website(lead.get("website"), fetcher, self.config.site_user_agent, country=lead.get("country") or "BR")
            updates.update({"site_analysis": analysis, "site_analyzed_at": utcnow(), "presence_kind": analysis["kind"]})
            updates.update(self._contact_updates(lead, analysis))
            lead.update(updates)
        result = score_lead(lead, settings["scoring"])
        updates.update({"score": result["score"], "priority": result["priority"], "score_breakdown": result, "scored_at": utcnow()})
        lead.update(updates)
        gen = ai_mod.generate(lead, choose_variant(lead), settings["seller"], self.config.timezone, self.writer, use_ai and self.writer is not None)
        updates.update({"analysis": gen["analysis"], "analysis_generated_by": gen["generated_by"], "analyzed_at": utcnow()})
        new_status = auto_advance(lead["status"], "qualificado")
        if new_status != lead["status"]:
            updates["status"] = new_status
        self.repo.update_lead(lead_id, updates)
        self.repo.add_event(lead_id, actor, "analise", result["summary"], details={"score": result["score"], "por": gen["generated_by"]})
        return self.repo.get_lead(lead_id)

    @staticmethod
    def _contact_updates(lead: dict, analysis: dict) -> dict:
        """Guarda WhatsApp, e-mails e redes que a própria empresa publicou (sem apagar o que o usuário informou)."""
        contacts = analysis.get("contacts") or {}
        out: dict = {}
        # o que já está salvo (inclusive o que o usuário corrigiu) prevalece
        socials = {**(analysis.get("social_links") or {}), **(lead.get("social_links") or {})}
        if contacts.get("instagram"):
            socials.setdefault("Instagram", contacts["instagram"])
        if contacts.get("facebook"):
            socials.setdefault("Facebook", contacts["facebook"])
        if socials:
            out["social_links"] = socials
        if contacts.get("whatsapp") and lead.get("whatsapp_source") in (None, "site"):
            out["whatsapp_e164"], out["whatsapp_source"] = contacts["whatsapp"][0], "site"
        if contacts.get("emails"):
            out["emails"] = clean_emails(list(lead.get("emails") or []) + contacts["emails"])
        return out

    def rescore_all(self, actor: str) -> int:
        settings = self.repo.settings()
        items, _ = self.repo.list_leads({"page_size": 500})
        count, page = 0, 1
        while items:
            for item in items:
                lead = self.repo.get_lead(item["id"])
                r = score_lead(lead, settings["scoring"])
                self.repo.update_lead(lead["id"], {"score": r["score"], "priority": r["priority"], "score_breakdown": r, "scored_at": utcnow()})
                count += 1
            page += 1
            items, _ = self.repo.list_leads({"page_size": 500, "page": page})
        return count

    # ------------------------------------------------------------------ mensagens
    def generate_message(self, lead_id: int, actor: str, variant: str | None = None, use_ai: bool = False,
                         channel: str | None = None) -> dict:
        lead = self.repo.get_lead(lead_id)
        channel = channel or lead.get("message_channel") or best_channel(lead) or "whatsapp"
        if channel not in MESSAGE_CHANNELS:
            raise BusinessError(f"Canal inválido. Opções: {', '.join(MESSAGE_CHANNELS)}")
        if variant == "roteiro_ligacao":
            channel = "ligacao"
        elif variant and channel == "ligacao":
            # Você escolheu uma mensagem escrita estando em "Ligação": troca para o melhor canal escrito.
            written = [c["key"] for c in recommend_channels(lead) if c["key"] in WRITTEN_CHANNELS]
            channel = written[0] if written else "email"
        variant = variant or choose_variant(lead, channel)
        if channel == "ligacao" and variant in COLD_VARIANTS:
            variant = "roteiro_ligacao"
        if variant not in VARIANTS:
            raise BusinessError(f"Variação inválida. Opções: {', '.join(VARIANTS)}")
        prospecting = variant in PROSPECTING_VARIANTS
        if prospecting and (lead["status"] == "nao_contatar" or lead.get("consent_status") == "opt_out"):
            raise BusinessError("Esta empresa pediu para não ser contatada. Não é possível gerar mensagem de prospecção.")
        if lead.get("score") is None:
            lead = self.analyze(lead_id, actor)
        settings = self.repo.settings()
        incompatible = variant_incompatibility(lead, variant)
        if incompatible:
            raise BusinessError(f"A variação '{VARIANTS[variant]}' não combina com esta empresa: {incompatible}.")
        template_warnings = lint_message(render_template(lead, variant, settings["seller"], self.config.timezone, channel=channel),
                                         lead, channel, variant)
        if has_blocking(template_warnings):
            motivos = "; ".join(w["motivo"] for w in template_warnings if w["nivel"] == "bloqueante")
            raise BusinessError(f"A variação '{VARIANTS[variant]}' não combina com os dados desta empresa: {motivos}.")
        gen = ai_mod.generate(lead, variant, settings["seller"], self.config.timezone, self.writer, use_ai and self.writer is not None,
                              channel=channel)
        warnings = list(gen["warnings"])
        if channel == "email" and not lead.get("emails"):
            warnings.append({"nivel": "aviso", "motivo": "Sem e-mail cadastrado: digite o endereço da empresa no campo \"Para\" antes de enviar."})
        if channel == "facebook" and not facebook_page(lead):
            warnings.append({"nivel": "aviso", "motivo": "Página do Facebook ainda não encontrada: salve o link da página antes de enviar."})
        if channel == "email" and (lead.get("country") or "BR") in ("US", "CA") and not settings["seller"].get("endereco"):
            warnings.append({"nivel": "aviso", "motivo": "Inclua seu endereço postal em Configurações: e-mails comerciais para os EUA precisam dele (CAN-SPAM)."})
        if channel == "instagram" and not (lead.get("social_links") or {}).get("Instagram"):
            warnings.append({"nivel": "aviso", "motivo": "Instagram da empresa ainda não encontrado: use \"Procurar o Instagram\" e confira o perfil."})
        updates = {"suggested_message": gen["message"], "message_variant": variant, "message_generated_by": gen["generated_by"],
                   "message_generated_at": utcnow(), "message_warnings": warnings, "message_channel": channel,
                   "message_subject": gen.get("subject")}
        if gen["generated_by"] == "ia":
            updates.update({"analysis": gen["analysis"], "analysis_generated_by": "ia"})
        if prospecting:
            new_status = auto_advance(lead["status"], "aguardando_revisao")
            if new_status != lead["status"]:
                updates["status"] = new_status
        self.repo.update_lead(lead_id, updates)
        self.repo.add_event(lead_id, actor, "mensagem_gerada",
                            f"Mensagem gerada ({VARIANTS[variant]}, {CHANNEL_LABELS.get(channel, channel)}) por {'IA' if gen['generated_by'] == 'ia' else 'modelo'}")
        return {"message": gen["message"], "subject": gen.get("subject"), "channel": channel, "variant": variant,
                "generated_by": gen["generated_by"], "warnings": warnings}

    # ------------------------------------------------------------------ status e contatos
    def change_status(self, lead_id: int, status: str, actor: str, note: str | None = None, is_admin: bool = False) -> dict:
        if status not in STATUSES:
            raise BusinessError(f"Status inválido. Opções: {', '.join(STATUSES)}")
        lead = self.repo.get_lead(lead_id)
        if lead["status"] == "nao_contatar" and status != "nao_contatar" and not is_admin:
            raise Forbidden("Lead marcado como 'Não contatar novamente'. Só o administrador pode reverter.")
        updates: dict = {"status": status}
        if status == "nao_contatar":
            updates.update({"consent_status": "opt_out", "consent_at": utcnow(), "consent_note": note or "Marcado como não contatar"})
            self.repo.suppress_lead(lead, note or "Status 'Não contatar novamente'", actor)
        summary = f"Status: {STATUSES[lead['status']]} → {STATUSES[status]}" + (f". {note}" if note else "")
        self.repo.add_event(lead_id, actor, "status", summary, lead_updates=updates)
        return self.repo.get_lead(lead_id)

    def check_contact(self, lead_id: int) -> dict:
        lead = self.repo.get_lead(lead_id)
        settings = self.repo.settings()
        stats = contact_stats(self.repo.events(lead_id))
        policy = settings["contact_policy"]
        return contact_check(
            lead, stats, self.repo.suppression_matches(lead), self.repo.sent_today(self.config.timezone), policy,
            self.config.timezone, phone_recent_other_leads=self.repo.phone_contacted_elsewhere(
                lead.get("phone_e164"), lead_id, int(policy.get("min_days_between_contacts", 3)) * 10),
        )

    def record_interaction(self, lead_id: int, type_: str, actor: str, summary: str | None = None, channel: str | None = None,
                           override_reason: str | None = None, is_admin: bool = False, message_text: str | None = None) -> dict:
        if type_ not in EVENT_TYPES:
            raise BusinessError(f"Tipo de interação inválido. Opções: {', '.join(EVENT_TYPES)}")
        lead = self.repo.get_lead(lead_id)
        channel = EVENT_CHANNEL.get(channel or "", channel)
        details: dict = {}
        if type_ == "sem_whatsapp":
            number = lead.get("whatsapp_e164") or lead.get("phone_e164")
            # "descartado" impede que a próxima leitura do site traga o mesmo número de volta
            updates_wa = ({"whatsapp_e164": None, "whatsapp_source": "descartado"} if lead.get("whatsapp_e164")
                          else {"whatsapp_status": "sem_whatsapp"})
            self.repo.add_event(lead_id, actor, "sem_whatsapp", summary or f"O número {number or ''} não tem WhatsApp".strip(),
                                "whatsapp", lead_updates=updates_wa)
            return self.repo.get_lead(lead_id)
        if type_ == "mensagem_enviada":
            check = self.check_contact(lead_id)
            if not check["allowed"]:
                hard = [b for b in check["blockers"] if any(h in b for h in SUPPRESSION_BLOCKER_HINTS)]
                if hard or not (is_admin and override_reason):
                    raise ContactBlocked(check["blockers"])
                details["override"] = {"reason": override_reason, "blockers": check["blockers"]}
            if message_text:
                details["mensagem"] = message_text[:2000]
            details["abordagem"] = lead.get("message_variant")
            details["canal_mensagem"] = lead.get("message_channel")
        transitions = {
            "mensagem_enviada": "contato_realizado",
            "resposta_recebida": "respondeu",
            "reuniao": "reuniao_agendada",
            "proposta": "proposta_enviada",
        }
        updates: dict = {}
        target = transitions.get(type_)
        if target and lead["status"] not in CLOSED_STATUSES and STATUS_ORDER.index(target) > STATUS_ORDER.index(lead["status"]):
            updates["status"] = target
        if type_ == "resposta_recebida" and channel == "whatsapp" and not lead.get("whatsapp_e164"):
            updates["whatsapp_status"] = "confirmado"
        if type_ == "opt_out":
            updates.update({"status": "nao_contatar", "consent_status": "opt_out", "consent_at": utcnow(), "consent_note": summary or "Pediu para não receber mensagens"})
            self.repo.suppress_lead(lead, summary or "Pediu para não receber mensagens", actor)
        default_summary = EVENT_TYPES[type_] + (f" via {channel}" if channel else "")
        if type_ == "mensagem_enviada" and channel == "telefone":
            default_summary = "Ligação feita (contato ativo)"
        elif type_ == "mensagem_enviada" and channel == "formulario_site":
            default_summary = "Mensagem enviada pelo formulário do site"
        self.repo.add_event(lead_id, actor, type_, summary or default_summary, channel, details or None, lead_updates=updates or None)
        return self.repo.get_lead(lead_id)

    def set_consent(self, lead_id: int, status: str, note: str, actor: str) -> dict:
        if status not in ("nao_registrado", "opt_in", "opt_out"):
            raise BusinessError("Consentimento inválido")
        lead = self.repo.get_lead(lead_id)
        updates = {"consent_status": status, "consent_note": note, "consent_at": utcnow()}
        if status == "opt_out":
            updates["status"] = "nao_contatar"
            self.repo.suppress_lead(lead, note or "Opt-out registrado", actor)
        self.repo.add_event(lead_id, actor, "consentimento", f"Consentimento: {status}. {note}".strip(), lead_updates=updates)
        return self.repo.get_lead(lead_id)

    # ------------------------------------------------------------------ visão completa
    def lead_detail(self, lead_id: int) -> dict:
        lead = self.repo.get_lead(lead_id)
        settings = self.repo.settings()
        events = self.repo.events(lead_id)
        stats = contact_stats(events)
        tasks = self.repo.list_tasks(lead_id, scope="all")
        open_tasks = [t for t in tasks if not t["done"]]
        check = self.check_contact(lead_id)
        phone = Phone(lead.get("phone") or "", None, lead.get("phone_e164"), lead["phone_kind"]) if lead.get("phone_kind") else None
        channels = recommend_channels(lead)
        wa_target = lead.get("whatsapp_e164") or (lead.get("phone_e164") if lead.get("whatsapp_status") != "sem_whatsapp" else None)
        stale = False
        if lead.get("google_fetched_at"):
            age = datetime.now(timezone.utc) - datetime.fromisoformat(lead["google_fetched_at"])
            stale = age.days >= self.config.google_cache_days
        return {
            "lead": lead,
            "events": events,
            "tasks": tasks,
            "contact": {**check, **stats},
            "next_action": next_action(lead, stats, open_tasks, settings["contact_policy"], self.config.timezone),
            "whatsapp_link": whatsapp_link(wa_target, lead.get("suggested_message")) if check["allowed"] and wa_target else None,
            "whatsapp_target": wa_target,
            "whatsapp_hypothesis": ("WhatsApp publicado pela empresa" if lead.get("whatsapp_e164")
                                    else phone.whatsapp_hypothesis if phone else None),
            "channels": channels,
            "channel_options": channel_options(lead),
            "messenger_url": messenger_url(next((c["target"] for c in channels if c["key"] == "facebook"), None)),
            "best_channel": channels[0]["key"] if channels else None,
            "instagram_search_url": instagram_search_url(lead),
            "suggested_variant": choose_variant(lead, lead.get("message_channel") or (channels[0]["key"] if channels else None)),
            "google_data_stale": stale,
        }

    # ------------------------------------------------------------------ importação
    def import_csv(self, raw: bytes, actor: str) -> dict:
        rows, errors = parse_csv(raw)
        created = updated = suppressed = 0
        ids = []
        for row in rows:
            website_known = row.pop("has_website_column")
            if not row.get("country"):
                phone_raw = (row.get("phone") or "").strip()
                row["country"] = next((c for prefix, c in (("+1", "US"), ("+44", "GB"), ("+61", "AU"), ("+55", "BR"))
                                       if phone_raw.startswith(prefix)), "BR")
            seg = detect_segment(row.get("category"), row.get("name"))
            row["segment"] = seg.key
            probe = {"phone_e164": None, "place_id": row.get("place_id"), "website": row.get("website")}
            p = normalize_phone(row.get("phone"), row.get("country") or "BR")
            probe["phone_e164"] = p.e164 if p else None
            if self.repo.suppression_matches(probe):
                suppressed += 1
                continue
            lead_id, is_new = self.repo.upsert_lead(row, "csv_importacao", actor, website_known=website_known)
            ids.append(lead_id)
            created += is_new
            updated += not is_new
        job_id = self.repo.create_job({"kind": "analise", "lead_ids": ids, "origem": "importacao_csv"}, actor) if ids else None
        return {"linhas_validas": len(rows), "novos": created, "atualizados": updated, "suprimidos": suppressed,
                "erros": errors[:50], "analysis_job_id": job_id}

    # ------------------------------------------------------------------ manutenção do cache do Google
    def google_cache_maintenance(self, mode: str, actor: str) -> dict:
        stale = self.repo.stale_google_leads(self.config.google_cache_days)
        report = {"prazo_dias": self.config.google_cache_days, "expirados": len(stale), "removidos": 0, "atualizados": 0, "erros": []}
        if mode == "report":
            report["leads"] = stale[:100]
            return report
        for item in stale:
            active = item["status"] not in ("identificado", "qualificado", "sem_interesse")
            try:
                if mode == "refresh" and active:
                    self.refresh_from_google(item["id"], actor)
                    report["atualizados"] += 1
                elif mode in ("purge", "refresh"):
                    self.repo.purge_google_content(item["id"], actor)
                    report["removidos"] += 1
            except Exception as e:
                report["erros"].append(f"Lead {item['id']}: {e}")
                if isinstance(e, QuotaExceeded):
                    break
        return report


def today_local(tz: str) -> str:
    return datetime.now(ZoneInfo(tz)).date().isoformat()


def should_auto_message(priority: str | None, min_priority: str) -> bool:
    return PRIORITY_RANK.get(priority or "baixa", 0) >= PRIORITY_RANK.get(min_priority, 99)
