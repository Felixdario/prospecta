"""Importação de leads por planilha CSV.

Aceita colunas em português ou o formato do google-maps-scraper-kit (title, phone, website,
category, address, review_rating, review_count, link, place_id). A origem dos dados é de
responsabilidade de quem importa: dados obtidos por raspagem podem violar termos de uso.
E-mails, se existirem na planilha, são IGNORADOS (minimização de dados pessoais).
"""
from __future__ import annotations

import csv
import io

MAX_ROWS = 5000

ALIASES = {
    "name": ("title", "name", "nome", "empresa", "nome_empresa", "razao_social", "razão social"),
    "phone": ("phone", "telefone", "fone", "celular", "whatsapp", "tel"),
    "website": ("website", "site", "url", "web_site"),
    "category": ("category", "categoria", "segmento", "ramo"),
    "address": ("address", "endereco", "endereço", "logradouro"),
    "neighborhood": ("bairro", "neighborhood", "regiao", "região"),
    "city": ("city", "cidade", "municipio", "município"),
    "state": ("state", "estado", "uf"),
    "rating": ("review_rating", "rating", "nota", "avaliacao_media"),
    "reviews_count": ("review_count", "reviews", "avaliacoes", "avaliações", "qtd_avaliacoes", "user_ratings_total"),
    "maps_url": ("link", "maps_url", "google_maps", "url_maps", "maps"),
    "place_id": ("place_id", "placeid"),
}


def _decode(raw: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _num(value: str, kind=float):
    value = (value or "").strip().replace(",", ".")
    if not value:
        return None
    try:
        return kind(float(value))
    except ValueError:
        return None


def parse_csv(raw: bytes) -> tuple[list[dict], list[str]]:
    text = _decode(raw)
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        return [], ["Arquivo sem cabeçalho"]
    header = {h.strip().lower(): h for h in reader.fieldnames if h}
    colmap = {}
    for field, names in ALIASES.items():
        for n in names:
            if n in header:
                colmap[field] = header[n]
                break
    if "name" not in colmap:
        return [], [f"Coluna de nome não encontrada. Use uma destas: {', '.join(ALIASES['name'])}"]
    rows, errors = [], []
    for i, row in enumerate(reader, start=2):
        if len(rows) >= MAX_ROWS:
            errors.append(f"Limite de {MAX_ROWS} linhas por importação atingido; o restante foi ignorado.")
            break
        get = lambda f: (row.get(colmap[f]) or "").strip() if f in colmap else ""
        name = get("name")
        if not name:
            errors.append(f"Linha {i}: sem nome, ignorada")
            continue
        rows.append({
            "name": name[:200],
            "phone": get("phone") or None,
            "website": get("website") or None,
            "category": get("category") or None,
            "address": get("address") or None,
            "neighborhood": get("neighborhood") or None,
            "city": get("city") or None,
            "state": get("state") or None,
            "rating": _num(get("rating")),
            "reviews_count": _num(get("reviews_count"), int),
            "maps_url": get("maps_url") or None,
            "place_id": get("place_id") or None,
            "has_website_column": "website" in colmap,
        })
    return rows, errors
