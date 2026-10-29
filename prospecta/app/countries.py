"""Países suportados na pesquisa: idioma do Google, formato da consulta e idioma das mensagens."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Country:
    code: str  # ISO 3166-1 alfa-2
    name: str  # nome em português (interface)
    places_language: str  # languageCode enviado à Places API
    message_language: str  # pt | en
    connector: str  # "em" / "in" na consulta de texto
    state_example: str
    calling_code: str


COUNTRIES: dict[str, Country] = {
    "BR": Country("BR", "Brasil", "pt-BR", "pt", "em", "PR", "55"),
    "US": Country("US", "Estados Unidos", "en", "en", "in", "TX", "1"),
    "CA": Country("CA", "Canadá", "en", "en", "in", "ON", "1"),
    "GB": Country("GB", "Reino Unido", "en", "en", "in", "", "44"),
    "AU": Country("AU", "Austrália", "en", "en", "in", "NSW", "61"),
}
DEFAULT_COUNTRY = "BR"


def get_country(code: str | None) -> Country:
    return COUNTRIES.get((code or DEFAULT_COUNTRY).upper(), COUNTRIES[DEFAULT_COUNTRY])


def build_query(segment: str, city: str, state: str | None, region: str | None, country_code: str) -> str:
    c = get_country(country_code)
    segment, city = segment.strip(), city.strip()
    state = (state or "").strip()
    if c.code == "BR":
        place = f"{city} - {state}" if state else city
        return f"{segment} {c.connector} {region + ', ' if region else ''}{place}"
    place = f"{city}, {state}" if state else city
    return f"{segment} {c.connector} {region + ', ' if region else ''}{place}"


def all_countries() -> list[dict]:
    return [{"code": c.code, "name": c.name, "language": c.message_language, "state_example": c.state_example}
            for c in COUNTRIES.values()]
