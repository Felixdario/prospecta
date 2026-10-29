"""Recomendação de canal de contato por lead.

Por que existe: o telefone do perfil do Google muitas vezes é fixo ou não tem WhatsApp. O canal
certo depende do que a própria empresa publicou:
- WhatsApp que aparece em um link wa.me do site, do Linktree ou no campo de site do Google (verificado);
- Instagram (no Brasil, 94% dos pequenos negócios têm perfil, segundo o Sebrae, e é por onde os
  clientes já falam com eles);
- e-mail publicado no site;
- formulário de contato do site;
- ligação (o telefone do Google quase sempre é atendido em horário comercial).
A ordem muda por país: nos EUA e no Canadá a ligação vem primeiro (regras sobre mensagens de texto).
"""
from __future__ import annotations

import re
from urllib.parse import quote, urlparse

from .phones import Phone

CHANNEL_LABELS = {
    "whatsapp": "WhatsApp",
    "instagram": "Direct do Instagram",
    "facebook": "Messenger do Facebook",
    "email": "E-mail",
    "formulario": "Formulário do site",
    "ligacao": "Ligação",
}
ALL_CHANNELS = tuple(CHANNEL_LABELS)
WRITTEN_CHANNELS = ("whatsapp", "instagram", "facebook", "email", "formulario")


def _instagram(lead: dict) -> str | None:
    links = lead.get("social_links") or {}
    return links.get("Instagram") or ((lead.get("site_analysis") or {}).get("contacts") or {}).get("instagram")


def _facebook(lead: dict) -> str | None:
    links = lead.get("social_links") or {}
    found = links.get("Facebook") or ((lead.get("site_analysis") or {}).get("contacts") or {}).get("facebook")
    if found:
        return found
    site = lead.get("website") or ""
    host = (urlparse(site if "://" in site else "https://" + site).hostname or "").lower()
    return site if host.endswith("facebook.com") or host == "fb.com" else None


facebook_page = _facebook


def messenger_url(page: str | None) -> str | None:
    """m.me/<página> abre a conversa no Messenger; páginas sem nome de usuário abrem a própria página."""
    if not page:
        return None
    p = urlparse(page if "://" in page else "https://" + page)
    parts = [x for x in p.path.split("/") if x]
    if parts and parts[0] not in ("profile.php", "pages", "people", "groups") and re.match(r"^[A-Za-z0-9.\-]{3,80}$", parts[0]):
        return f"https://m.me/{parts[0]}"
    return page


