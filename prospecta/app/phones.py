"""Normalização de telefones brasileiros e links de clique para conversar (wa.me).

Importante: o tipo de número é uma HIPÓTESE. Celulares (11 dígitos começando com 9 após o DDD)
costumam ter WhatsApp, e fixos também podem ter WhatsApp Business. Nada disso é verificado, e
ter um telefone público NÃO equivale a autorização para mensagens promocionais.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import quote

SPECIAL_PREFIXES = ("0800", "0300", "0500", "0900", "3003", "4003", "4004", "4020", "4062")


@dataclass(frozen=True)
class Phone:
    raw: str
    national: str | None  # DDD + número, só dígitos
    e164: str | None
    kind: str  # celular | fixo | especial | invalido

    @property
    def whatsapp_hypothesis(self) -> str:
        return {
            "celular": "Celular: provavelmente tem WhatsApp (não verificado)",
            "fixo": "Fixo: pode ter WhatsApp Business (não verificado)",
            "especial": "Número especial (0800/4004): não usa WhatsApp",
            "invalido": "Número não reconhecido",
        }[self.kind]

    def display(self) -> str:
        n = self.national
        if not n:
            return self.raw
        if self.kind == "celular":
            return f"({n[:2]}) {n[2:7]}-{n[7:]}"
        if self.kind == "fixo":
            return f"({n[:2]}) {n[2:6]}-{n[6:]}"
        return n


def normalize_br_phone(raw: str | None) -> Phone | None:
    if not raw or not str(raw).strip():
        return None
    raw = str(raw).strip()
    digits = re.sub(r"\D", "", raw)
    if digits.startswith(SPECIAL_PREFIXES) or (len(digits) in (8, 11) and digits[:4] in SPECIAL_PREFIXES):
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
