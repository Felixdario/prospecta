"""Diagnóstico da presença digital a partir do site informado no perfil da empresa.

Princípios:
- Uma única visita à página inicial, com User-Agent identificado, respeitando o robots.txt.
- Nunca acessa redes sociais (Instagram, Facebook etc.): o link é apenas classificado.
- Proteção contra SSRF: só acessa endereços públicos da internet, inclusive após redirecionamentos.
- Cada observação traz a evidência e a base: "verificado" (observado na checagem) ou
  "hipotese" (interpretação que pode estar errada).
"""
from __future__ import annotations

import ipaddress
import re
import socket
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Callable, Protocol
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

MAX_BYTES = 2_000_000

SOCIAL_DOMAINS = {
    "instagram.com": "Instagram", "facebook.com": "Facebook", "fb.com": "Facebook", "fb.me": "Facebook",
    "tiktok.com": "TikTok", "linkedin.com": "LinkedIn", "youtube.com": "YouTube", "youtu.be": "YouTube",
    "twitter.com": "X/Twitter", "x.com": "X/Twitter", "pinterest.com": "Pinterest", "threads.net": "Threads",
    "kwai.com": "Kwai",
}
WHATSAPP_DOMAINS = {"wa.me": "WhatsApp", "api.whatsapp.com": "WhatsApp", "whatsapp.com": "WhatsApp", "wa.link": "WhatsApp"}
LINK_IN_BIO_DOMAINS = {
    "linktr.ee": "Linktree", "beacons.ai": "Beacons", "bio.link": "bio.link", "taplink.cc": "Taplink",
    "campsite.bio": "Campsite", "lnk.bio": "lnk.bio", "msha.ke": "Milkshake", "linkbio.co": "LinkBio",
}
THIRD_PARTY_DOMAINS = {
    "ifood.com.br": "iFood", "goomer.app": "Goomer", "anota.ai": "Anota AI", "aiqfome.com": "aiqfome",
    "booksy.com": "Booksy", "trinks.com": "Trinks", "doctoralia.com.br": "Doctoralia",
    "boaconsulta.com": "BoaConsulta", "avec.app": "Avec", "mercadolivre.com.br": "Mercado Livre",
    "shopee.com.br": "Shopee", "olx.com.br": "OLX", "cardapioweb.com": "Cardápio Web",
    "menudino.com": "MenuDino", "ola.click": "Olaclick", "gendo.app": "Gendo",
    # Estados Unidos e outros países de língua inglesa
    "yelp.com": "Yelp", "doordash.com": "DoorDash", "order.online": "DoorDash", "ubereats.com": "Uber Eats",
    "grubhub.com": "Grubhub", "toasttab.com": "Toast", "opentable.com": "OpenTable", "chownow.com": "ChowNow",
    "menufy.com": "Menufy", "clover.com": "Clover", "vagaro.com": "Vagaro", "styleseat.com": "StyleSeat",
    "mindbodyonline.com": "Mindbody", "schedulicity.com": "Schedulicity", "glossgenius.com": "GlossGenius",
    "nextdoor.com": "Nextdoor", "angi.com": "Angi", "homeadvisor.com": "HomeAdvisor", "thumbtack.com": "Thumbtack",
    "houzz.com": "Houzz", "zocdoc.com": "Zocdoc", "healthgrades.com": "Healthgrades", "avvo.com": "Avvo",
    "yell.com": "Yell", "checkatrade.com": "Checkatrade", "hipages.com.au": "hipages", "yellowpages.com": "Yellow Pages",
}
GOOGLE_DISCONTINUED = {"business.site": "site gratuito do Perfil da Empresa no Google", "negocio.site": "site gratuito do Perfil da Empresa no Google"}
FREE_SUBDOMAINS = {
    "wixsite.com": "Wix (gratuito)", "webnode.page": "Webnode", "webnode.com.br": "Webnode",
    "sites.google.com": "Google Sites", "blogspot.com": "Blogger", "wordpress.com": "WordPress.com",
    "weebly.com": "Weebly", "godaddysites.com": "GoDaddy", "ueniweb.com": "UENI", "comunidades.net": "Comunidades.net",
    "vercel.app": "Vercel", "netlify.app": "Netlify", "github.io": "GitHub Pages", "carrd.co": "Carrd",
    "square.site": "Square Online (gratuito)", "squarespace.com": "Squarespace", "wix.com": "Wix", "jimdosite.com": "Jimdo",
    "mystrikingly.com": "Strikingly", "site123.me": "SITE123", "webflow.io": "Webflow",
}

