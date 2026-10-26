"""Análise comercial determinística e mensagens de abordagem.

- Fatos verificados vêm apenas dos dados coletados (Google/planilha/checagem do site).
- Hipóteses ficam separadas e rotuladas.
- As mensagens usam somente observações VERIFICADAS e passam por um verificador de
  linguagem (sem promessas, pressão, exageros ou afirmações sem dados).
"""
from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

from .phones import Phone
from .segments import get_segment

VARIANTS: dict[str, str] = {
    "sem_site": "Empresa sem site identificado",
    "presenca_limitada": "Presença digital limitada (rede social, link ou plataforma)",
    "site_desatualizado": "Site com oportunidades de melhoria verificadas",
    "site_existente": "Site próprio sem problemas evidentes",
    "responsavel_nao_identificado": "Responsável ainda não identificado",
    "follow_up": "Follow-up único (sem resposta)",
    "resposta_interesse": "Respondeu demonstrando interesse",
    "pedido_informacoes": "Pediu mais informações",
    "outro_horario": "Pediu contato em outro horário",
    "opt_out": "Não deseja receber novas mensagens",
}

# Observações de site que podem ser citadas na mensagem (somente verificadas)
SITE_OBSERVATIONS = {
    "site_fora_do_ar": "que o site não abriu quando tentei acessar",
    "erro_http": "que o site apresentou um erro quando tentei acessar",
    "pagina_em_construcao": "que a página está com aviso de construção",
    "tecnologia_obsoleta": "que a página usa uma tecnologia antiga, que não funciona bem nos navegadores atuais",
    "sem_meta_viewport": "que a página não está configurada para se adaptar ao celular",
    "dominio_gratuito": "que o site está em um endereço gratuito, sem domínio próprio",
    "sem_https": "que o site ainda não usa HTTPS, então alguns navegadores mostram o aviso de \"não seguro\"",
    "sem_contato_direto": "que não há um botão direto para WhatsApp ou telefone na página inicial",
}
OBS_ORDER = list(SITE_OBSERVATIONS)

LINT_RULES: list[tuple[str, str, str]] = [
    (r"perd(?:e|em|endo|er|eu|eram)\s+(?:muitos?\s+)?(?:clientes|dinheiro|vendas|oportunidades)", "Afirma que a empresa perde clientes ou dinheiro sem dados", "bloqueante"),
    (r"\bgarant(?:o|imos|ia|ido|ir)\b", "Promessa ou garantia de resultado", "bloqueante"),
    (r"\b100\s?%", "Promessa absoluta", "bloqueante"),
    (r"\bdobrar\b|\btriplicar\b|multiplicar (?:as |suas )?vendas|explodir", "Promessa exagerada de resultado", "bloqueante"),
    (r"imperd[ií]vel|[uú]ltima chance|s[oó] hoje|\burgente\b|\bcorra\b|vagas limitadas", "Pressão ou urgência artificial", "bloqueante"),
    (r"site (?:é |está )?(?:ruim|feio|horr[ií]vel|p[eé]ssimo|amador)", "Desqualifica o site da empresa", "bloqueante"),
    (r"ficando para tr[aá]s|seus concorrentes j[aá]|concorr[eê]ncia est[aá] na frente", "Comparação negativa com concorrentes sem dados", "bloqueante"),
    (r"\bpromo[cç][aã]o\b|oferta especial|desconto exclusivo", "Linguagem excessivamente publicitária", "aviso"),
    (r"!{2,}", "Excesso de exclamações", "aviso"),
    (r"\[[^\]]*\]|\{[^}]*\}", "Campo de modelo não preenchido", "bloqueante"),
]

NO_SITE_CLAIM = re.compile(r"n[aã]o (?:tem|possui|encontrei|achei|identifiquei)(?: um| nenhum)? site", re.I)


def fmt_rating(r: float) -> str:
    return f"{r:.1f}".replace(".", ",")