def recommend_channels(lead: dict) -> list[dict]:
    """Lista ordenada de canais disponíveis para o lead, do mais recomendado ao menos."""
    country = (lead.get("country") or "BR").upper()
    out: list[dict] = []
    wa_verified = lead.get("whatsapp_e164")
    wa_source = lead.get("whatsapp_source") or "site"
    wa_blocked = lead.get("whatsapp_status") == "sem_whatsapp"
    phone, kind = lead.get("phone_e164"), lead.get("phone_kind")
    emails = lead.get("emails") or []
    insta = _instagram(lead)
    fb = _facebook(lead)
    signals = (lead.get("site_analysis") or {}).get("signals") or {}
    has_form = bool(signals.get("formulario")) and bool(lead.get("website"))

    source_label = {"site": "publicado pela empresa no site ou na página de links", "manual": "informado por você",
                    "planilha": "vindo da planilha importada", "cadastro": "informado no cadastro"}.get(wa_source, "publicado pela empresa")
    if wa_verified and not (wa_blocked and wa_verified == phone):
        out.append({"key": "whatsapp", "target": wa_verified, "basis": "verificado",
                    "reason": f"WhatsApp {source_label}."})
    if insta:
        out.append({"key": "instagram", "target": insta, "basis": "verificado",
                    "reason": "Perfil do Instagram da empresa. Muitos negócios respondem mais rápido pelo Direct do que por telefone."})
    if fb:
        out.append({"key": "facebook", "target": fb, "basis": "verificado",
                    "reason": "Página da empresa no Facebook. Clique em \"Copiar e abrir\" e cole no Messenger (botão \"Enviar mensagem\" da página)."})
    if phone and not wa_verified and not wa_blocked and kind in ("celular", "fixo", "indefinido") and country != "US" and country != "CA":
        out.append({"key": "whatsapp", "target": phone, "basis": "hipotese",
                    "reason": Phone("", None, phone, kind).whatsapp_hypothesis + ". Se o WhatsApp avisar que o número não está no app, marque \"Não tem WhatsApp\"."})
    if phone:
        out.append({"key": "ligacao", "target": phone, "basis": "verificado",
                    "reason": "Telefone do perfil. Na ligação, peça permissão para mandar a ideia pelo WhatsApp ou e-mail do responsável."})
    if emails:
        legal = {"US": " Nos EUA, o e-mail precisa do seu endereço postal e da opção de descadastro (CAN-SPAM).",
                 "CA": " No Canadá, só vale se a empresa publicou o e-mail sem aviso contra ofertas (CASL).",
                 "GB": " No Reino Unido, autônomos precisam ter consentido (PECR): na dúvida, ligue antes."}.get(country, "")
        out.append({"key": "email", "target": emails[0], "basis": "verificado",
                    "reason": f"E-mail da empresa ({', '.join(emails)}).{legal}"})
    if has_form:
        out.append({"key": "formulario", "target": lead.get("website"), "basis": "verificado",
                    "reason": "O site da empresa tem formulário de contato."})

    order = {"BR": ["whatsapp", "instagram", "facebook", "ligacao", "email", "formulario"],
             "US": ["ligacao", "email", "formulario", "facebook", "instagram", "whatsapp"],
             "CA": ["ligacao", "email", "formulario", "facebook", "instagram", "whatsapp"],
             # Reino Unido (autônomos contam como pessoa física no PECR) e Austrália (Spam Act): ligação e formulário primeiro
             "GB": ["ligacao", "formulario", "email", "facebook", "instagram", "whatsapp"],
             "AU": ["ligacao", "formulario", "email", "facebook", "instagram", "whatsapp"]}.get(
        country, ["whatsapp", "email", "instagram", "facebook", "ligacao", "formulario"])

    def rank(c: dict) -> tuple:
        # WhatsApp verificado sempre antes do WhatsApp suposto; dentro do país, segue a ordem acima.
        return (order.index(c["key"]), 0 if c["basis"] == "verificado" else 1)

    # WhatsApp suposto (telefone do Google) fica depois da ligação quando o número é fixo
    out.sort(key=rank)
    if kind == "fixo":
        out.sort(key=lambda c: (c["key"] == "whatsapp" and c["basis"] == "hipotese", rank(c)))
    for c in out:
        c["label"] = CHANNEL_LABELS[c["key"]]
        c["available"] = True
    return out


