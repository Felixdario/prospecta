"""Análise comercial determinística e mensagens de abordagem.

- Fatos verificados vêm apenas dos dados coletados (Google/planilha/checagem do site).
- Hipóteses ficam separadas e rotuladas.
- As mensagens usam somente observações VERIFICADAS e passam por um verificador de
  linguagem (sem promessas, pressão, exageros ou afirmações sem dados).

Princípios de abordagem (veja docs/ABORDAGEM.md, com as fontes):
- Começar pela empresa, não pelo vendedor: a primeira linha é o que aparece na notificação.
- Mensagem curta no WhatsApp/Instagram (até ~350 caracteres) e e-mail de 50 a 125 palavras.
- Uma pergunta de interesse, fácil de responder ("Posso te mandar...?"), em vez de pedir reunião.
- Oferecer algo concreto e gratuito (uma ideia ou prévia do site) antes de pedir qualquer coisa.
- Pedir permissão antes de mandar links; no máximo dois follow-ups, cada um com algo novo.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .countries import get_country
from .phones import Phone
from .segments import get_segment

VARIANTS: dict[str, str] = {
    "abertura_curta": "Abertura curta (pergunta pelo responsável)",
    "sem_site": "Empresa sem site identificado",
    "presenca_limitada": "Presença digital limitada (rede social, link ou plataforma)",
    "site_desatualizado": "Site com oportunidades de melhoria verificadas",
    "site_existente": "Site próprio sem problemas evidentes",
    "responsavel_nao_identificado": "Responsável ainda não identificado",
    "roteiro_ligacao": "Roteiro para ligação (pedir permissão)",
    "follow_up": "Follow-up com proposta concreta",
    "follow_up_final": "Último contato (encerramento educado)",
    "resposta_interesse": "Respondeu demonstrando interesse",
    "pedido_informacoes": "Pediu mais informações",
    "outro_horario": "Pediu contato em outro horário",
    "opt_out": "Não deseja receber novas mensagens",
}
COLD_VARIANTS = ("abertura_curta", "sem_site", "presenca_limitada", "site_desatualizado", "site_existente",
                 "responsavel_nao_identificado")
PROSPECTING_VARIANTS = COLD_VARIANTS + ("roteiro_ligacao", "follow_up", "follow_up_final")

CHANNELS = ("whatsapp", "instagram", "facebook", "email", "formulario", "ligacao")
SHORT_CHANNELS = ("whatsapp", "instagram", "facebook", "formulario")

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
SITE_OBSERVATIONS_EN = {
    "site_fora_do_ar": "the site didn't load when I tried to open it",
    "erro_http": "the site returned an error when I tried to open it",
    "pagina_em_construcao": "the page shows an \"under construction\" notice",
    "tecnologia_obsoleta": "it uses older technology that doesn't work well in current browsers",
    "sem_meta_viewport": "it isn't set up to adapt to phone screens",
    "dominio_gratuito": "it's on a free subdomain rather than your own domain",
    "sem_https": "it doesn't use HTTPS yet, so some browsers show a \"Not secure\" warning",
    "sem_contato_direto": "there's no direct call or message button on the homepage",
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
    # Inglês
    (r"losing\s+(?:\w+\s+)?(?:customers|clients|money|sales|business)", "Afirma que a empresa perde clientes ou dinheiro sem dados", "bloqueante"),
    (r"\bguarantee[ds]?\b", "Promessa ou garantia de resultado", "bloqueante"),
    (r"\bdouble (?:your|the)\b|\btriple (?:your|the)\b|skyrocket|\b10x\b", "Promessa exagerada de resultado", "bloqueante"),
    (r"act now|limited time|last chance|today only|\burgent\b|don'?t miss out", "Pressão ou urgência artificial", "bloqueante"),
    (r"(?:website|site) (?:is |looks )?(?:bad|ugly|terrible|awful|amateur|outdated)", "Desqualifica o site da empresa", "bloqueante"),
    (r"your competitors|falling behind|left behind", "Comparação negativa com concorrentes sem dados", "bloqueante"),
    (r"special offer|exclusive discount", "Linguagem excessivamente publicitária", "aviso"),
]

NO_SITE_CLAIM = re.compile(
    r"n[aã]o (?:tem|t[eê]m|possui|possuem|encontrei|achei|identifiquei)(?: um| nenhum)? site"
    r"|ainda n[aã]o t[eê]m um site"
    r"|(?:couldn'?t|could not|didn'?t|did not|can'?t|cannot) find (?:a |any )?(?:website|site)"
    r"|(?:don'?t|do not|doesn'?t|does not) have (?:a |any )?(?:website|site)|\bno website\b",
    re.I,
)
OPT_OUT_HINT = re.compile(r"responder .{0,6}n[aã]o|n[aã]o (?:envio|mando) mais|won'?t (?:email|reach out|contact)|reply \"?no", re.I)


def fmt_rating(r: float, lang: str = "pt") -> str:
    return f"{r:.1f}" if lang == "en" else f"{r:.1f}".replace(".", ",")


def lead_language(lead: dict) -> str:
    if lead.get("language") in ("pt", "en"):
        return lead["language"]
    return get_country(lead.get("country")).message_language


def local_now(lead: dict | None, tz: str = "America/Sao_Paulo") -> datetime:
    """Hora local da empresa: usa o fuso informado pelo Google; senão, o fuso do sistema."""
    offset = (lead or {}).get("utc_offset_minutes")
    if offset is not None:
        return datetime.now(timezone(timedelta(minutes=int(offset))))
    return datetime.now(ZoneInfo(tz))


def greeting(tz: str = "America/Sao_Paulo", now: datetime | None = None, lead: dict | None = None) -> str:
    now = now or local_now(lead, tz)
    h = now.hour
    if 5 <= h < 12:
        return "Bom dia"
    if 12 <= h < 18:
        return "Boa tarde"
    return "Boa noite"


def presence_kind(lead: dict) -> str:
    analysis = lead.get("site_analysis") or {}
    if analysis.get("kind"):
        return analysis["kind"]
    return "sem_site" if not lead.get("website") else "proprio"


def _verified_codes(lead: dict) -> list[str]:
    analysis = lead.get("site_analysis") or {}
    codes = {i["code"] for i in analysis.get("issues", []) if i.get("basis") == "verificado"}
    return [c for c in OBS_ORDER if c in codes]


def verified_site_observations(lead: dict, lang: str = "pt") -> list[str]:
    table = SITE_OBSERVATIONS_EN if lang == "en" else SITE_OBSERVATIONS
    return [table[c] for c in _verified_codes(lead)]


def choose_variant(lead: dict, channel: str | None = None) -> str:
    status = lead.get("status")
    if status == "nao_contatar" or lead.get("consent_status") == "opt_out":
        return "opt_out"
    if status == "contato_realizado" and (lead.get("contact_count") or 0) >= 1:
        return "follow_up_final" if (lead.get("contact_count") or 0) >= 2 else "follow_up"
    if channel == "ligacao":
        return "roteiro_ligacao"
    kind = presence_kind(lead)
    if channel is None and (lead.get("country") or "BR") in ("US", "CA") and lead.get("phone_e164") \
            and status in (None, "identificado", "qualificado", "aguardando_revisao"):
        # Nos EUA/Canadá o primeiro contato recomendado é a ligação (texto de marketing exige consentimento).
        return "roteiro_ligacao"
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
    if variant == "roteiro_ligacao" and not lead.get("phone_e164"):
        return "não há telefone válido para ligar"
    return None


# ---------------------------------------------------------------------------------------
# Artigo do nome da empresa ("a Barbearia", "o Restaurante")
# ---------------------------------------------------------------------------------------
_MASC = {"restaurante", "salao", "studio", "estudio", "espaco", "instituto", "centro", "consultorio", "escritorio", "bar",
         "buffet", "atelie", "hotel", "mercado", "emporio", "acougue", "posto", "colegio", "pet", "petshop", "laboratorio",
         "box", "ct", "lava", "lava-jato", "auto", "grupo", "armazem", "bistro", "cafe", "boteco", "sobrado", "recanto"}
_FEM_EXCEPTIONS = {"dia", "programa", "sistema", "clima", "tema", "problema"}


def _articles(company: str | None) -> dict | None:
    """Retorna {"a": "a"/"o", "da": "da"/"do", "pela": "pela"/"pelo"} ou None quando não dá para saber."""
    if not company:
        return None
    first = unicodedata.normalize("NFKD", company.split()[0].lower())
    first = "".join(c for c in first if not unicodedata.combining(c)).strip(".,'\"")
    if first in _MASC:
        return {"a": "o", "da": "do", "pela": "pelo"}
    if first.endswith("a") and first not in _FEM_EXCEPTIONS:
        return {"a": "a", "da": "da", "pela": "pela"}
    return None


def _company_ref(lead: dict, form: str, fallback: str) -> str:
    """Ex.: form="pela" → "pela Barbearia X"; sem artigo conhecido → fallback ("de vocês")."""
    company = lead.get("name")
    art = _articles(company)
    return f"{art[form]} {company}" if art else fallback


# ---------------------------------------------------------------------------------------
# Português
# ---------------------------------------------------------------------------------------
def _first_name(lead: dict) -> str | None:
    r = (lead.get("responsible_name") or "").strip()
    return r.split()[0] if r else None


def _hello_pt(lead: dict, email: bool = False) -> str:
    name = _first_name(lead)
    word = "Olá" if email else "Oi"
    return f"{word}, {name}, tudo bem?" if name else f"{word}, tudo bem?"


def _good_reputation(lead: dict) -> bool:
    return lead.get("rating") is not None and lead["rating"] >= 4.5 and (lead.get("reviews_count") or 0) >= 20


def _seen_pt(lead: dict) -> str:
    seg = get_segment(lead.get("segment"))
    rep = f": nota {fmt_rating(lead['rating'])} com {lead.get('reviews_count')} avaliações, parabéns pelo trabalho!" if _good_reputation(lead) else "."
    if lead.get("source") in ("google_places", "demo"):
        who = _company_ref(lead, "a", "o perfil de vocês")
        return f"Vi {who} no Google{rep}" if rep != "." else f"Vi {who} no Google Maps."
    where = f" em {lead['city']}" if lead.get("city") else " da região"
    return f"Conheci {_company_ref(lead, 'a', 'vocês')} pesquisando {seg.label.lower()}{where}{rep if rep != '.' else '.'}"


def _who_pt(seller: dict) -> str:
    nome = seller.get("primeiro_nome") or seller.get("nome") or "..."
    empresa = (seller.get("empresa") or "").strip()
    exp = (seller.get("experiencia") or "").strip()
    return f"Sou o {nome}{', da ' + empresa if empresa else ''} e faço sites para negócios locais{' ' + exp if exp else ''}."


def _observation_pt(lead: dict, short: bool = True) -> str:
    kind = presence_kind(lead)
    platform = (lead.get("site_analysis") or {}).get("platform") or ""
    if kind == "proprio":
        obs = verified_site_observations(lead)[: 1 if short else 2]
        return f"Dei uma olhada no site e notei {' e '.join(obs)}." if obs else "Dei uma olhada no site de vocês."
    return {
        "sem_site": "Reparei que vocês ainda não têm um site próprio.",
        "google_descontinuado": "Reparei que o link de site do perfil aponta para o site gratuito do Google, que foi desativado em 2024.",
        "rede_social": f"Reparei que o perfil no Google leva para o {platform or 'perfil na rede social'} e não para um site próprio.",
        "whatsapp": "Reparei que o perfil no Google leva direto para o WhatsApp, sem um site próprio.",
        "agregador_links": f"Reparei que o perfil usa um link do {platform or 'agregador de links'} no lugar de um site próprio.",
        "plataforma_terceiros": f"Reparei que o perfil leva para a página de vocês no {platform or 'site de terceiros'}, sem um site próprio.",
    }.get(kind, "")


def _offer_pt(lead: dict, variant: str) -> str:
    if lead.get("preview_ready"):
        return "Montei uma prévia de como poderia ficar o site de vocês. Posso te mandar o link?"
    if variant == "site_desatualizado":
        return "Posso te mandar 2 ou 3 sugestões de melhoria? Sem compromisso."
    if variant == "site_existente":
        return "Se um dia pensarem em renovar o site, posso te mandar algumas ideias?"
    return "Posso te mandar uma ideia de como ficaria o site de vocês? Sem compromisso."


def _signature(seller: dict, lang: str) -> str:
    lines = [seller.get("nome") or seller.get("primeiro_nome") or ""]
    if seller.get("empresa"):
        lines.append(seller["empresa"])
    if seller.get("whatsapp"):
        lines.append(("WhatsApp: " if lang == "pt" else "Phone/WhatsApp: ") + seller["whatsapp"])
    if seller.get("portfolio"):
        lines.append(("Trabalhos: " if lang == "pt" else "Portfolio: ") + seller["portfolio"])
    if seller.get("endereco"):
        lines.append(seller["endereco"])
    return "\n".join(x for x in lines if x)


def email_footer(lead: dict, seller: dict, variant: str) -> str:
    """Assinatura e, em mensagens de prospecção, a forma de pedir para não receber mais e-mails."""
    lang = lead_language(lead)
    footer = _signature(seller, lang)
    if variant in PROSPECTING_VARIANTS:
        footer += "\n\n" + (f"This email is a business proposal for website services. {OPT_OUT_EN_EMAIL}" if lang == "en" else OPT_OUT_PT_EMAIL)
    return footer


OPT_OUT_PT_EMAIL = "Se não quiser receber outros e-mails meus, é só responder \"não\" que eu não envio mais."
OPT_OUT_EN = " If not, no worries, I won't reach out again."
OPT_OUT_EN_EMAIL = "If you'd rather not hear from me, just reply \"no\" and I won't email you again."


def _render_pt(lead: dict, variant: str, seller: dict, tz: str, now: datetime | None, channel: str) -> str:
    seg = get_segment(lead.get("segment"))
    b1, b2 = seg.benefits
    email = channel == "email"
    nome = seller.get("primeiro_nome") or seller.get("nome") or "..."
    company_by = _company_ref(lead, "pela", "pela empresa")

    if variant == "roteiro_ligacao":
        kind = presence_kind(lead)
        obs = verified_site_observations(lead)[:1]
        if kind in ("sem_site", "google_descontinuado"):
            hook = "não encontrei um site próprio de vocês"
        elif kind == "proprio" and obs:
            hook = f"notei no site {obs[0]}"
        elif kind == "proprio":
            hook = "vi o site de vocês e tive algumas ideias"
        elif kind == "desconhecido":
            hook = "queria entender como vocês aparecem hoje na internet"
        else:
            hook = "vi que vocês estão nas redes, mas sem um site próprio"
        rep = f" (nota {fmt_rating(lead['rating'])}, parabéns!)" if _good_reputation(lead) else ""
        return ("Roteiro de ligação. Objetivo: conseguir permissão e o melhor contato, não vender por telefone.\n"
                f"1. \"{greeting(tz, now, lead)}! Aqui é o {nome}. Falo com o responsável {company_by}?\" "
                "Se não for: \"Com quem eu falo sobre a divulgação de vocês, e qual o melhor horário?\"\n"
                f"2. \"Vou ser rápido: vi vocês no Google{rep} e {hook}. Eu faço sites para negócios locais.\"\n"
                "3. \"Posso te mandar uma ideia de como ficaria o site de vocês? Qual o melhor WhatsApp ou e-mail?\"\n"
                "4. Anote o WhatsApp ou e-mail no Prospecta e clique em \"Registrar que autorizou contato\".\n"
                "Se não houver interesse: agradeça, registre como \"Sem interesse\" e não ligue de novo.")

    if variant == "abertura_curta":
        text = (f"{_hello_pt(lead)} Falo com o responsável {company_by}? Sou o {nome} e faço sites para negócios locais. "
                "Tive uma ideia para a presença de vocês no Google, posso te contar?")
    elif variant == "responsavel_nao_identificado":
        text = (f"{_hello_pt(lead, email)} {_seen_pt(lead)} {_who_pt(seller)} "
                "Com quem eu falo sobre o site ou a divulgação de vocês?")
    elif variant in ("sem_site", "presenca_limitada", "site_desatualizado", "site_existente"):
        if variant == "presenca_limitada":
            platform = (lead.get("site_analysis") or {}).get("platform")
            benefit = (f"Um site próprio poderia complementar o {platform} e ajudar a {b1}." if platform
                       else f"Um site próprio poderia ajudar a {b1}.")
        elif variant == "site_existente":
            benefit = "Além de criar sites, também faço novas versões e melhorias."
        else:
            benefit = f"Um site poderia ajudar a {b1}" + (f" e {b2}." if email else ".")
        if email and variant == "site_existente":  # "além de criar sites" só faz sentido depois da apresentação
            text = (f"{_hello_pt(lead, True)}\n\n{_seen_pt(lead)}\n\n{_observation_pt(lead, short=False)}\n\n"
                    f"{_who_pt(seller)} {benefit} {_offer_pt(lead, variant)}")
        elif email:
            text = (f"{_hello_pt(lead, True)}\n\n{_seen_pt(lead)}\n\n{_observation_pt(lead, short=False)} {benefit}\n\n"
                    f"{_who_pt(seller)} {_offer_pt(lead, variant)}")
        else:
            text = f"{_hello_pt(lead)} {_seen_pt(lead)} {_observation_pt(lead)} {_who_pt(seller)} {benefit} {_offer_pt(lead, variant)}"
    elif variant == "follow_up":
        if presence_kind(lead) == "proprio":
            idea = f"a ideia é uma versão nova do site, com {seg.site_items}, adaptada ao celular e com botão de WhatsApp"
        else:
            idea = f"a ideia é um site simples para vocês, com {seg.site_items}, ligado ao perfil do Google e com botão de WhatsApp"
        text = (f"{_hello_pt(lead, email)} Voltando à minha mensagem: {idea}. Quer que eu te mande um exemplo? "
                "Se não for o momento, sem problema.")
    elif variant == "follow_up_final":
        text = (f"{_hello_pt(lead, email)} Vou parar de mandar mensagem por aqui para não incomodar. "
                "Se em algum momento quiserem um site, é só me chamar. Sucesso para vocês!")
    elif variant == "resposta_interesse":
        text = (f"Que bom, obrigado pelo retorno! Para eu preparar algo alinhado com vocês, posso te fazer três perguntas rápidas? "
                f"1) O que vocês mais gostariam que o site mostrasse (por exemplo: {seg.site_items})? "
                "2) Vocês já têm um domínio, como www.nomedaempresa.com.br? "
                "3) Qual o melhor dia e horário para conversarmos por uns 15 minutos?")
    elif variant == "pedido_informacoes":
        text = (f"Claro! Funciona assim: eu crio um site profissional para vocês, adaptado para celular, com {seg.site_items}. "
                "Antes de falar em valores, entendo o que vocês precisam e apresento uma proposta com prazo e investimento. "
                "Posso te enviar alguns exemplos de trabalhos que já fiz?" + (f" Estão aqui: {seller['portfolio']}" if seller.get("portfolio") else ""))
    elif variant == "outro_horario":
        text = "Sem problema, obrigado por avisar! Qual dia e horário ficam melhores para você? Retorno no horário que você preferir."
    else:  # opt_out
        text = ("Entendido, obrigado pelo retorno! Não vou mais enviar mensagens. "
                "Se no futuro precisar de algo relacionado a site, fico à disposição. Tenha um ótimo dia!")
    if email:
        text = f"{text}\n\n{email_footer(lead, seller, variant)}"
    return text


# ---------------------------------------------------------------------------------------
# Inglês (EUA, Canadá, Reino Unido, Austrália)
# ---------------------------------------------------------------------------------------
def _hello_en(lead: dict, email: bool = False) -> str:
    name = _first_name(lead)
    if email:
        return f"Hi {name}, hope you're doing well." if name else "Hi, hope you're doing well."
    return f"Hi {name}!" if name else "Hi there!"


def _seen_en(lead: dict) -> str:
    company = lead.get("name") or "your business"
    label = get_segment(lead.get("segment")).text("en")[0]
    rep = (f": {fmt_rating(lead['rating'], 'en')} stars from {lead.get('reviews_count')} reviews, great work!"
           if _good_reputation(lead) else ".")
    if lead.get("source") in ("google_places", "demo"):
        return f"I came across {company} on Google{rep}" if rep != "." else f"I came across {company} on Google Maps."
    where = f" in {lead['city']}" if lead.get("city") else ""
    return f"I came across {company} while looking at {label.lower()}{where}{rep}"


def _who_en(seller: dict) -> str:
    nome = seller.get("primeiro_nome") or seller.get("nome") or "..."
    empresa = (seller.get("empresa") or "").strip()
    exp = (seller.get("experiencia_en") or "").strip()
    who = f"I'm {nome}{', from ' + empresa + ',' if empresa else ''} and I"
    return f"{who}'ve been building websites for local businesses {exp}." if exp else f"{who} build websites for local businesses."


def _observation_en(lead: dict, short: bool = True) -> str:
    kind = presence_kind(lead)
    platform = (lead.get("site_analysis") or {}).get("platform") or ""
    if kind == "proprio":
        obs = verified_site_observations(lead, "en")[: 1 if short else 2]
        return f"I took a look at your website and noticed {' and '.join(obs)}." if obs else "I took a look at your website."
    return {
        "sem_site": "I couldn't find a website linked to your profile.",
        "google_descontinuado": "The website link on your profile points to Google's free business site, which Google discontinued in 2024.",
        "rede_social": f"Your Google profile links to your {platform or 'social media page'}, but I couldn't find a website of your own.",
        "whatsapp": "Your Google profile links straight to WhatsApp, but I couldn't find a website of your own.",
        "agregador_links": f"Your profile uses a {platform or 'link-in-bio'} page instead of a website of your own.",
        "plataforma_terceiros": f"Your profile points to your page on {platform or 'a third-party platform'} instead of a website of your own.",
    }.get(kind, "")


def _offer_en(lead: dict, variant: str) -> str:
    if lead.get("preview_ready"):
        return "I put together a quick preview of what your site could look like. Want me to send you the link?"
    if variant == "site_desatualizado":
        return "Would it be helpful if I sent you 2 or 3 quick suggestions? No obligation."
    if variant == "site_existente":
        return "If you ever think about refreshing it, would it be useful if I sent a few ideas?"
    return "Would it help if I sent you an idea of what yours could look like?"


def _render_en(lead: dict, variant: str, seller: dict, channel: str) -> str:
    company = lead.get("name") or "your business"
    label, (b1, b2), items = get_segment(lead.get("segment")).text("en")
    email = channel == "email"
    nome = seller.get("primeiro_nome") or seller.get("nome") or "..."

    if variant == "roteiro_ligacao":
        kind = presence_kind(lead)
        obs = verified_site_observations(lead, "en")[:1]
        if kind in ("sem_site", "google_descontinuado"):
            hook = "I couldn't find a website for your business"
        elif kind == "proprio" and obs:
            hook = f"I noticed on your website that {obs[0]}"
        elif kind == "proprio":
            hook = "I saw your website and had a few ideas"
        elif kind == "desconhecido":
            hook = "I wanted to learn how you're showing up online today"
        else:
            hook = "I saw you're on social media, but I couldn't find a website of your own"
        rep = f" and saw your {fmt_rating(lead['rating'], 'en')}-star rating" if _good_reputation(lead) else ""
        return ("Roteiro de ligação em inglês. Objetivo: conseguir permissão e o melhor contato, não vender por telefone.\n"
                f"1. \"Hi, this is {nome}. Am I speaking with the owner or manager of {company}?\" "
                "Se não for: \"Who would be the best person to talk to about your marketing, and when's a good time to reach them?\"\n"
                f"2. \"I'll be quick: I came across you on Google{rep}. {hook[0].upper() + hook[1:]}. I build websites for local businesses.\"\n"
                "3. \"Would it be okay if I sent you an idea of what your site could look like? What's the best email for that?\"\n"
                "4. Anote o e-mail no Prospecta e clique em \"Registrar que autorizou contato\".\n"
                "Se não houver interesse: agradeça (\"No problem, thanks for your time!\"), registre como \"Sem interesse\" e não ligue de novo.")

    if variant == "abertura_curta":
        text = (f"Hi! Am I reaching the owner or manager of {company}? I'm {nome} and I build websites for local businesses. "
                "I had an idea for how you show up on Google. Mind if I share it?")
    elif variant == "responsavel_nao_identificado":
        text = f"{_hello_en(lead)} {_seen_en(lead)} {_who_en(seller)} Who would be the best person to talk to about your website or marketing?"
    elif variant in ("sem_site", "presenca_limitada", "site_desatualizado", "site_existente"):
        if variant == "presenca_limitada":
            benefit = (f"A website of your own could complement your social media and help {b1}." if email
                       else f"A site could help {b1}.")
        elif variant == "site_existente":
            benefit = "Besides building new sites, I also do redesigns and improvements."
        else:
            benefit = f"A simple website could help {b1}" + (f" and {b2}." if email else ".")
        if email:
            text = (f"{_hello_en(lead, True)}\n\n{_seen_en(lead)}\n\n{_observation_en(lead, short=False)} {benefit}\n\n"
                    f"{_who_en(seller)} {_offer_en(lead, variant)}")
        else:
            text = f"{_hello_en(lead)} {_seen_en(lead)} {_observation_en(lead)} {_who_en(seller)} {benefit} {_offer_en(lead, variant)}"
    elif variant == "follow_up":
        idea = (f"a refreshed version of your site with {items}, mobile-friendly and with a click-to-call button"
                if presence_kind(lead) == "proprio" else
                f"a simple website for {company} with {items}, linked from your Google profile and with a click-to-call button")
        text = f"Hi again! Quick follow-up: the idea is {idea}. Want me to send you an example? If now isn't a good time, no worries."
    elif variant == "follow_up_final":
        text = (f"Hi! I'll stop reaching out so I don't clutter your messages. If you ever want help with a website, "
                f"just reply here. All the best to the team at {company}!")
    elif variant == "resposta_interesse":
        text = (f"Great, thanks for getting back to me! So I can put together something that fits {company}, may I ask three quick questions? "
                f"1) What would you most like the site to show (for example: {items})? "
                "2) Do you already own a domain, like www.yourbusiness.com? "
                "3) What's a good day and time for a 15-minute call?")
    elif variant == "pedido_informacoes":
        text = (f"Sure! Here's how it works: I build a professional, mobile-friendly website for {company}, with {items}. "
                "Before talking about price, I learn what you need and then send a proposal with timeline and cost. "
                "Can I send you a few examples of sites I've built?" + (f" Here they are: {seller['portfolio']}" if seller.get("portfolio") else ""))
    elif variant == "outro_horario":
        text = "No problem, thanks for letting me know! What day and time work best for you? I'll reach out whenever you prefer."
    else:  # opt_out
        text = ("Understood, thanks for letting me know. I won't send any more messages. "
                "If you ever need help with a website, feel free to reach out. Have a great day!")
    if email:
        text = f"{text}\n\n{email_footer(lead, seller, variant)}"
    elif variant in COLD_VARIANTS and variant != "abertura_curta":
        text += OPT_OUT_EN
    return text


def render_template(lead: dict, variant: str, seller: dict, tz: str = "America/Sao_Paulo", now: datetime | None = None,
                    channel: str = "whatsapp") -> str:
    if variant not in VARIANTS:
        raise ValueError(f"Variação desconhecida: {variant}")
    if channel not in CHANNELS:
        channel = "whatsapp"
    if lead_language(lead) == "en":
        return _render_en(lead, variant, seller, channel)
    return _render_pt(lead, variant, seller, tz, now, channel)


def render_subject(lead: dict, variant: str) -> str:
    """Assunto curto para e-mail (3 a 5 palavras costumam ter mais resposta)."""
    company = lead.get("name") or ""
    en = lead_language(lead) == "en"
    base = {
        "site_desatualizado": f"Ideas for {company}'s website" if en else f"Ideias para o site {_company_ref(lead, 'da', 'de vocês')}",
        "site_existente": f"{company}'s website" if en else f"Site {_company_ref(lead, 'da', 'de vocês')}",
        "responsavel_nao_identificado": "Quick question about your website" if en else "Pergunta rápida sobre o site",
    }.get(variant, f"Website for {company}" if en else f"Site para {_company_ref(lead, 'a', 'vocês')}")
    if variant in ("follow_up", "follow_up_final"):
        return "Re: " + (f"Website for {company}" if en else f"Site para {_company_ref(lead, 'a', 'vocês')}")
    return base


def lint_message(text: str, lead: dict, channel: str | None = None, variant: str | None = None) -> list[dict]:
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
    for m in re.finditer(r"nota\s+(\d[,.]\d)|(\d\.\d)[ -]stars?|rated (\d\.\d)", text, re.I):
        value = next(g for g in m.groups() if g)
        stated = float(value.replace(",", "."))
        if lead.get("rating") is None or abs(stated - float(lead["rating"])) > 0.05:
            out.append({"nivel": "bloqueante", "motivo": f"Nota citada ({value}) não confere com os dados ({lead.get('rating')})"})
    cold = variant in COLD_VARIANTS if variant else False
    if channel in SHORT_CHANNELS and cold and len(text) > 450:
        out.append({"nivel": "aviso", "motivo": f"Mensagem longa para {channel} ({len(text)} caracteres). Primeiras mensagens de até ~350 caracteres costumam ter mais resposta."})
    elif channel is None and len(text) > 750:
        out.append({"nivel": "aviso", "motivo": f"Mensagem longa ({len(text)} caracteres). Primeiras mensagens curtas costumam funcionar melhor."})
    if cold and re.match(r"^\s*(?:(?:oi|ol[aá]|bom dia|boa tarde|boa noite|hi|hello)[^.?!]*[.?!]\s*)?(?:meu nome [eé]|my name is)", text, re.I):
        out.append({"nivel": "aviso", "motivo": "Comece falando da empresa, não de você: a primeira linha é o que aparece na notificação."})
    if channel in SHORT_CHANNELS and cold and re.search(r"https?://", text):
        out.append({"nivel": "aviso", "motivo": "Link na primeira mensagem parece spam vindo de número desconhecido. Peça permissão antes e mande o link depois."})
    if channel == "email":
        words = len(re.findall(r"\w+", text.split("\n\n" + "—")[0]))
        if variant in PROSPECTING_VARIANTS and not OPT_OUT_HINT.search(text):
            out.append({"nivel": "aviso", "motivo": "E-mail sem forma clara de pedir para não receber mais mensagens."})
        if cold and words > 170:
            out.append({"nivel": "aviso", "motivo": f"E-mail longo ({words} palavras). E-mails de 50 a 125 palavras costumam ter mais resposta."})
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
    country = (lead.get("country") or "BR").upper()
    loc = ", ".join(x for x in (lead.get("neighborhood"), lead.get("city"), lead.get("state"),
                                None if country == "BR" else get_country(country).name) if x)
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
    contacts = analysis.get("contacts") or {}
    if lead.get("whatsapp_e164"):
        source = lead.get("whatsapp_source") or "site"
        origem = {"site": "Site ou página de links da empresa", "manual": "Informado por você", "planilha": "Planilha importada",
                  "cadastro": "Cadastro manual"}.get(source, "Site da empresa")
        f(f"WhatsApp{' publicado' if source == 'site' else ''}: {lead['whatsapp_e164']}", origem)
    # a origem de cada contato é dita com honestidade: o que veio do site é "publicado", o resto foi você que informou
    site_emails = {e.lower() for e in contacts.get("emails") or []}
    published = [e for e in lead.get("emails") or [] if e.lower() in site_emails]
    informed = [e for e in lead.get("emails") or [] if e.lower() not in site_emails]
    if published:
        f(f"E-mail publicado: {', '.join(published)}", "Site da empresa")
    if informed:
        f(f"E-mail: {', '.join(informed)}", "Informado por você (cadastro, planilha ou edição)")
    insta = (lead.get("social_links") or {}).get("Instagram") or contacts.get("instagram")
    if insta:
        def norm(u: str) -> str:
            return (u or "").lower().replace("://www.", "://").rstrip("/")
        found = [contacts.get("instagram"), (analysis.get("social_links") or {}).get("Instagram")]
        if any(x and norm(x) == norm(insta) for x in found):
            f(f"Instagram: {insta}", "Link publicado pela empresa")
        else:
            f(f"Instagram: {insta}", "Informado por você")
    if lead.get("whatsapp_status") == "sem_whatsapp":
        f("O telefone do perfil não tem WhatsApp (marcado por você)", "Seu registro")
    if lead.get("business_status") and lead["business_status"] != "OPERATIONAL":
        f(f"Situação no Google: {lead['business_status']}")
    return facts


def build_hypotheses(lead: dict) -> list[str]:
    seg = get_segment(lead.get("segment"))
    hyps = [f"Um site poderia ajudar a {seg.benefits[0]} e {seg.benefits[1]} (benefício típico de {seg.label.lower()}, não verificado para esta empresa)."]
    if lead.get("phone_kind"):
        hyps.append(Phone(lead.get("phone") or "", None, lead.get("phone_e164"), lead["phone_kind"]).whatsapp_hypothesis + ".")
    if (lead.get("country") or "BR").upper() in ("US", "CA"):
        hyps.append("Nos EUA e no Canadá, a ligação costuma ser o primeiro contato mais adequado; mensagens de texto de marketing exigem cuidado com consentimento.")
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