def greeting(tz: str = "America/Sao_Paulo", now: datetime | None = None) -> str:
    now = now or datetime.now(ZoneInfo(tz))
    h = now.hour
    if 5 <= h < 12:
        return "Bom dia, tudo bem?"
    if 12 <= h < 18:
        return "Boa tarde, tudo bem?"
    return "Boa noite, tudo bem?"


def presence_kind(lead: dict) -> str:
    analysis = lead.get("site_analysis") or {}
    if analysis.get("kind"):
        return analysis["kind"]
    return "sem_site" if not lead.get("website") else "proprio"


def verified_site_observations(lead: dict) -> list[str]:
    analysis = lead.get("site_analysis") or {}
    codes = {i["code"] for i in analysis.get("issues", []) if i.get("basis") == "verificado"}
    return [SITE_OBSERVATIONS[c] for c in OBS_ORDER if c in codes]


def choose_variant(lead: dict) -> str:
    status = lead.get("status")
    if status == "nao_contatar" or lead.get("consent_status") == "opt_out":
        return "opt_out"
    if status == "contato_realizado" and (lead.get("contact_count") or 0) >= 1:
        return "follow_up"
    kind = presence_kind(lead)
    if kind in ("sem_site", "google_descontinuado"):
        return "sem_site"
    if kind == "desconhecido":
        return "responsavel_nao_identificado"
    if kind != "proprio":
        return "presenca_limitada"
    return "site_desatualizado" if verified_site_observations(lead) else "site_existente"


VARIANT_PRESENCE = {
    "sem_site": ("sem_site", "google_descontinuado"),
    "presenca_limitada": ("rede_social", "whatsapp", "agregador_links", "plataforma_terceiros", "google_descontinuado"),
    "site_desatualizado": ("proprio",),
    "site_existente": ("proprio",),
}


def variant_incompatibility(lead: dict, variant: str) -> str | None:
    """Explica por que a variação não combina com os dados (ou None se combina)."""
    allowed = VARIANT_PRESENCE.get(variant)
    kind = presence_kind(lead)
    if allowed and kind not in allowed:
        from .site_analysis import KIND_LABELS
        return f"a presença digital desta empresa é '{KIND_LABELS.get(kind, kind)}'"
    if variant == "site_desatualizado" and not verified_site_observations(lead):
        return "não há problemas verificados no site para citar"
    return None


def _seller_intro(seller: dict) -> str:
    nome = seller.get("primeiro_nome") or seller.get("nome") or "..."
    empresa = (seller.get("empresa") or "").strip()
    exp = (seller.get("experiencia") or "").strip()
    who = f"Meu nome é {nome}" + (f", da {empresa}," if empresa else "")
    return f"{who} e trabalho com desenvolvimento de sites para empresas{(' ' + exp) if exp else ''}."


def _reputation_snippet(lead: dict) -> str:
    rating, reviews = lead.get("rating"), lead.get("reviews_count") or 0
    if rating is not None and rating >= 4.5 and reviews >= 20:
        return f" Vi que vocês têm nota {fmt_rating(rating)} com {reviews} avaliações, um ótimo sinal do trabalho de vocês."
    return ""


def _presence_observation(lead: dict) -> str:
    kind = presence_kind(lead)
    platform = (lead.get("site_analysis") or {}).get("platform") or ""
    return {
        "sem_site": "Procurei e não encontrei um site próprio vinculado ao perfil de vocês.",
        "google_descontinuado": "O link de site do perfil aponta para o site gratuito do Google, um serviço que foi descontinuado em 2024.",
        "rede_social": f"O perfil de vocês direciona para o {platform or 'perfil na rede social'}, mas não encontrei um site próprio.",
        "whatsapp": "O perfil leva direto para o WhatsApp, mas não encontrei um site próprio.",
        "agregador_links": f"O perfil usa um link do {platform or 'agregador de links'}, mas não encontrei um site próprio.",
        "plataforma_terceiros": f"O perfil aponta para a página de vocês no {platform or 'site de terceiros'}, mas não encontrei um site próprio.",
    }.get(kind, "")


