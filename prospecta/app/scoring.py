"""Pontuação de leads (0 a 100), explicável e configurável.

Cada critério gera um item com pontos, evidência e base ("verificado" ou "hipotese").
A IA não participa do cálculo: a nota é determinística e reproduzível. Os pesos ficam em
settings["scoring"] e podem ser ajustados pela tela de Configurações.
"""
from __future__ import annotations

import copy
from typing import Any

from .segments import get_segment

DEFAULT_SCORING: dict[str, Any] = {
    "thresholds": {"alta": 70, "media": 45},
    "presence": {
        "sem_site": 40,
        "google_descontinuado": 40,
        "rede_social": 32,
        "whatsapp": 32,
        "agregador_links": 30,
        "plataforma_terceiros": 22,
        "proprio": 0,
        "desconhecido": 0,
    },
    "site_issue_points": {
        "site_fora_do_ar": 35,
        "erro_http": 30,
        "pagina_em_construcao": 30,
        "dominio_gratuito": 12,
        "tecnologia_obsoleta": 12,
        "sem_meta_viewport": 10,
        "sem_https": 8,
        "rodape_desatualizado": 6,
        "sem_contato_direto": 5,
        "lento": 4,
        "conteudo_minimo": 4,
        "sem_titulo": 3,
        "sem_meta_descricao": 2,
    },
    "site_issue_cap": 35,
    "reputation": {
        "excelente": {"min_rating": 4.5, "min_reviews": 30, "points": 20},
        "boa": {"min_rating": 4.0, "min_reviews": 10, "points": 12},
    },
    "review_volume": [
        {"min_reviews": 100, "points": 10},
        {"min_reviews": 30, "points": 5},
    ],
    "penalties": {
        "poucas_avaliacoes": {"max_reviews": 4, "points": -10},
        "nota_baixa": {"max_rating": 3.5, "points": -10},
    },
    "contact": {"telefone": 10, "celular": 5, "whatsapp_publicado": 5, "email": 3, "instagram": 3},
    "segment_values": {},
}

PRESENCE_LABELS = {
    "sem_site": "Nenhum site informado no perfil do Google",
    "google_descontinuado": "Usa o site gratuito do Google, serviço descontinuado em 2024",
    "rede_social": "Usa rede social no lugar de um site próprio",
    "whatsapp": "Usa link de WhatsApp no lugar de um site próprio",
    "agregador_links": "Usa agregador de links (ex.: Linktree) no lugar de um site próprio",
    "plataforma_terceiros": "Usa página em plataforma de terceiros no lugar de um site próprio",
    "desconhecido": "Presença digital desconhecida: a fonte não informa site (confirme antes de abordar)",
}