def channel_options(lead: dict) -> list[dict]:
    """Todos os canais: primeiro os disponíveis (na ordem recomendada), depois os que ainda faltam
    contato. Você pode escolher qualquer um; nos que faltam, a página pede o contato."""
    country = (lead.get("country") or "BR").upper()
    available = recommend_channels(lead)
    keys = {c["key"] for c in available}
    us_ca = country in ("US", "CA")
    missing_reason = {
        "whatsapp": ("Nos EUA e no Canadá, mensagem de texto comercial para celular exige consentimento (TCPA/CASL). "
                     "Use só um WhatsApp que a empresa te passou ou autorizou.") if us_ca else
                    ("O número do Google não tem WhatsApp. Se a empresa te passar outro número, adicione."
                     if lead.get("whatsapp_status") == "sem_whatsapp" or lead.get("whatsapp_source") == "descartado"
                     else "Nenhum WhatsApp encontrado. Adicione o número se encontrar (ex.: na bio do Instagram)."),
        "instagram": "Instagram não encontrado. Use \"Procurar o Instagram\" e salve o @ da empresa.",
        "facebook": "Página do Facebook não encontrada. Se achar, salve o link da página.",
        "email": "Nenhum e-mail encontrado. Digite o e-mail que a empresa publica (site, Facebook) ou te passou."
                 + (" Fora do Brasil o sistema não lê e-mails de sites; a escolha do endereço é sua." if country != "BR" else ""),
        "formulario": "Não achamos formulário na página inicial do site; pode haver em outra página (ex.: Contato)."
                      if lead.get("website") and not _facebook(lead) == lead.get("website") else "A empresa não tem site com formulário.",
        "ligacao": "Sem telefone cadastrado.",
    }
    out = list(available)
    for key in ALL_CHANNELS:
        if key not in keys:
            target = lead.get("website") if key == "formulario" and lead.get("website") and _facebook(lead) != lead.get("website") else None
            out.append({"key": key, "target": target, "basis": "ausente", "available": False,
                        "label": CHANNEL_LABELS[key], "reason": missing_reason[key]})
    return out


HANDLE_RE = re.compile(r"^[A-Za-z0-9._]{1,30}$")
RESERVED = {"p", "reel", "reels", "explore", "stories", "accounts", "tv", "direct"}


def normalize_instagram(value: str) -> str | None:
    """Aceita o link do perfil, "@empresa" ou "empresa"; devolve https://www.instagram.com/empresa/ ou None."""
    v = (value or "").strip()
    if not v:
        return None
    if v.startswith("@"):
        v = v[1:]
    if HANDLE_RE.match(v) and "." not in v[:1]:
        handle = v
    else:
        url = v if "://" in v else "https://" + v
        p = urlparse(url)
        host = (p.hostname or "").lower()
        if host not in ("instagram.com", "www.instagram.com", "m.instagram.com"):
            return None
        parts = [x for x in p.path.split("/") if x]
        if not parts or parts[0].lower() in RESERVED or not HANDLE_RE.match(parts[0]):
            return None
        handle = parts[0]
    return f"https://www.instagram.com/{handle}/"


def normalize_facebook(value: str) -> str | None:
    """Aceita o link da página (facebook.com/empresa, fb.com/empresa, profile.php?id=...) ou só o nome da página."""
    v = (value or "").strip()
    if not v:
        return None
    if v.startswith("@"):
        v = v[1:]
    if re.match(r"^[A-Za-z0-9.\-]{3,80}$", v) and "." not in v[:1] and not v.lower().endswith((".com", ".com.br")):
        return f"https://www.facebook.com/{v}"
    p = urlparse(v if "://" in v else "https://" + v)
    host = (p.hostname or "").lower()
    if host not in ("facebook.com", "www.facebook.com", "m.facebook.com", "web.facebook.com", "fb.com", "www.fb.com"):
        return None
    parts = [x for x in p.path.split("/") if x]
    if not parts:
        return None
    if parts[0] == "pg" and len(parts) > 1:
        parts = parts[1:2]
    if parts[0] == "profile.php":
        ident = re.search(r"(?:^|&)id=(\d+)", p.query or "")
        return f"https://www.facebook.com/profile.php?id={ident.group(1)}" if ident else None
    if parts[0] in ("sharer", "share", "groups", "events", "watch", "login", "dialog", "plugins", "tr"):
        return None
    return "https://www.facebook.com/" + "/".join(parts[:3])


def instagram_search_url(lead: dict) -> str:
    """Busca no Google pelo Instagram da empresa (o usuário abre e confere)."""
    q = f"\"{lead.get('name') or ''}\" {lead.get('city') or ''} instagram"
    return "https://www.google.com/search?q=" + quote(q.strip())


def best_channel(lead: dict) -> str | None:
    channels = recommend_channels(lead)
    return channels[0]["key"] if channels else None