def _closing(lead: dict, ask_responsible: bool = True) -> str:
    company = lead.get("name") or "empresa"
    if lead.get("preview_ready"):
        link = f" {lead['preview_url']}" if lead.get("preview_url") else ""
        return (f"Inclusive, preparei uma prévia de como poderia ficar a página da {company}.{link} "
                "Posso te mostrar? É sem compromisso.")
    q = "Você é a pessoa responsável por essa parte? " if ask_responsible and not lead.get("responsible_name") else ""
    return q + "Se fizer sentido, posso te apresentar uma proposta sem compromisso."


def render_template(lead: dict, variant: str, seller: dict, tz: str = "America/Sao_Paulo", now: datetime | None = None) -> str:
    if variant not in VARIANTS:
        raise ValueError(f"Variação desconhecida: {variant}")
    company = lead.get("name") or "sua empresa"
    seg = get_segment(lead.get("segment"))
    b1, b2 = seg.benefits
    hi = greeting(tz, now)
    responsible = lead.get("responsible_name")
    if responsible:
        hi = hi.replace(", tudo bem?", f", {responsible.split()[0]}, tudo bem?")
    intro = _seller_intro(seller)
    if lead.get("source") in ("google_places", "demo"):
        found = f"Encontrei a {company} no Google Maps."
    elif lead.get("city"):
        found = f"Estive pesquisando {seg.label.lower()} em {lead['city']} e encontrei a {company}."
    else:
        found = f"Encontrei a {company} pesquisando empresas da região."
    rep = _reputation_snippet(lead)

    if variant == "sem_site":
        body = f"{_presence_observation(lead) or 'Procurei e não encontrei um site próprio vinculado ao perfil de vocês.'} Um site simples poderia ajudar a {b1} e {b2}."
        return f"{hi} {intro} {found}{rep} {body} {_closing(lead)}"
    if variant == "presenca_limitada":
        body = f"{_presence_observation(lead)} Um site próprio poderia complementar o que vocês já fazem nas redes, ajudando a {b1} e {b2}."
        return f"{hi} {intro} {found}{rep} {body} {_closing(lead)}"
    if variant == "site_desatualizado":
        obs = verified_site_observations(lead)[:2]
        notes = " e ".join(obs) if obs else "alguns pontos que poderiam ser melhorados"
        body = f"Dei uma olhada no site de vocês e notei {notes}. Tenho algumas ideias de melhorias que poderiam ajudar a {b1} e {b2}."
        return f"{hi} {intro} {found}{rep} {body} {_closing(lead)}"
    if variant == "site_existente":
        body = ("Vi o site de vocês. Além de criar sites, também faço novas versões e melhorias. "
                "Se em algum momento vocês pensarem em atualizar ou ampliar o site, posso ajudar.")
        return f"{hi} {intro} {found} {body} Faz sentido conversarmos rapidamente?"
    if variant == "responsavel_nao_identificado":
        return (f"{hi} {intro} {found} Gostaria de falar com a pessoa responsável pela divulgação da empresa "
                "sobre uma ideia de site. Poderia me indicar com quem posso conversar, por favor?")
    if variant == "follow_up":
        return (f"{hi} Passando só para retomar minha mensagem anterior sobre um site para a {company}. "
                "Se não for o momento, sem problema, é só me avisar que não volto a insistir. "
                "Se tiver interesse, posso te mostrar a ideia em poucos minutos.")
    if variant == "resposta_interesse":
        return (f"Que bom, obrigado pelo retorno! Para eu preparar algo alinhado com a {company}, posso te fazer três perguntas rápidas? "
                f"1) O que vocês mais gostariam que o site mostrasse (por exemplo: {seg.site_items})? "
                "2) Vocês já têm um domínio, como www.nomedaempresa.com.br? "
                "3) Qual o melhor dia e horário para conversarmos por uns 15 minutos?")
    if variant == "pedido_informacoes":
        return (f"Claro! Funciona assim: eu crio um site profissional para a {company}, adaptado para celular, com {seg.site_items}. "
                "Antes de falar em valores, entendo o que vocês precisam e apresento uma proposta com prazo e investimento. "
                "Posso te enviar alguns exemplos de trabalhos que já fiz? Se preferir, também podemos conversar por telefone.")
    if variant == "outro_horario":
        return ("Sem problema, obrigado por avisar! Qual dia e horário ficam melhores para você? "
                "Retorno no horário que você preferir.")
    # opt_out
    return ("Entendido, obrigado pelo retorno! Não vou mais enviar mensagens. "
            "Se no futuro precisar de algo relacionado a site, fico à disposição. Tenha um ótimo dia!")


