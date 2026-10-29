"""Etapas comerciais, próxima ação recomendada e política de contato."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

STATUSES: dict[str, str] = {
    "identificado": "Lead identificado",
    "qualificado": "Lead qualificado",
    "aguardando_revisao": "Aguardando revisão",
    "contato_realizado": "Contato realizado",
    "respondeu": "Respondeu",
    "reuniao_agendada": "Reunião agendada",
    "proposta_enviada": "Proposta enviada",
    "convertido": "Cliente convertido",
    "sem_interesse": "Sem interesse",
    "nao_contatar": "Não contatar novamente",
}
STATUS_ORDER = list(STATUSES)
EARLY_STATUSES = ("identificado", "qualificado", "aguardando_revisao")
CLOSED_STATUSES = ("convertido", "sem_interesse", "nao_contatar")

PRIORITIES = {"alta": "Prioridade alta", "media": "Prioridade média", "baixa": "Prioridade baixa"}

EVENT_TYPES = {
    "mensagem_enviada": "Mensagem enviada",
    "resposta_recebida": "Resposta recebida",
    "ligacao": "Ligação",
    "reuniao": "Reunião",
    "proposta": "Proposta",
    "nota": "Anotação",
    "opt_out": "Pediu para não receber mensagens",
    "status": "Mudança de status",
    "analise": "Análise",
    "mensagem_gerada": "Mensagem gerada",
    "coleta": "Coleta de dados",
    "atualizacao_dados": "Atualização de dados",
    "consentimento": "Consentimento",
    "sem_whatsapp": "Número sem WhatsApp",
}
MANUAL_EVENT_TYPES = ("mensagem_enviada", "resposta_recebida", "ligacao", "reuniao", "proposta", "nota", "opt_out", "sem_whatsapp")
CHANNELS = ("whatsapp", "telefone", "email", "formulario_site", "instagram", "facebook", "presencial", "outro")

DEFAULT_CONTACT_POLICY = {
    "daily_limit": 20,
    "min_days_between_contacts": 3,
    "max_unanswered_attempts": 3,  # 1ª mensagem + follow-up + encerramento
    "business_hours": [8, 19],
    "business_days": [0, 1, 2, 3, 4, 5],  # segunda (0) a sábado (5)
}


def auto_advance(current: str, target: str) -> str:
    """Avança automaticamente só dentro das etapas iniciais, sem nunca regredir."""
    if current in EARLY_STATUSES and target in EARLY_STATUSES and EARLY_STATUSES.index(target) > EARLY_STATUSES.index(current):
        return target
    return current


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def contact_stats(events: list[dict]) -> dict:
    """Resume o histórico: tentativas sem resposta desde a última resposta, último envio etc."""
    outbound = [e for e in events if e["type"] == "mensagem_enviada"]
    replies = [e for e in events if e["type"] == "resposta_recebida"]
    last_reply = max((_parse(e["created_at"]) for e in replies), default=None)
    last_out = max((_parse(e["created_at"]) for e in outbound), default=None)
    unanswered = [e for e in outbound if not last_reply or _parse(e["created_at"]) > last_reply]
    return {
        "outbound_total": len(outbound),
        "unanswered_attempts": len(unanswered),
        "last_outbound_at": last_out.isoformat() if last_out else None,
        "last_reply_at": last_reply.isoformat() if last_reply else None,
        "has_opt_out": any(e["type"] == "opt_out" for e in events),
    }


def contact_check(lead: dict, stats: dict, suppressed: list[dict], sent_today: int, policy: dict,
                  tz: str = "America/Sao_Paulo", now: datetime | None = None, phone_recent_other_leads: int = 0) -> dict:
    """Decide se um novo contato ativo pode ser feito agora. Retorna {allowed, blockers, warnings}."""
    p = {**DEFAULT_CONTACT_POLICY, **(policy or {})}
    now = now or datetime.now(timezone.utc)
    blockers: list[str] = []
    warnings: list[str] = []
    if lead.get("status") == "nao_contatar" or lead.get("consent_status") == "opt_out" or stats.get("has_opt_out"):
        blockers.append("A empresa pediu para não ser contatada (status, opt-out ou histórico).")
    for s in suppressed:
        blockers.append(f"Na lista de supressão ({s['kind']}: {s['value']}){' — ' + s['reason'] if s.get('reason') else ''}.")
    if lead.get("source") == "demo":
        blockers.append("Lead fictício de demonstração: envio desativado.")
    has_instagram = bool((lead.get("social_links") or {}).get("Instagram") or (lead.get("social_links") or {}).get("Facebook"))
    has_form = bool(((lead.get("site_analysis") or {}).get("signals") or {}).get("formulario"))
    if not (lead.get("phone_e164") or lead.get("whatsapp_e164") or lead.get("emails") or has_instagram or has_form):
        blockers.append("Sem nenhum canal de contato (telefone, WhatsApp, e-mail, Instagram ou formulário).")
    if lead.get("status") in ("sem_interesse", "convertido"):
        blockers.append(f"Lead com status '{STATUSES[lead['status']]}': não é caso de prospecção.")
    if sent_today >= p["daily_limit"]:
        blockers.append(f"Limite diário de {p['daily_limit']} contatos atingido. Volte amanhã.")
    awaiting_reply = stats.get("unanswered_attempts", 0) > 0
    last_out = _parse(stats.get("last_outbound_at"))
    if awaiting_reply and last_out and now - last_out < timedelta(days=p["min_days_between_contacts"]):
        when = (last_out + timedelta(days=p["min_days_between_contacts"])).astimezone(ZoneInfo(tz)).strftime("%d/%m")
        blockers.append(f"Último contato sem resposta foi há menos de {p['min_days_between_contacts']} dias. Próximo contato possível a partir de {when}.")
    if stats.get("unanswered_attempts", 0) >= p["max_unanswered_attempts"]:
        blockers.append(f"Já foram {stats['unanswered_attempts']} mensagens sem resposta (máximo {p['max_unanswered_attempts']}). Não insista.")
    if phone_recent_other_leads:
        blockers.append("Este telefone já foi contatado recentemente por outro cadastro (possível duplicata).")
    country = (lead.get("country") or "BR").upper()
    offset = lead.get("utc_offset_minutes")
    start, end = p["business_hours"]
    if offset is not None or country == "BR":
        local = now.astimezone(timezone(timedelta(minutes=int(offset))) if offset is not None else ZoneInfo(tz))
        where = "da empresa" if country != "BR" else "configurado"
        if local.weekday() not in p["business_days"] or not (start <= local.hour < end):
            warnings.append(f"Fora do horário comercial {where} ({start}h–{end}h; agora são {local:%H:%M} lá). Considere contatar mais tarde.")
        elif country != "BR":
            warnings.append(f"Horário local da empresa agora: {local:%H:%M}.")
    else:
        warnings.append("Fuso horário da empresa desconhecido: confira o horário local antes de ligar.")
    channel = lead.get("message_channel")
    if country in ("US", "CA") and channel == "email":
        warnings.append("EUA: e-mail comercial precisa do seu endereço postal, de deixar claro que é uma oferta e de um jeito de "
                        "descadastrar (CAN-SPAM). A mensagem já traz isso; confira o endereço em Configurações."
                        if country == "US" else
                        "Canadá (CASL): só envie se a empresa publicou o e-mail sem aviso contra ofertas ou te deu permissão.")
    elif country in ("US", "CA"):
        warnings.append("EUA/Canadá: WhatsApp é pouco usado e mensagens de texto de marketing para celular podem exigir "
                        "consentimento prévio (TCPA nos EUA, CASL no Canadá). Prefira ligar ou usar o formulário do site.")
    elif country != "BR":
        warnings.append("Fora do Brasil: confira as regras locais de contato comercial (ex.: PECR no Reino Unido, Spam Act na Austrália).")
    if (lead.get("phone_kind") == "fixo" and not lead.get("whatsapp_e164") and lead.get("whatsapp_status") != "sem_whatsapp"
            and lead.get("message_channel") in (None, "whatsapp")):
        warnings.append("Número fixo: pode não ter WhatsApp. Se não abrir, marque \"Não tem WhatsApp\" e tente outro canal.")
    if ((lead.get("site_analysis") or {}).get("contacts") or {}).get("sem_ofertas"):
        warnings.append("O site da empresa diz que não quer receber ofertas. Os e-mails de lá não foram guardados; pense bem antes de contatar.")
    if lead.get("consent_status") != "opt_in":
        warnings.append("Sem consentimento prévio registrado: faça um contato individual, sem envio em massa, e respeite pedidos de parada.")
    return {"allowed": not blockers, "blockers": blockers, "warnings": warnings, "sent_today": sent_today, "daily_limit": p["daily_limit"]}


def next_action(lead: dict, stats: dict, open_tasks: list[dict], policy: dict, tz: str = "America/Sao_Paulo",
                now: datetime | None = None) -> str:
    p = {**DEFAULT_CONTACT_POLICY, **(policy or {})}
    now = now or datetime.now(timezone.utc)
    if open_tasks:
        t = sorted(open_tasks, key=lambda t: t["due_date"])[0]
        due = datetime.fromisoformat(t["due_date"]).strftime("%d/%m")
        return f"Tarefa: {t['title']} (até {due})"
    status = lead.get("status")
    if status == "identificado":
        return "Analisar a presença digital e calcular a pontuação"
    if status == "qualificado":
        if lead.get("priority") == "baixa":
            return "Baixa prioridade: revisar só se houver tempo"
        if (lead.get("country") or "BR").upper() in ("US", "CA"):
            return "Gerar o roteiro de ligação"
        return "Gerar a mensagem personalizada"
    if status == "aguardando_revisao":
        channel = lead.get("message_channel")
        if lead.get("message_variant") == "roteiro_ligacao" or channel == "ligacao" or (
                not channel and (lead.get("country") or "BR").upper() in ("US", "CA")):
            return "Revisar o roteiro e ligar"
        where = {"instagram": "pelo Direct do Instagram", "facebook": "pelo Messenger do Facebook", "email": "por e-mail",
                 "formulario": "pelo formulário do site"}.get(
            channel or "", "pelo WhatsApp")
        return f"Revisar a mensagem e enviar {where}"
    if status == "contato_realizado":
        last_out = _parse(stats.get("last_outbound_at"))
        if stats.get("unanswered_attempts", 0) >= p["max_unanswered_attempts"]:
            return "Sem resposta após as tentativas: encerrar como 'Sem interesse'"
        if last_out and now - last_out >= timedelta(days=p["min_days_between_contacts"]):
            if stats.get("unanswered_attempts", 0) >= max(2, p["max_unanswered_attempts"] - 1):
                return "Enviar a mensagem de encerramento (último contato)"
            return "Enviar o follow-up com uma proposta concreta"
        if last_out:
            when = (last_out + timedelta(days=p["min_days_between_contacts"])).astimezone(ZoneInfo(tz)).strftime("%d/%m")
            return f"Aguardar resposta (follow-up possível a partir de {when})"
        return "Aguardar resposta"
    return {
        "respondeu": "Responder e propor um horário para conversar",
        "reuniao_agendada": "Preparar a apresentação ou prévia para a reunião",
        "proposta_enviada": "Acompanhar a proposta enviada",
        "convertido": "Iniciar o projeto",
        "sem_interesse": "Nenhuma: não insistir",
        "nao_contatar": "Nenhuma: contato bloqueado",
    }.get(status, "")
