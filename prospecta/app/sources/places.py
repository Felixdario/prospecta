"""Cliente da Google Places API (New): Text Search e Place Details.

Custos (tabela oficial do Google, conferida em out/2026; confirme antes de usar em volume):
- Os campos pedidos (telefone, site, nota, avaliações, horário) enquadram cada chamada no SKU
  "Text Search Enterprise": 1.000 chamadas grátis por mês e depois cerca de US$ 35 por 1.000.
- Cada chamada retorna até 20 empresas, e a busca pagina até 60 resultados (3 chamadas).
- "Place Details Enterprise" (usado para atualizar um lead): 1.000 grátis/mês, depois ~US$ 20 por 1.000.
O sistema conta as chamadas por mês e para antes do limite configurado no .env.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Iterator

BASE_URL = "https://places.googleapis.com/v1"

PLACE_FIELDS = [
    "id", "displayName", "formattedAddress", "addressComponents", "nationalPhoneNumber",
    "internationalPhoneNumber", "websiteUri", "googleMapsUri", "rating", "userRatingCount",
    "regularOpeningHours", "businessStatus", "primaryType", "primaryTypeDisplayName", "types",
]
SEARCH_FIELD_MASK = ",".join(["places." + f for f in PLACE_FIELDS] + ["nextPageToken"])
DETAILS_FIELD_MASK = ",".join(PLACE_FIELDS)

SKU_TEXT_SEARCH = "text_search_enterprise"
SKU_DETAILS = "place_details_enterprise"


class PlacesError(Exception):
    pass


class QuotaExceeded(PlacesError):
    pass


@dataclass
class HttpResponse:
    status: int
    data: dict


def _default_http(method: str, url: str, headers: dict, json_body: dict | None, timeout: int) -> HttpResponse:
    import requests

    r = requests.request(method, url, headers=headers, json=json_body, timeout=timeout)
    try:
        data = r.json()
    except ValueError:
        data = {"error": {"message": r.text[:300]}}
    return HttpResponse(r.status_code, data)


class PlacesClient:
    """`usage_guard(sku)` é chamado antes de cada requisição: deve lançar QuotaExceeded se o
    limite mensal foi atingido e registrar a chamada caso contrário."""

    def __init__(self, api_key: str, usage_guard: Callable[[str], None], http: Callable[..., HttpResponse] | None = None,
                 sleep: Callable[[float], None] = time.sleep, timeout: int = 30, max_retries: int = 3):
        if not api_key:
            raise PlacesError("GOOGLE_PLACES_API_KEY não configurada no arquivo .env")
        self.api_key = api_key
        self.usage_guard = usage_guard
        self.http = http or _default_http
        self.sleep = sleep
        self.timeout = timeout
        self.max_retries = max_retries
        self.calls = 0

    def _request(self, method: str, url: str, field_mask: str, sku: str, body: dict | None = None) -> dict:
        headers = {"Content-Type": "application/json", "X-Goog-Api-Key": self.api_key, "X-Goog-FieldMask": field_mask}
        delay = 1.0
        for attempt in range(1, self.max_retries + 1):
            self.usage_guard(sku)
            self.calls += 1
            try:
                res = self.http(method, url, headers, body, self.timeout)
            except Exception as e:  # erro de rede
                if attempt == self.max_retries:
                    raise PlacesError(f"Falha de conexão com a Places API: {e}") from e
                self.sleep(delay)
                delay *= 2
                continue
            if res.status == 200:
                return res.data
            message = (res.data.get("error") or {}).get("message", "")
            if res.status in (429, 500, 502, 503, 504) and attempt < self.max_retries:
                self.sleep(delay)
                delay *= 2
                continue
            hints = {
                400: "Requisição inválida.",
                403: "Chave sem permissão: confira se a 'Places API (New)' está ativada no projeto e se o faturamento está habilitado.",
                429: "Limite de requisições do Google atingido. Tente novamente mais tarde.",
            }
            raise PlacesError(f"Places API respondeu {res.status}. {hints.get(res.status, '')} Detalhe: {message}".strip())
        raise PlacesError("Places API: tentativas esgotadas")

    def search_text(self, text_query: str, max_results: int = 60, min_rating: float | None = None,
                    language: str = "pt-BR", region: str = "BR", page_delay: float = 1.0) -> Iterator[dict]:
        """Gera lugares (formato bruto da API) até max_results (máximo 60 por consulta)."""
        max_results = max(1, min(60, int(max_results)))
        body: dict = {"textQuery": text_query, "languageCode": language, "regionCode": region, "pageSize": min(20, max_results)}
        if min_rating:
            body["minRating"] = min(5.0, max(0.0, round(float(min_rating) * 2) / 2))
        yielded = 0
        while True:
            data = self._request("POST", f"{BASE_URL}/places:searchText", SEARCH_FIELD_MASK, SKU_TEXT_SEARCH, body)
            for place in data.get("places", []):
                yield place
                yielded += 1
                if yielded >= max_results:
                    return
            token = data.get("nextPageToken")
            if not token:
                return
            body = dict(body, pageToken=token, pageSize=min(20, max_results - yielded))
            self.sleep(page_delay)

    def get_details(self, place_id: str, language: str = "pt-BR", region: str = "BR") -> dict:
        url = f"{BASE_URL}/places/{place_id}?languageCode={language}&regionCode={region}"
        return self._request("GET", url, DETAILS_FIELD_MASK, SKU_DETAILS)


def _component(components: list[dict], *types: str, short: bool = False) -> str | None:
    for t in types:
        for c in components or []:
            if t in c.get("types", []):
                return c.get("shortText" if short else "longText") or c.get("longText")
    return None


def map_place(place: dict) -> dict:
    """Converte o formato da Places API para os campos do lead."""
    comps = place.get("addressComponents") or []
    hours = (place.get("regularOpeningHours") or {}).get("weekdayDescriptions")
    return {
        "place_id": place.get("id"),
        "name": (place.get("displayName") or {}).get("text") or "(sem nome)",
        "category": (place.get("primaryTypeDisplayName") or {}).get("text"),
        "primary_type": place.get("primaryType"),
        "types": place.get("types") or [],
        "address": place.get("formattedAddress"),
        "neighborhood": _component(comps, "sublocality_level_1", "sublocality", "neighborhood"),
        "city": _component(comps, "administrative_area_level_2", "locality"),
        "state": _component(comps, "administrative_area_level_1", short=True),
        "phone": place.get("nationalPhoneNumber") or place.get("internationalPhoneNumber"),
        "website": place.get("websiteUri"),
        "maps_url": place.get("googleMapsUri"),
        "rating": place.get("rating"),
        "reviews_count": place.get("userRatingCount"),
        "opening_hours": hours,
        "business_status": place.get("businessStatus"),
    }