def lint_message(text: str, lead: dict) -> list[dict]:
    """Verifica a mensagem. Retorna avisos {nivel, motivo}."""
    out: list[dict] = []
    for pattern, reason, level in LINT_RULES:
        if re.search(pattern, text, re.I):
            out.append({"nivel": level, "motivo": reason})
    kind = presence_kind(lead)
    if kind == "proprio" and NO_SITE_CLAIM.search(text):
        out.append({"nivel": "bloqueante", "motivo": "A mensagem diz que não há site, mas a empresa tem site próprio informado"})
    if kind == "sem_site" and lead.get("source") in ("csv_importacao", "manual") and NO_SITE_CLAIM.search(text):
        out.append({"nivel": "aviso", "motivo": "A ausência de site veio da planilha/cadastro, não do Google: confirme antes de enviar"})
    if kind == "desconhecido" and NO_SITE_CLAIM.search(text):
        out.append({"nivel": "bloqueante", "motivo": "A mensagem afirma que não há site, mas isso não foi verificado"})
    for m in re.finditer(r"nota\s+(\d[,.]\d)", text, re.I):
        stated = float(m.group(1).replace(",", "."))
        if lead.get("rating") is None or abs(stated - float(lead["rating"])) > 0.05:
            out.append({"nivel": "bloqueante", "motivo": f"Nota citada ({m.group(1)}) não confere com os dados ({lead.get('rating')})"})
    if len(text) > 750:
        out.append({"nivel": "aviso", "motivo": f"Mensagem longa ({len(text)} caracteres). Primeiras mensagens curtas costumam funcionar melhor."})
    return out


def has_blocking(warnings: list[dict]) -> bool:
    return any(w["nivel"] == "bloqueante" for w in warnings)


# ---------------------------------------------------------------------------------------
# Análise comercial determinística (sem IA)
# ---------------------------------------------------------------------------------------
def _br_date(iso: str | None) -> str:
    if not iso or len(iso) < 10:
        return ""
    y, m, d = iso[:10].split("-")
    return f"{d}/{m}/{y}"


def build_facts(lead: dict) -> list[dict]:
    src = {"google_places": "Google Maps", "csv_importacao": "Planilha importada", "manual": "Cadastro manual", "demo": "Dado fictício (demonstração)"}.get(lead.get("source"), lead.get("source"))
    when = _br_date(lead.get("google_fetched_at") or lead.get("created_at"))
    fonte = f"{src}{' em ' + when if when else ''}"
    facts = []

    def f(texto, fonte_=fonte):
        facts.append({"texto": texto, "fonte": fonte_})

    if lead.get("category"):
        f(f"Categoria: {lead['category']}")
    loc = ", ".join(x for x in (lead.get("neighborhood"), lead.get("city"), lead.get("state")) if x)
    if loc:
        f(f"Localização: {loc}")
    if lead.get("rating") is not None:
        f(f"Nota {fmt_rating(lead['rating'])} com {lead.get('reviews_count') or 0} avaliações públicas")
    if lead.get("phone"):
        f(f"Telefone comercial público: {lead['phone']}")
    if lead.get("opening_hours"):
        f("Horário de funcionamento informado no perfil")
    kind = presence_kind(lead)
    analysis = lead.get("site_analysis") or {}
    checked = _br_date(analysis.get("checked_at"))
    if kind == "sem_site":
        f("Nenhum site informado no perfil" if lead.get("source") != "csv_importacao" else "Nenhum site na planilha importada")
    elif kind == "proprio":
        f(f"Site informado: {lead.get('website')}")
        for issue in analysis.get("issues", []):
            if issue.get("basis") == "verificado":
                f(f"{issue['label']} ({issue.get('evidence', '')})".strip(), f"Checagem automática do site em {checked}")
        if analysis.get("skipped_reason"):
            f(f"Site não analisado: {analysis['skipped_reason']}", f"Checagem em {checked}")
    else:
        from .site_analysis import KIND_LABELS
        f(f"{KIND_LABELS.get(kind, kind)}: {lead.get('website')}")
    if lead.get("business_status") and lead["business_status"] != "OPERATIONAL":
        f(f"Situação no Google: {lead['business_status']}")
    return facts


