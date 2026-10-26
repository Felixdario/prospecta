"""Utilitários de teste: respostas simuladas da Places API, sites falsos e serviços isolados."""
from __future__ import annotations

import tempfile
from pathlib import Path

from app.config import Config
from app.db import Database
from app.repository import Repo
from app.services import Services
from app.site_analysis import FetchResult
from app.sources.places import HttpResponse, PlacesClient

ADMIN = "test-admin-token"


def make_place(i: int, **over) -> dict:
    place = {
        "id": f"ChIJ_place_{i}",
        "displayName": {"text": f"Academia Teste {i}", "languageCode": "pt-BR"},
        "formattedAddress": f"Rua Teste, {i} - Batel, Curitiba - PR, 80000-000, Brasil",
        "addressComponents": [
            {"longText": "Batel", "shortText": "Batel", "types": ["sublocality_level_1", "sublocality", "political"]},
            {"longText": "Curitiba", "shortText": "Curitiba", "types": ["administrative_area_level_2", "political"]},
            {"longText": "Paraná", "shortText": "PR", "types": ["administrative_area_level_1", "political"]},
        ],
        "nationalPhoneNumber": f"(41) 99999-{i:04d}",
        "internationalPhoneNumber": f"+55 41 99999-{i:04d}",
        "googleMapsUri": f"https://maps.google.com/?cid={i}",
        "rating": 4.7,
        "userRatingCount": 150,
        "regularOpeningHours": {"weekdayDescriptions": ["segunda-feira: 06:00–22:00"]},
        "businessStatus": "OPERATIONAL",
        "primaryType": "gym",
        "primaryTypeDisplayName": {"text": "Academia", "languageCode": "pt-BR"},
        "types": ["gym", "health", "point_of_interest", "establishment"],
    }
    place.update(over)
    return {k: v for k, v in place.items() if v is not None}


class FakePlacesHttp:
    """Simula a Places API. `pages` é uma lista de listas de lugares; responde por pageToken."""

    def __init__(self, pages: list[list[dict]] | None = None, statuses: list[int] | None = None, details: dict | None = None):
        self.pages = pages or []
        self.statuses = list(statuses or [])
        self.details = details or {}
        self.requests: list[dict] = []

    def __call__(self, method, url, headers, body, timeout):
        self.requests.append({"method": method, "url": url, "headers": headers, "body": body})
        if self.statuses:
            status = self.statuses.pop(0)
            if status != 200:
                return HttpResponse(status, {"error": {"message": f"erro simulado {status}"}})
        if method == "GET":
            pid = url.split("/places/")[1].split("?")[0]
            return HttpResponse(200, self.details[pid])
        idx = int((body or {}).get("pageToken", "page-0").split("-")[1])
        data = {"places": self.pages[idx] if idx < len(self.pages) else []}
        if idx + 1 < len(self.pages):
            data["nextPageToken"] = f"page-{idx + 1}"
        return HttpResponse(200, data)


def fake_fetcher(sites: dict):
    """sites: url -> FetchResult | Exception | str(html)."""
    calls = []

    def fetch(url: str) -> FetchResult:
        calls.append(url)
        if url.endswith("/robots.txt"):
            v = sites.get(url)
            if v is None:
                return FetchResult(url, 404, "", 10)
        else:
            v = sites.get(url)
        if isinstance(v, Exception):
            raise v
        if isinstance(v, FetchResult):
            return v
        if isinstance(v, str):
            return FetchResult(url, 200, v, 120)
        raise ConnectionError(f"site não simulado: {url}")

    fetch.calls = calls
    return fetch


def make_services(places_http: FakePlacesHttp | None = None, fetcher=None, writer=None, **config_over) -> Services:
    tmp = Path(tempfile.mkdtemp(prefix="prospecta-test-"))
    cfg = Config(database_path=tmp / "test.db", admin_token=ADMIN, google_api_key="fake-key", anthropic_api_key="", **config_over)
    db = Database(cfg.database_path)
    db.init()
    repo = Repo(db)
    places_http = places_http or FakePlacesHttp()

    def factory():
        def guard(sku):
            if repo.consume_quota(sku, cfg.google_textsearch_monthly_limit) < 0:
                from app.sources.places import QuotaExceeded
                raise QuotaExceeded("limite")
        return PlacesClient(cfg.google_api_key, guard, http=places_http, sleep=lambda s: None)

    svc = Services(repo, cfg, places_factory=factory, fetcher=fetcher or fake_fetcher({}), writer=writer)
    svc.places_http = places_http
    return svc


GOOD_HTML = """<!doctype html><html><head><title>Academia Boa</title>
<meta name="viewport" content="width=device-width"><meta name="description" content="A melhor academia">
</head><body><h1>Bem-vindo</h1><p>{text}</p><a href="https://wa.me/5541999990000">WhatsApp</a>
<a href="https://instagram.com/academiaboa">Instagram</a><footer>© 2026 Academia Boa</footer></body></html>""".replace("{text}", "Texto institucional. " * 30)

OLD_HTML = """<html><head><title></title></head><body><table><tr><td>Bem vindo ao nosso site</td></tr></table>
<object data="intro.swf"></object><p>Copyright © 2016 - Oficina Antiga</p></body></html>"""