KIND_LABELS = {
    "sem_site": "Nenhum site informado",
    "proprio": "Site próprio",
    "rede_social": "Rede social no lugar do site",
    "whatsapp": "Link de WhatsApp no lugar do site",
    "agregador_links": "Agregador de links no lugar do site",
    "plataforma_terceiros": "Página em plataforma de terceiros",
    "google_descontinuado": "Site gratuito do Google (serviço descontinuado)",
    "desconhecido": "Presença digital desconhecida (fonte sem campo de site)",
}

CONSTRUCTION_PATTERNS = re.compile(
    r"em constru[cç][aã]o|site em manuten[cç][aã]o|under construction|coming soon|em breve|"
    r"this domain (?:is|may be) for sale|dom[ií]nio (?:est[aá] )?[àa] venda|parked free|domain parking",
    re.I,
)
COPYRIGHT_RE = re.compile(
    r"(?:©|&copy;|&#169;|copyright|todos os direitos reservados)[^0-9]{0,60}((?:19|20)\d{2})(?:\s*[-–]\s*((?:19|20)\d{2}))?",
    re.I,
)


def _host_matches(host: str, domains: dict[str, str]) -> str | None:
    host = host.lower().removeprefix("www.").removeprefix("m.")
    for d, label in domains.items():
        if host == d or host.endswith("." + d):
            return label
    return None


def normalize_url(url: str | None) -> str | None:
    if not url or not str(url).strip():
        return None
    url = str(url).strip()
    if not re.match(r"^https?://", url, re.I):
        url = "http://" + url
    return url


def classify_url(url: str | None) -> tuple[str, str | None]:
    """Retorna (tipo, plataforma) sem acessar a internet."""
    url = normalize_url(url)
    if not url:
        return "sem_site", None
    host = (urlparse(url).hostname or "").lower()
    for kind, table in (
        ("google_descontinuado", GOOGLE_DISCONTINUED),
        ("rede_social", SOCIAL_DOMAINS),
        ("whatsapp", WHATSAPP_DOMAINS),
        ("agregador_links", LINK_IN_BIO_DOMAINS),
        ("plataforma_terceiros", THIRD_PARTY_DOMAINS),
    ):
        label = _host_matches(host, table)
        if label:
            return kind, label
    return "proprio", _host_matches(host, FREE_SUBDOMAINS)


# ---------------------------------------------------------------------------------------
# Acesso HTTP seguro
# ---------------------------------------------------------------------------------------
class UnsafeURL(Exception):
    pass


def assert_public_host(host: str) -> None:
    """Bloqueia endereços internos (localhost, rede privada, link-local, metadados de nuvem)."""
    if not host:
        raise UnsafeURL("URL sem host")
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise ConnectionError(f"DNS não resolveu {host}: {e}") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise UnsafeURL(f"{host} aponta para endereço não público ({ip})")


@dataclass
class FetchResult:
    url: str
    status: int
    text: str
    elapsed_ms: int


class Fetcher(Protocol):
    def __call__(self, url: str) -> FetchResult: ...