def build_hypotheses(lead: dict) -> list[str]:
    seg = get_segment(lead.get("segment"))
    hyps = [f"Um site poderia ajudar a {seg.benefits[0]} e {seg.benefits[1]} (benefício típico de {seg.label.lower()}, não verificado para esta empresa)."]
    if lead.get("phone_kind"):
        hyps.append(Phone(lead.get("phone") or "", None, lead.get("phone_e164"), lead["phone_kind"]).whatsapp_hypothesis + ".")
    for issue in (lead.get("site_analysis") or {}).get("issues", []):
        if issue.get("basis") == "hipotese":
            hyps.append(f"{issue['label']}: {issue.get('evidence', '')}")
    if (lead.get("reviews_count") or 0) >= 100:
        hyps.append("O volume de avaliações sugere um negócio com movimento constante de clientes.")
    return hyps


def build_analysis(lead: dict) -> dict:
    seg = get_segment(lead.get("segment"))
    company = lead.get("name") or "A empresa"
    kind = presence_kind(lead)
    rep = ""
    if lead.get("rating") is not None:
        rep = f", com nota {fmt_rating(lead['rating'])} e {lead.get('reviews_count') or 0} avaliações"
    presence_phrase = {
        "sem_site": "não tem site próprio identificado",
        "google_descontinuado": "aponta para o site gratuito do Google, que foi descontinuado",
        "rede_social": "usa rede social no lugar de um site próprio",
        "whatsapp": "usa link de WhatsApp no lugar de um site próprio",
        "agregador_links": "usa um agregador de links no lugar de um site próprio",
        "plataforma_terceiros": "depende de uma página em plataforma de terceiros",
        "proprio": "tem site próprio" + (" com pontos de melhoria verificados" if verified_site_observations(lead) else ""),
        "desconhecido": "a presença digital ainda não foi verificada",
    }.get(kind, "")
    city = f" em {lead['city']}" if lead.get("city") else ""
    resumo = f"{company}{city}: presença no Google Maps{rep}; {presence_phrase}."
    justificativa = (
        f"Para {seg.label.lower()}, um site costuma reunir {seg.site_items}. "
        + ("Como não identificamos um site próprio, a oportunidade é oferecer uma página que concentre essas informações e facilite o contato."
           if kind not in ("proprio", "desconhecido") else
           "Antes de abordar, confirme no Google se a empresa tem site."
           if kind == "desconhecido" else
           "A oportunidade é propor melhorias específicas, baseadas apenas nos pontos verificados na checagem.")
    )
    return {
        "resumo": resumo,
        "fatos_verificados": build_facts(lead),
        "hipoteses": build_hypotheses(lead),
        "justificativa": justificativa,
        "abordagem_sugerida": choose_variant(lead),
        "cuidados": [
            "Não afirmar que a empresa perde clientes ou dinheiro: não há dados sobre isso.",
            "Citar apenas fatos verificados; hipóteses servem para preparar a conversa.",
        ],
    }
