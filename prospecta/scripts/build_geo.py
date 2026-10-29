"""Gera as listas de estados e cidades usadas nos seletores da pesquisa (static/geo/*.json).

Fontes (baixe e informe os caminhos):
- Brasil: municípios do IBGE, via https://github.com/kelvins/municipios-brasileiros (MIT)
    csv/estados.csv e csv/municipios.csv
- EUA, Canadá, Reino Unido e Austrália: cidades com mais de 15 mil habitantes do GeoNames, via
    https://github.com/datasets/world-cities (dados GeoNames, licença CC BY 4.0)
    data/world-cities.csv

Uso:
    python scripts/build_geo.py --br-estados estados.csv --br-municipios municipios.csv --world world-cities.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import unicodedata
from collections import defaultdict
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "static" / "geo"

US_STATES = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR", "California": "CA", "Colorado": "CO",
    "Connecticut": "CT", "Delaware": "DE", "District of Columbia": "DC", "Florida": "FL", "Georgia": "GA",
    "Hawaii": "HI", "Idaho": "ID", "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
    "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD", "Massachusetts": "MA", "Michigan": "MI",
    "Minnesota": "MN", "Mississippi": "MS", "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
    "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY", "North Carolina": "NC",
    "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK", "Oregon": "OR", "Pennsylvania": "PA",
    "Rhode Island": "RI", "South Carolina": "SC", "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX",
    "Utah": "UT", "Vermont": "VT", "Virginia": "VA", "Washington": "WA", "West Virginia": "WV",
    "Wisconsin": "WI", "Wyoming": "WY",
}
CA_PROVINCES = {
    "Alberta": "AB", "British Columbia": "BC", "Manitoba": "MB", "New Brunswick": "NB",
    "Newfoundland and Labrador": "NL", "Northwest Territories": "NT", "Nova Scotia": "NS", "Nunavut": "NU",
    "Ontario": "ON", "Prince Edward Island": "PE", "Quebec": "QC", "Saskatchewan": "SK", "Yukon": "YT",
}
AU_STATES = {
    "Australian Capital Territory": "ACT", "New South Wales": "NSW", "Northern Territory": "NT",
    "Queensland": "QLD", "South Australia": "SA", "Tasmania": "TAS", "Victoria": "VIC", "Western Australia": "WA",
}
GB_NATIONS = {"England": "England", "Northern Ireland": "Northern Ireland", "Scotland": "Scotland", "Wales": "Wales"}

WORLD = {
    "US": ("United States", US_STATES),
    "CA": ("Canada", CA_PROVINCES),
    "GB": ("United Kingdom", GB_NATIONS),
    "AU": ("Australia", AU_STATES),
}


def sort_key(name: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", name.casefold()) if not unicodedata.combining(c))


def write(code: str, source: str, license_: str, states: list[dict]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    data = {"country": code, "source": source, "license": license_, "states": states}
    path = OUT / f"{code}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    total = sum(len(s["cities"]) for s in states)
    print(f"{path.name}: {len(states)} estados/regiões, {total} cidades")


def build_br(estados_csv: str, municipios_csv: str) -> None:
    ufs = {}
    with open(estados_csv, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            ufs[r["codigo_uf"]] = {"code": r["uf"], "name": r["nome"], "capital": None, "cities": []}
    with open(municipios_csv, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            uf = ufs[r["codigo_uf"]]
            uf["cities"].append(r["nome"])
            if r["capital"] == "1":
                uf["capital"] = r["nome"]
    states = sorted(ufs.values(), key=lambda s: sort_key(s["name"]))
    for s in states:
        s["cities"] = sorted(set(s["cities"]), key=sort_key)
    write("BR", "IBGE, via github.com/kelvins/municipios-brasileiros", "MIT", states)


def build_world(world_csv: str) -> None:
    by_country: dict[str, dict[str, set]] = {code: defaultdict(set) for code in WORLD}
    names = {v[0]: k for k, v in WORLD.items()}
    with open(world_csv, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            code = names.get(r["country"])
            if code and r["subcountry"] in WORLD[code][1]:
                by_country[code][r["subcountry"]].add(r["name"].strip())
    for code, (_, regions) in WORLD.items():
        states = []
        for region_name, region_code in sorted(regions.items(), key=lambda kv: sort_key(kv[0])):
            cities = sorted(by_country[code].get(region_name, set()), key=sort_key)
            if cities:
                states.append({"code": region_code, "name": region_name, "capital": None, "cities": cities})
        write(code, "GeoNames (cidades com mais de 15 mil habitantes), via github.com/datasets/world-cities",
              "CC BY 4.0 (GeoNames)", states)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--br-estados", required=True)
    ap.add_argument("--br-municipios", required=True)
    ap.add_argument("--world", required=True)
    a = ap.parse_args()
    build_br(a.br_estados, a.br_municipios)
    build_world(a.world)


if __name__ == "__main__":
    main()