def make_requests_fetcher(user_agent: str, timeout: int = 10, host_check: Callable[[str], None] = assert_public_host) -> Fetcher:
    import requests

    def fetch(url: str) -> FetchResult:
        start = time.monotonic()
        current = url
        with requests.Session() as s:
            s.headers["User-Agent"] = user_agent
            s.headers["Accept-Language"] = "pt-BR,pt;q=0.9,en;q=0.8"
            for _ in range(6):
                parsed = urlparse(current)
                if parsed.scheme not in ("http", "https"):
                    raise UnsafeURL(f"Esquema não permitido: {parsed.scheme}")
                host_check(parsed.hostname or "")
                r = s.get(current, timeout=timeout, allow_redirects=False, stream=True)
                if r.is_redirect and r.headers.get("location"):
                    current = urljoin(current, r.headers["location"])
                    r.close()
                    continue
                content = b""
                for chunk in r.iter_content(65536):
                    content += chunk
                    if len(content) > MAX_BYTES:
                        break
                r.close()
                encoding = r.encoding if r.encoding and r.encoding.lower() != "iso-8859-1" else None
                text = content.decode(encoding or "utf-8", errors="replace")
                return FetchResult(current, r.status_code, text, int((time.monotonic() - start) * 1000))
        raise ConnectionError("Redirecionamentos demais")

    return fetch


# ---------------------------------------------------------------------------------------
# Leitura do HTML
# ---------------------------------------------------------------------------------------
class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self._in_title = False
        self._skip = 0
        self.text_len = 0
        self.metas: dict[str, str] = {}
        self.links: list[str] = []
        self.forms = 0
        self.obsolete: set[str] = set()

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "title":
            self._in_title = True
        elif tag in ("script", "style", "noscript"):
            self._skip += 1
        elif tag == "meta":
            key = (a.get("name") or a.get("property") or "").lower()
            if key:
                self.metas[key] = a.get("content", "")
        elif tag == "a" and a.get("href"):
            self.links.append(a["href"].strip())
        elif tag == "form":
            self.forms += 1
        elif tag in ("frameset", "frame"):
            self.obsolete.add("frames (frameset)")
        elif tag in ("object", "embed"):
            src = (a.get("data") or a.get("src") or "").lower()
            if ".swf" in src or "flash" in a.get("type", "").lower():
                self.obsolete.add("Flash")
        elif tag in ("marquee", "blink"):
            self.obsolete.add(f"<{tag}>")

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag in ("script", "style", "noscript") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip:
            self.text_len += len(data.strip())


def _issue(code: str, label: str, evidence: str, basis: str = "verificado") -> dict:
    return {"code": code, "label": label, "evidence": evidence, "basis": basis}


def _social_from_links(links: list[str]) -> dict[str, str]:
    found: dict[str, str] = {}
    for href in links:
        if not href.lower().startswith("http"):
            continue
        host = (urlparse(href).hostname or "").lower()
        label = _host_matches(host, SOCIAL_DOMAINS)
        if label and label not in found:
            path = urlparse(href).path.strip("/")
            if path and not path.startswith(("sharer", "share", "intent", "dialog", "plugins", "tr")):
                found[label] = href.split("?")[0]
    return found


# ---------------------------------------------------------------------------------------
# Contatos publicados pela própria empresa (WhatsApp, e-mail, Instagram)
# ---------------------------------------------------------------------------------------
WA_PATTERNS = (
    re.compile(r"wa\.me/\+?(\d{8,15})", re.I),
    re.compile(r"whatsapp\.com/send/?\?(?:[^\"'#<>\s]*?&(?:amp;)?)?phone=\+?(\d{8,15})", re.I),
)
EMAIL_TEXT_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
JUNK_EMAIL = ("example.", "exemplo", "sentry", "wixpress", "domain.com", "seuemail", "seu@", "email@email", "nome@",
              "user@", "usuario@", "@2x", "yourdomain", "godaddy", "@sentry", "noreply", "no-reply")
IMG_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".css", ".js")
CONTACT_PAGE_RE = re.compile(r"contato|contact|fale-conosco|faleconosco|atendimento|about|sobre", re.I)