def merge_config(base: dict, override: dict | None) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge_config(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def priority_for(score: int, thresholds: dict) -> str:
    if score >= thresholds["alta"]:
        return "alta"
    if score >= thresholds["media"]:
        return "media"
    return "baixa"


def _fmt_rating(r: float) -> str:
    return f"{r:.1f}".replace(".", ",")


def score_lead(lead: dict, config: dict | None = None) -> dict:
    """Recebe o lead (dict com colunas do banco já decodificadas) e devolve
    {score, priority, items, summary}."""
    cfg = merge_config(DEFAULT_SCORING, config)
    items: list[dict] = []
    iso = (lead.get("google_fetched_at") or "")[:10]
    fetched_on = "/".join(reversed(iso.split("-"))) if iso else ""
    google_basis = f"Google Maps{' em ' + fetched_on if fetched_on else ''}"

    def add(code, label, points, evidence, basis="verificado"):
        items.append({"code": code, "label": label, "points": int(points), "evidence": evidence, "basis": basis})

    status = (lead.get("business_status") or "").upper()
    if status in ("CLOSED_PERMANENTLY", "CLOSED_TEMPORARILY"):
        label = "Fechada permanentemente" if status == "CLOSED_PERMANENTLY" else "Fechada temporariamente"
        add("empresa_fechada", f"Empresa marcada como {label.lower()} no Google", 0, google_basis)
        return {"score": 0, "priority": "baixa", "items": items, "summary": f"Pontuação 0: empresa {label.lower()}."}

    # 1) Presença digital
    analysis = lead.get("site_analysis") or {}
    website = lead.get("website")
    kind = analysis.get("kind") or ("sem_site" if not website else None)
    if kind is None:
        add("site_nao_analisado", "Site informado, mas ainda não analisado", 0, website or "", "verificado")
    elif kind != "proprio":
        pts = cfg["presence"].get(kind, 0)
        evidence = "Campo de site vazio no perfil" if kind == "sem_site" else f"Site informado: {website}"
        if lead.get("source") == "csv_importacao" and kind == "sem_site":
            evidence = "Planilha importada sem site para esta empresa (confirme no Google antes de afirmar)"
        if kind == "desconhecido":
            evidence = "A planilha importada não tem coluna de site"
        add(f"presenca_{kind}", PRESENCE_LABELS.get(kind, kind), pts, evidence, "hipotese" if kind == "desconhecido" else "verificado")
    else:
        if analysis.get("skipped_reason"):
            add("site_nao_analisado", "Site próprio não analisado", 0, analysis["skipped_reason"])
        issue_points = cfg["site_issue_points"]
        cap = cfg["site_issue_cap"]
        total = 0
        for issue in analysis.get("issues", []):
            p = issue_points.get(issue["code"], 0)
            if p <= 0:
                continue
            p = min(p, max(0, cap - total))
            total += p
            add(f"site_{issue['code']}", issue["label"], p, issue.get("evidence", ""), issue.get("basis", "verificado"))
        if not analysis.get("issues") and analysis.get("fetched"):
            add("site_ok", "Site próprio sem problemas evidentes na checagem automática", 0, analysis.get("final_url", website or ""))

    # 2) Reputação e atividade (potencial de retorno)
    rating = lead.get("rating")
    reviews = lead.get("reviews_count") or 0
    if rating is not None:
        rep = cfg["reputation"]
        for level in ("excelente", "boa"):
            r = rep[level]
            if rating >= r["min_rating"] and reviews >= r["min_reviews"]:
                add(f"reputacao_{level}", f"Reputação {level} no Google",
                    r["points"], f"Nota {_fmt_rating(rating)} com {reviews} avaliações ({google_basis})")
                break
        for tier in sorted(cfg["review_volume"], key=lambda t: -t["min_reviews"]):
            if reviews >= tier["min_reviews"]:
                add("volume_avaliacoes", "Volume alto de avaliações (negócio com movimento)", tier["points"],
                    f"{reviews} avaliações", "verificado")
                break
        pen = cfg["penalties"]
        if rating <= pen["nota_baixa"]["max_rating"]:
            add("nota_baixa", "Nota baixa no Google", pen["nota_baixa"]["points"], f"Nota {_fmt_rating(rating)}")
    if reviews <= cfg["penalties"]["poucas_avaliacoes"]["max_reviews"]:
        add("poucas_avaliacoes", "Poucas avaliações públicas (menos sinais de atividade)",
            cfg["penalties"]["poucas_avaliacoes"]["points"], f"{reviews} avaliações", "hipotese")

    # 3) Contato disponível
    kind_phone = lead.get("phone_kind")
    if lead.get("phone_e164"):
        add("telefone", "Telefone comercial público para contato", cfg["contact"]["telefone"], lead.get("phone") or "")
        if kind_phone == "celular":
            add("celular", "Número de celular (pode ter WhatsApp)", cfg["contact"]["celular"],
                "Formato de celular. WhatsApp não verificado", "hipotese")
    else:
        add("sem_telefone", "Sem telefone válido para contato", 0, lead.get("phone") or "Campo vazio")
    contact_cfg = cfg["contact"]
    if lead.get("whatsapp_e164") and contact_cfg.get("whatsapp_publicado"):
        add("whatsapp_publicado", "WhatsApp publicado pela empresa", contact_cfg["whatsapp_publicado"], lead["whatsapp_e164"])
    if lead.get("emails") and contact_cfg.get("email"):
        add("email_publicado", "E-mail publicado pela empresa", contact_cfg["email"], ", ".join(lead["emails"]))
    if (lead.get("social_links") or {}).get("Instagram") and contact_cfg.get("instagram"):
        add("instagram", "Instagram da empresa encontrado", contact_cfg["instagram"], lead["social_links"]["Instagram"])

    # 4) Segmento (estimativa de benefício de um site)
    seg = get_segment(lead.get("segment"))
    seg_points = cfg["segment_values"].get(seg.key, seg.value)
    if seg_points:
        add("segmento", f"Segmento: {seg.label}", seg_points,
            "Estimativa configurável de quanto o segmento costuma se beneficiar de um site", "hipotese")

    score = max(0, min(100, sum(i["points"] for i in items)))
    priority = priority_for(score, cfg["thresholds"])
    top = sorted((i for i in items if i["points"] != 0), key=lambda i: -abs(i["points"]))[:4]
    parts = ", ".join(f"{i['label'][:1].lower()}{i['label'][1:]} ({'+' if i['points'] > 0 else ''}{i['points']})" for i in top)
    summary = f"Pontuação {score} ({priority}): {parts}." if parts else f"Pontuação {score} ({priority})."
    return {"score": score, "priority": priority, "items": items, "summary": summary}
