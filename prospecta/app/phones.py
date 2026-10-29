"""Normalização de telefones (Brasil e internacionais) e links de clique para conversar (wa.me).

O tipo de número é uma HIPÓTESE. No Brasil, celulares (11 dígitos com 9 após o DDD) costumam ter
WhatsApp. Nos EUA e no Canadá não dá para saber pelo número se é celular. Ter um telefone público
NÃO equivale a autorização para mensagens promocionais.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import quote

BR_SPECIAL_PREFIXES = ("0800", "0300", "0500", "0900", "3003", "4003", "4004", "4020", "4062")
NANP_TOLL_FREE = ("800", "833", "844", "855", "866", "877", "888")

HYPOTHESES = {
    "celular": "Celular: provavelmente tem WhatsApp (não verificado)",
    "fixo": "Fixo: pode ter WhatsApp Business (não verificado)",
    "especial": "Número especial (0800/toll-free): não usa WhatsApp",
    "invalido": "Número não reconhecido",
    "indefinido": "Não dá para saber pelo número se é celular. Nos EUA, WhatsApp é pouco usado: prefira ligar",
}


@dataclass(frozen=True)
class Phone:
    raw: str
    national: str | None  # só dígitos, sem código do país
    e164: str | None
    kind: str  # celular | fixo | especial | invalido | indefinido
    country_code: str = "55"

    @property
    def whatsapp_hypothesis(self) -> str:
        return HYPOTHESES[self.kind]

    def display(self) -> str:
        n = self.national
        if not n:
            return self.raw
        if self.country_code == "55":
            if self.kind == "celular":
                return f"({n[:2]}) {n[2:7]}-{n[7:]}"
            if self.kind == "fixo":
                return f"({n[:2]}) {n[2:6]}-{n[6:]}"
            return n
        if self.country_code == "1" and len(n) == 10:
            return f"({n[:3]}) {n[3:6]}-{n[6:]}"
        return f"+{self.country_code} {n}"


def normalize_br_phone(raw: str | None) -> Phone | None:
    if not raw or not str(raw).strip():
        return None
    raw = str(raw).strip()
    digits = re.sub(r"\D", "", raw)
    if digits.startswith(BR_SPECIAL_PREFIXES) or (len(digits) in (8, 11) and digits[:4] in BR_SPECIAL_PREFIXES):
        return Phone(raw, digits, None, "especial")
    if digits.startswith("55") and len(digits) in (12, 13):
        digits = digits[2:]
    if digits.startswith("0") and len(digits) in (11, 12):  # 0 + DDD + número (formato de discagem antiga)
        digits = digits[1:]
    if len(digits) == 11 and digits[2] == "9":
        return Phone(raw, digits, "+55" + digits, "celular")
    if len(digits) == 10 and digits[2] in "2345":
        return Phone(raw, digits, "+55" + digits, "fixo")
    if len(digits) == 10 and digits[2] in "6789":
        # Celular antigo sem o nono dígito: não dá para garantir; tratamos como inválido.
        return Phone(raw, digits, None, "invalido")
    return Phone(raw, digits or None, None, "invalido")


def _from_e164_digits(raw: str, digits: str) -> Phone:
    """digits = código do país + número nacional."""
    if digits.startswith("55"):
        return normalize_br_phone("+" + digits) or Phone(raw, None, None, "invalido")
    if digits.startswith("1") and len(digits) == 11:
        national = digits[1:]
        kind = "especial" if national[:3] in NANP_TOLL_FREE else "indefinido"
        return Phone(raw, national, None if kind == "especial" else "+" + digits, kind, "1")
    for cc, mobile_prefix, toll_free in (("44", "7", ("800", "808")), ("61", "4", ("1800", "1300")), ("351", "9", ("800",))):
        if digits.startswith(cc):
            national = digits[len(cc):]
            if national.startswith(toll_free):
                return Phone(raw, national, None, "especial", cc)
            kind = "celular" if national.startswith(mobile_prefix) else "fixo"
            return Phone(raw, national, "+" + digits, kind, cc)
    if 8 <= len(digits) <= 15:
        return Phone(raw, digits, "+" + digits, "indefinido", "")
    return Phone(raw, None, None, "invalido", "")


def normalize_phone(raw: str | None, country: str | None = "BR", international: str | None = None) -> Phone | None:
    """Normaliza um telefone considerando o país da empresa.

    `international` (ex.: "+1 512-555-0101", vindo do Google) tem prioridade porque já traz o
    código do país."""
    country = (country or "BR").upper()
    for candidate in (international, raw):
        if candidate and str(candidate).strip().startswith(("+", "00")):
            digits = re.sub(r"\D", "", str(candidate))
            if str(candidate).strip().startswith("00"):
                digits = digits[2:]
            phone = _from_e164_digits(str(raw or candidate).strip(), digits)
            return phone
    if not raw or not str(raw).strip():
        return None
    if country == "BR":
        return normalize_br_phone(raw)
    digits = re.sub(r"\D", "", str(raw))
    if country in ("US", "CA"):
        if len(digits) == 10:
            digits = "1" + digits
        if len(digits) == 11 and digits.startswith("1"):
            return _from_e164_digits(str(raw).strip(), digits)
        return Phone(str(raw).strip(), None, None, "invalido", "1")
    codes = {"GB": "44", "AU": "61", "PT": "351"}
    cc = codes.get(country)
    if cc:
        national = digits[1:] if digits.startswith("0") else digits
        return _from_e164_digits(str(raw).strip(), cc + national)
    return Phone(str(raw).strip(), None, None, "invalido", "")


def whatsapp_link(e164: str | None, text: str | None = None) -> str | None:
    """Link oficial de clique para conversar. Abre o WhatsApp com o texto preenchido;
    o envio continua sendo feito manualmente pelo usuário."""
    if not e164:
        return None
    number = e164.lstrip("+")
    url = f"https://wa.me/{number}"
    if text:
        url += "?text=" + quote(text, safe="")
    return url
