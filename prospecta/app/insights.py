"""O que está funcionando: taxa de resposta por canal, abordagem, segmento e tentativa.

Cada empresa contatada conta uma vez, pelo PRIMEIRO contato ativo (canal e abordagem usados).
"Respondeu" = houve resposta registrada depois desse primeiro contato.
Com poucos envios os números variam muito: compare abordagens só depois de uns 20 contatos em cada.
"""
from __future__ import annotations

from collections import defaultdict

from .channels import CHANNEL_LABELS
from .db import loads
from .messages import VARIANTS
from .segments import get_segment

EVENT_TO_CHANNEL = {"telefone": "ligacao", "formulario_site": "formulario"}
ADVANCED = ("reuniao_agendada", "proposta_enviada", "convertido")
MIN_SAMPLE = 20


def _row(key: str, label: str, contacted: int, replied: int) -> dict:
    return {"chave": key, "rotulo": label, "contatados": contacted, "responderam": replied,
            "taxa": round(100 * replied / contacted, 1) if contacted else 0.0, "amostra_pequena": contacted < MIN_SAMPLE}


def compute(rows: list[dict]) -> dict:
    """rows: eventos de contato ordenados por lead e data, com dados do lead (repo.outreach_events)."""
    leads: dict[int, dict] = {}
    for r in rows:
        info = leads.setdefault(r["lead_id"], {"first": None, "outbound": 0, "replied_after": None, "segment": r["segment"],
                                               "country": r["country"], "status": r["status"], "presence": r["presence_kind"],
                                               "sem_whatsapp": False, "opt_out": False})
        if r["type"] == "mensagem_enviada":
            info["outbound"] += 1
            if info["first"] is None:
                details = loads(r["details"], {}) or {}
                channel = EVENT_TO_CHANNEL.get(r["channel"] or "", r["channel"] or details.get("canal_mensagem") or "outro")
                info["first"] = {"channel": channel, "variant": details.get("abordagem") or "sem_registro"}
        elif r["type"] == "resposta_recebida" and info["first"] is not None and info["replied_after"] is None:
            info["replied_after"] = info["outbound"]
        elif r["type"] == "sem_whatsapp":
            info["sem_whatsapp"] = True
        elif r["type"] == "opt_out":
            info["opt_out"] = True

    contacted = [i for i in leads.values() if i["first"] is not None]
    groups: dict[str, dict[str, list[int]]] = {"canal": defaultdict(lambda: [0, 0]), "abordagem": defaultdict(lambda: [0, 0]),
                                                "segmento": defaultdict(lambda: [0, 0]), "presenca": defaultdict(lambda: [0, 0]),
                                                "pais": defaultdict(lambda: [0, 0])}
    by_attempt: dict[int, int] = defaultdict(int)
    for i in contacted:
        replied = i["replied_after"] is not None
        for group, key in (("canal", i["first"]["channel"]), ("abordagem", i["first"]["variant"]), ("segmento", i["segment"] or "geral"),
                           ("presenca", i["presence"] or "desconhecido"), ("pais", i["country"] or "BR")):
            groups[group][key][0] += 1
            groups[group][key][1] += replied
        if replied:
            by_attempt[i["replied_after"]] += 1

    labels = {
        "canal": lambda k: CHANNEL_LABELS.get(k, {"telefone": "Ligação", "outro": "Outro"}.get(k, k.capitalize())),
        "abordagem": lambda k: VARIANTS.get(k, "Sem registro (contatos antigos)" if k == "sem_registro" else k),
        "segmento": lambda k: get_segment(k).label,
        "presenca": lambda k: k,
        "pais": lambda k: k,
    }

    def table(group: str) -> list[dict]:
        rows_ = [_row(k, labels[group](k), v[0], v[1]) for k, v in groups[group].items()]
        return sorted(rows_, key=lambda x: (-x["contatados"], -x["taxa"]))

    total, replied_total = len(contacted), sum(1 for i in contacted if i["replied_after"] is not None)
    return {
        "contatados": total,
        "responderam": replied_total,
        "taxa": round(100 * replied_total / total, 1) if total else 0.0,
        "avancaram": sum(1 for i in contacted if i["status"] in ADVANCED),
        "convertidos": sum(1 for i in contacted if i["status"] == "convertido"),
        "sem_whatsapp": sum(1 for i in leads.values() if i["sem_whatsapp"]),
        "pediram_para_parar": sum(1 for i in leads.values() if i["opt_out"]),
        "por_canal": table("canal"),
        "por_abordagem": table("abordagem"),
        "por_segmento": table("segmento"),
        "por_presenca": table("presenca"),
        "por_pais": table("pais"),
        "resposta_por_tentativa": [{"tentativa": k, "respostas": v} for k, v in sorted(by_attempt.items())],
        "amostra_minima": MIN_SAMPLE,
    }