def _wa_numbers(text: str, country: str) -> list[str]:
    from .phones import normalize_phone

    found: list[str] = []
    for pat in WA_PATTERNS:
        for m in pat.finditer(text):
            digits = m.group(1)
            if country == "BR" and len(digits) in (10, 11):
                phone = normalize_phone(digits, "BR")
            elif country in ("US", "CA") and len(digits) == 10:
                phone = normalize_phone(digits, country)
            else:
                phone = normalize_phone("+" + digits, country)
            if phone and phone.e164 and phone.e164 not in found:
                found.append(phone.e164)
    return found[:3]


def _emails(links: list[str], text: str) -> list[str]:
    from urllib.parse import unquote

    candidates: list[str] = []
    for href in links:
        if href.lower().startswith("mailto:"):
            candidates += re.split(r"[,;]", unquote(href[7:].split("?")[0]))
    candidates += [m.group(0) for m in EMAIL_TEXT_RE.finditer(text[:300_000])]
    out: list[str] = []
    for e in candidates:
        e = e.strip().strip(".").lower()
        if not EMAIL_TEXT_RE.fullmatch(e) or e.endswith(IMG_EXT) or any(j in e for j in JUNK_EMAIL):
            continue
        if e not in out:
            out.append(e)
    return out[:3]


# Aviso publicado pela empresa de que não quer receber ofertas. Quando aparece, os e-mails da página
# NÃO são guardados (respeita a vontade de quem publicou; na lei canadense e na americana esse aviso
# muda o que é permitido).
NO_SOLICIT_RE = re.compile(
    r"\b(no|not accept(ing)?|do not send( us)?|don'?t send( us)?)\s+(unsolicited|solicitations?|sales (calls|emails|pitches)|marketing (emails|offers))"
    r"|\bno solicit(ing|ation|ors)\b|\bnot for (solicitation|marketing)\b"
    r"|n[ãa]o\s+(envie|enviem|aceitamos|recebemos|desejamos receber|queremos receber)\s+(propagandas?|publicidade|ofertas|spam|mensagens comerciais|e-?mails? comerciais)"
    r"|proibido o envio de (propagandas?|publicidade|e-?mails? comerciais|ofertas)",
    re.I)


# Países onde o sistema lê e-mails publicados no site da empresa. Fora do Brasil, não lê:
# nos EUA (CAN-SPAM), no Canadá (PIPEDA/CASL) e na Austrália (Spam Act) a coleta automática de
# endereços de e-mail ("harvesting") é proibida ou agravante; no Reino Unido, autônomos contam como
# pessoa física (PECR). Lá, um e-mail só entra se você mesmo cadastrar (ex.: a empresa passou na ligação).
EMAIL_EXTRACTION_COUNTRIES = {"BR"}


def extract_contacts(html: str, links: list[str], country: str = "BR") -> dict:
    socials = _social_from_links(links)
    no_offers = bool(NO_SOLICIT_RE.search(re.sub(r"<[^>]+>", " ", html[:300_000])))
    read_emails = (country or "BR").upper() in EMAIL_EXTRACTION_COUNTRIES and not no_offers
    return {
        "whatsapp": _wa_numbers(" ".join(links) + " " + html[:300_000], country),
        "emails": _emails(links, html) if read_emails else [],
        "instagram": socials.get("Instagram"),
        "facebook": socials.get("Facebook"),
        "sem_ofertas": no_offers,
    }


def _merge_contacts(base: dict, extra: dict) -> dict:
    out = dict(base)
    for key in ("whatsapp", "emails"):
        out[key] = list(dict.fromkeys((base.get(key) or []) + (extra.get(key) or [])))[:3]
    for key in ("instagram", "facebook"):
        out[key] = base.get(key) or extra.get(key)
    out["sem_ofertas"] = bool(base.get("sem_ofertas") or extra.get("sem_ofertas"))
    if out["sem_ofertas"]:
        out["emails"] = []
    return out


def _fetch_contacts(fetcher: Fetcher, url: str, user_agent: str, country: str) -> tuple[dict, list[str]]:
    """Visita uma página pública da empresa (ex.: Linktree ou página de contato) e extrai contatos."""
    if not robots_allows(fetcher, url, user_agent):
        return {}, []
    res = fetcher(url)
    if res.status >= 400:
        return {}, []
    parser = _PageParser()
    try:
        parser.feed(res.text)
    except Exception:
        pass
    return extract_contacts(res.text, parser.links, country), parser.links


def robots_allows(fetcher: Fetcher, url: str, user_agent: str) -> bool:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        res = fetcher(robots_url)
    except Exception:
        return True  # sem robots.txt acessível: comportamento padrão da web é permitir
    if res.status >= 400:
        return True
    rp = RobotFileParser()
    rp.parse(res.text.splitlines())
    return rp.can_fetch(user_agent, url)


def analyze_website(url: str | None, fetcher: Fetcher | None, user_agent: str = "ProspectaBot", now: datetime | None = None,
                    country: str = "BR") -> dict:
    """Analisa a presença digital a partir do campo "site" do perfil. Sempre retorna um dicionário."""
    now = now or datetime.now(timezone.utc)
    norm = normalize_url(url)
    kind, platform = classify_url(norm)
    result: dict = {
        "checked_at": now.replace(microsecond=0).isoformat(),
        "input_url": url,
        "kind": kind,
        "kind_label": KIND_LABELS[kind],
        "platform": platform,
        "fetched": False,
        "issues": [],
        "signals": {},
        "social_links": {},
        "contacts": {"whatsapp": [], "emails": [], "instagram": None, "facebook": None},
    }
    if kind == "rede_social":
        result["social_links"] = {platform: norm}
        result["contacts"].update({"instagram": norm if platform == "Instagram" else None,
                                   "facebook": norm if platform == "Facebook" else None})
        return result
    if kind == "whatsapp":
        result["contacts"]["whatsapp"] = _wa_numbers(norm, country)
        return result
    if kind == "agregador_links":
        # Página de links da própria empresa (Linktree etc.): costuma ter WhatsApp, Instagram e e-mail.
        if fetcher is not None:
            try:
                contacts, links = _fetch_contacts(fetcher, norm, user_agent, country)
                result["contacts"] = _merge_contacts(result["contacts"], contacts)
                result["social_links"] = _social_from_links(links)
            except Exception:
                pass
        return result
    if kind in ("sem_site", "plataforma_terceiros", "google_descontinuado"):
        return result

    # Site próprio: visita a página inicial
    if platform:
        result["issues"].append(_issue(
            "dominio_gratuito", f"Site em subdomínio gratuito ({platform})",
            f"Endereço: {urlparse(norm).hostname}",
        ))
    if fetcher is None:
        result["skipped_reason"] = "Análise do site desativada"
        return result
    try:
        if not robots_allows(fetcher, norm, user_agent):
            result["skipped_reason"] = "O robots.txt do site não permite a visita automatizada; nada foi acessado."
            return result
        res = fetcher(norm)
    except UnsafeURL as e:
        result["skipped_reason"] = f"Endereço bloqueado por segurança: {e}"
        return result
    except Exception as e:  # timeout, DNS, conexão recusada, SSL
        msg = str(e).split("(Caused by")[0][:180]
        result["issues"].append(_issue(
            "site_fora_do_ar", "Site não respondeu na checagem",
            f"Erro ao acessar {norm}: {type(e).__name__}: {msg}. Pode ser instabilidade momentânea.",
        ))
        result["reachable"] = False
        return result

    result.update({"fetched": True, "reachable": True, "final_url": res.url, "status_code": res.status, "response_ms": res.elapsed_ms})
    if res.status >= 400:
        result["issues"].append(_issue("erro_http", f"Site respondeu com erro HTTP {res.status}", f"GET {res.url} → {res.status}"))
        return result

    parser = _PageParser()
    try:
        parser.feed(res.text)
    except Exception:  # HTML muito quebrado
        pass
    title = re.sub(r"\s+", " ", parser.title).strip()
    desc = parser.metas.get("description", "").strip()
    viewport = parser.metas.get("viewport", "")
    generator = parser.metas.get("generator", "")
    links_lower = [h.lower() for h in parser.links]
    has_wa = any(("wa.me/" in h or "whatsapp.com/send" in h or "api.whatsapp.com" in h or "wa.link/" in h) for h in links_lower)
    has_tel = any(h.startswith("tel:") for h in links_lower)
    https = res.url.lower().startswith("https://")
    result["title"] = title[:200]
    result["meta_description"] = desc[:300]
    result["signals"] = {
        "https": https,
        "meta_viewport": bool(viewport),
        "link_whatsapp": has_wa,
        "link_telefone": has_tel,
        "formulario": parser.forms > 0,
        "gerador": generator[:80] or None,
        "texto_visivel_caracteres": parser.text_len,
    }
    result["social_links"] = _social_from_links(parser.links)
    contacts = extract_contacts(res.text, parser.links, country)
    if not contacts["emails"] and not contacts["sem_ofertas"] and (country or "BR").upper() in EMAIL_EXTRACTION_COUNTRIES:
        base_host = (urlparse(res.url).hostname or "").lower()
        for href in parser.links:
            target = urljoin(res.url, href)
            if (urlparse(target).hostname or "").lower() == base_host and CONTACT_PAGE_RE.search(urlparse(target).path or ""):
                try:
                    extra, _ = _fetch_contacts(fetcher, target, user_agent, country)
                    contacts = _merge_contacts(contacts, extra)
                except Exception:
                    pass
                break
    result["contacts"] = contacts

    issues = result["issues"]
    text_sample = res.text[:200_000]
    if CONSTRUCTION_PATTERNS.search(text_sample) and parser.text_len < 1500:
        m = CONSTRUCTION_PATTERNS.search(text_sample)
        issues.append(_issue("pagina_em_construcao", "Página parece em construção ou domínio estacionado", f"Trecho encontrado: \"{m.group(0)}\""))
    if not https:
        issues.append(_issue("sem_https", "Site sem HTTPS (navegadores mostram \"Não seguro\")", f"Endereço final: {res.url}"))
    if not viewport:
        issues.append(_issue("sem_meta_viewport", "Página sem a tag de adaptação para celular (meta viewport)",
                             "Sem essa tag, a página costuma aparecer reduzida no celular (interpretação).", "verificado"))
    if parser.obsolete:
        issues.append(_issue("tecnologia_obsoleta", "Usa tecnologia obsoleta", ", ".join(sorted(parser.obsolete))))
    years = []
    for m in COPYRIGHT_RE.finditer(text_sample):
        years += [int(y) for y in m.groups() if y]
    if years:
        last_year = max(years)
        result["signals"]["ano_rodape"] = last_year
        if last_year <= now.year - 2:
            issues.append(_issue("rodape_desatualizado", f"Ano no rodapé: {last_year}",
                                 f"O aviso de copyright mostra {last_year}. Pode indicar que o site não é atualizado há algum tempo.", "hipotese"))
    if res.elapsed_ms > 4000:
        issues.append(_issue("lento", "Resposta lenta na checagem", f"{res.elapsed_ms / 1000:.1f}s para carregar o HTML (medição única).", "hipotese"))
    if not title:
        issues.append(_issue("sem_titulo", "Página sem título (tag <title>)", "Afeta como o site aparece no Google."))
    if not desc:
        issues.append(_issue("sem_meta_descricao", "Sem meta descrição", "O Google escolhe um trecho aleatório para mostrar nos resultados."))
    if parser.text_len < 200:
        issues.append(_issue("conteudo_minimo", "Pouco texto na página inicial",
                             f"{parser.text_len} caracteres de texto visível no HTML. Pode ser site montado por JavaScript.", "hipotese"))
    if not has_wa and not has_tel and parser.forms == 0:
        issues.append(_issue("sem_contato_direto", "Sem botão de WhatsApp, link de telefone ou formulário na página inicial",
                             "Nenhum link wa.me, tel: ou <form> encontrado na página inicial."))
    return result
