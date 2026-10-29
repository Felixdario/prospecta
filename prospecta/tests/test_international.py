"""Pesquisa e abordagem fora do Brasil (EUA, Canadá, Reino Unido, Austrália)."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from starlette.testclient import TestClient

from app.countries import build_query
from app.db import Database
from app.jobs import Worker
from app.main import create_app
from app.messages import lint_message, render_template
from app.phones import normalize_phone
from app.segments import detect_segment
from app.sources.places import map_place

from tests.helpers import ADMIN, FakePlacesHttp, fake_fetcher, make_place, make_services

H = {"Authorization": f"Bearer {ADMIN}"}
SELLER = {"nome": "Eduardo Felix", "primeiro_nome": "Eduardo", "experiencia": "há mais de 3 anos", "experiencia_en": "for over 3 years", "empresa": ""}


def us_place(i: int, **over) -> dict:
    base = make_place(
        i,
        displayName={"text": f"Austin Dental {i}", "languageCode": "en"},
        formattedAddress=f"{100 + i} Congress Ave, Austin, TX 78701, USA",
        addressComponents=[
            {"longText": "Downtown", "shortText": "Downtown", "types": ["neighborhood", "political"]},
            {"longText": "Austin", "shortText": "Austin", "types": ["locality", "political"]},
            {"longText": "Travis County", "shortText": "Travis County", "types": ["administrative_area_level_2", "political"]},
            {"longText": "Texas", "shortText": "TX", "types": ["administrative_area_level_1", "political"]},
            {"longText": "United States", "shortText": "US", "types": ["country", "political"]},
        ],
        nationalPhoneNumber=f"(512) 555-01{i:02d}",
        internationalPhoneNumber=f"+1 512-555-01{i:02d}",
        primaryType="dentist",
        primaryTypeDisplayName={"text": "Dentist", "languageCode": "en"},
        types=["dentist", "health", "point_of_interest", "establishment"],
        utcOffsetMinutes=-300,
    )
    base.update(over)
    return base


class PhoneAndQueryTests(unittest.TestCase):
    def test_us_phones(self):
        p = normalize_phone("(512) 555-0101", "US")
        self.assertEqual((p.e164, p.kind, p.display()), ("+15125550101", "indefinido", "(512) 555-0101"))
        p = normalize_phone("(512) 555-0101", "BR", "+1 512-555-0101")  # o número internacional manda
        self.assertEqual(p.e164, "+15125550101")
        toll_free = normalize_phone("(800) 555-0100", "US")
        self.assertEqual((toll_free.kind, toll_free.e164), ("especial", None))

    def test_uk_and_australia_detect_mobile(self):
        self.assertEqual(normalize_phone("+44 7700 900123", "GB").kind, "celular")
        p = normalize_phone("020 7946 0018", "GB")
        self.assertEqual((p.kind, p.e164), ("fixo", "+442079460018"))
        p = normalize_phone("0412 345 678", "AU")
        self.assertEqual((p.kind, p.e164), ("celular", "+61412345678"))

    def test_brazil_unchanged(self):
        p = normalize_phone("(41) 99876-5432", "BR")
        self.assertEqual((p.e164, p.kind), ("+5541998765432", "celular"))

    def test_queries(self):
        self.assertEqual(build_query("dentists", "Austin", "TX", None, "US"), "dentists in Austin, TX")
        self.assertEqual(build_query("dentists", "Austin", "TX", "Downtown", "US"), "dentists in Downtown, Austin, TX")
        self.assertEqual(build_query("plumbers", "Manchester", "", None, "GB"), "plumbers in Manchester")
        self.assertEqual(build_query("academias", "Curitiba", "PR", "Batel", "BR"), "academias em Batel, Curitiba - PR")

    def test_us_address_uses_city_not_county(self):
        d = map_place(us_place(1))
        self.assertEqual((d["city"], d["state"], d["country"], d["neighborhood"]), ("Austin", "TX", "US", "Downtown"))
        self.assertEqual(d["utc_offset_minutes"], -300)
        self.assertEqual(d["phone_international"], "+1 512-555-0101")

    def test_english_segments(self):
        for text, key in (("gyms", "academia"), ("dentists", "saude"), ("hair salons", "beleza"), ("roofers", "servicos"),
                          ("auto repair shops", "automotivo"), ("law firms", "profissionais")):
            self.assertEqual(detect_segment(text).key, key, text)


class EnglishMessageTests(unittest.TestCase):
    def lead(self, **over):
        base = {"name": "Austin Dental 1", "source": "google_places", "segment": "saude", "city": "Austin", "state": "TX",
                "country": "US", "language": "en", "rating": 4.8, "reviews_count": 212, "phone_e164": "+15125550101",
                "phone_kind": "indefinido", "status": "qualificado", "site_analysis": {"kind": "sem_site", "issues": []}}
        base.update(over)
        return base

    def test_cold_message_is_english_honest_and_has_opt_out(self):
        msg = render_template(self.lead(), "sem_site", SELLER)
        self.assertTrue(msg.startswith("Hi there! I came across Austin Dental 1 on Google: 4.8 stars from 212 reviews"), msg)
        self.assertIn("I'm Eduardo", msg)
        self.assertIn("couldn't find a website", msg)
        self.assertIn("won't reach out again", msg)
        self.assertNotIn("tudo bem", msg)
        self.assertEqual(lint_message(msg, self.lead(), "whatsapp", "sem_site"), [])
        email = render_template(self.lead(), "sem_site", dict(SELLER, endereco="Rua Exemplo, 100 - Curitiba, Brasil"), channel="email")
        self.assertIn("This email is a business proposal for website services.", email)
        self.assertIn("Rua Exemplo, 100", email)
        self.assertEqual(lint_message(email, self.lead(), "email", "sem_site"), [])

    def test_english_lint(self):
        site_lead = self.lead(website="https://a.com", site_analysis={"kind": "proprio", "issues": []})
        text = "You are losing customers without a site. I guarantee we can double your sales. Act now! I couldn't find a website. Your 4.1-star rating..."
        reasons = " ".join(w["motivo"] for w in lint_message(text, site_lead))
        for expected in ("perde clientes", "garantia", "exagerada", "urgência", "não há site", "Nota citada"):
            self.assertIn(expected, reasons)

    def test_language_override(self):
        msg = render_template(self.lead(language="pt"), "sem_site", SELLER)
        self.assertIn("tudo bem?", msg)


class UsSearchFlowTests(unittest.TestCase):
    def setUp(self):
        pages = [[us_place(1), us_place(2, websiteUri="https://www.yelp.com/biz/austin-dental-2"),
                  us_place(3, addressComponents=[{"longText": "Mexico", "shortText": "MX", "types": ["country"]}])]]
        self.svc = make_services(FakePlacesHttp(pages), fetcher=fake_fetcher({}))
        self.client = TestClient(create_app(self.svc.config, self.svc, start_worker=False))
        self.worker = Worker(self.svc)

    def test_us_search_end_to_end(self):
        body = {"country": "US", "segment": "dentists", "city": "Austin", "state": "TX", "max_results": 20,
                "filters": {"website": "sem_site_proprio", "only_mobile": True}}
        r = self.client.post("/api/searches", json=body, headers=H)
        self.assertEqual(r.status_code, 202, r.text)
        self.worker.process_next()
        job = self.client.get(f"/api/searches/{r.json()['id']}", headers=H).json()
        self.assertEqual(job["status"], "concluida", job)
        req = self.svc.places_http.requests[0]["body"]
        self.assertEqual((req["textQuery"], req["languageCode"], req["regionCode"]), ("dentists in Austin, TX", "en", "US"))
        # "Só celulares" não descarta números dos EUA (não dá para saber); empresa de outro país é descartada
        self.assertEqual(job["saved_new"], 2)
        self.assertEqual(job["discard_reasons"], {"fora_do_pais": 1})
        leads = self.client.get("/api/leads?country=US&sort=name", headers=H).json()["items"]
        self.assertEqual([(l["city"], l["country"], l["language"]) for l in leads], [("Austin", "US", "en")] * 2)
        self.assertEqual(leads[1]["presence_kind"], "plataforma_terceiros")  # Yelp no lugar do site
        d = self.client.get(f"/api/leads/{leads[0]['id']}", headers=H).json()
        lead = d["lead"]
        self.assertEqual((lead["phone_e164"], lead["phone_kind"], lead["utc_offset_minutes"]), ("+15125550101", "indefinido", -300))
        # Primeiro contato sugerido nos EUA: roteiro de ligação, em inglês
        self.assertEqual(d["suggested_variant"], "roteiro_ligacao")
        self.assertIn("Hi, this is Eduardo", lead["suggested_message"])
        self.assertEqual(d["next_action"], "Revisar o roteiro e ligar")
        warnings = " ".join(d["contact"]["warnings"])
        self.assertIn("TCPA", warnings)
        self.assertTrue("Horário local da empresa" in warnings or "horário comercial da empresa" in warnings, warnings)
        self.assertIn("pouco usado", d["whatsapp_hypothesis"])
        # Mensagem escrita (formulário do site) em inglês, sem bloqueios
        r = self.client.post(f"/api/leads/{lead['id']}/message", json={"variant": "sem_site"}, headers=H)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("couldn't find a website", r.json()["message"])
        self.assertFalse([w for w in r.json()["warnings"] if w["nivel"] == "bloqueante"])
        # Registro de ligação conta como contato ativo
        r = self.client.post(f"/api/leads/{lead['id']}/interactions", json={"type": "mensagem_enviada", "channel": "telefone"}, headers=H)
        self.assertEqual(r.json()["lead"]["status"], "contato_realizado")
        self.assertEqual(r.json()["events"][0]["summary"], "Ligação feita (contato ativo)")
        # Exportação traz país e telefone internacional
        csv_text = self.client.get("/api/export.csv?country=US", headers=H).content.decode("utf-8-sig")
        self.assertIn("pais", csv_text.splitlines()[0])
        self.assertIn("+15125550101", csv_text)

    def test_suppression_with_us_phone(self):
        r = self.client.post("/api/suppression", json={"kind": "phone", "value": "(512) 555-0101", "country": "US", "reason": "pediu"}, headers=H)
        self.assertEqual(r.status_code, 201)
        values = [s["value"] for s in self.client.get("/api/suppression", headers=H).json()["items"]]
        self.assertIn("+15125550101", values)
        self.client.post("/api/searches", json={"country": "US", "segment": "dentists", "city": "Austin", "state": "TX"}, headers=H)
        self.worker.process_next()
        job = self.client.get("/api/searches", headers=H).json()["items"][0]
        self.assertEqual(job["discard_reasons"].get("lista_de_supressao"), 1)

    def test_csv_import_detects_country(self):
        csv_data = ("name,phone,website,category,city,state\n"
                    "Lone Star Plumbing,+1 512 555 0142,,Plumber,Austin,TX\n"
                    "Maple Dental,(416) 555-0123,,Dentist,Toronto,ON\n").encode()
        csv_with_country = "nome;telefone;cidade;pais\nMaple Dental;(416) 555-0123;Toronto;Canada\n".encode()
        r = self.client.post("/api/import", files={"file": ("a.csv", csv_data, "text/csv")}, headers=H)
        self.assertEqual(r.json()["novos"], 2)
        self.client.post("/api/import", files={"file": ("b.csv", csv_with_country, "text/csv")}, headers=H)
        items = {l["name"]: l for l in self.client.get("/api/leads", headers=H).json()["items"]}
        self.assertEqual((items["Lone Star Plumbing"]["country"], items["Lone Star Plumbing"]["phone_e164"]), ("US", "+15125550142"))
        self.assertEqual((items["Maple Dental"]["country"], items["Maple Dental"]["phone_e164"]), ("CA", "+14165550123"))


class SegmentSelectTests(unittest.TestCase):
    def test_chosen_segment_group_is_used_when_google_types_are_generic(self):
        place = make_place(1, primaryType=None, primaryTypeDisplayName={"text": "Business"}, types=["point_of_interest", "establishment"])
        svc = make_services(FakePlacesHttp([[place]]), fetcher=fake_fetcher({}))
        client = TestClient(create_app(svc.config, svc, start_worker=False))
        r = client.post("/api/searches", json={"country": "BR", "segment": "Mudanças e fretes", "segment_group": "servicos",
                                               "city": "Curitiba", "state": "PR"}, headers=H)
        self.assertEqual(r.status_code, 202, r.text)
        Worker(svc).process_next()
        lead = client.get("/api/leads", headers=H).json()["items"][0]
        self.assertEqual(lead["segment"], "servicos")
        bad = client.post("/api/searches", json={"country": "BR", "segment": "x" * 3, "segment_group": "inexistente",
                                                 "city": "Curitiba", "state": "PR"}, headers=H)
        self.assertEqual(bad.status_code, 422)

    def test_catalog_and_city_lists(self):
        import json
        from app.segment_catalog import CATALOG
        from app.segments import SEGMENTS
        keys = {s.key for s in SEGMENTS}
        self.assertTrue(all(group in keys for group, _, _ in CATALOG))
        geo_dir = Path(__file__).resolve().parent.parent / "static" / "geo"
        br = json.loads((geo_dir / "BR.json").read_text(encoding="utf-8"))
        pr = next(s for s in br["states"] if s["code"] == "PR")
        self.assertEqual((len(br["states"]), pr["capital"]), (27, "Curitiba"))
        self.assertGreater(sum(len(s["cities"]) for s in br["states"]), 5500)
        us = json.loads((geo_dir / "US.json").read_text(encoding="utf-8"))
        self.assertIn("Austin", next(s for s in us["states"] if s["code"] == "TX")["cities"])
        for code in ("CA", "GB", "AU"):
            self.assertTrue(json.loads((geo_dir / f"{code}.json").read_text(encoding="utf-8"))["states"])


class MigrationTests(unittest.TestCase):
    def test_v1_database_is_upgraded_without_losing_data(self):
        path = Path(tempfile.mkdtemp()) / "old.db"
        Database(path).init()
        conn = sqlite3.connect(path)
        conn.execute("DROP INDEX idx_leads_country")
        for col in ("country", "language", "utc_offset_minutes"):
            conn.execute(f"ALTER TABLE leads DROP COLUMN {col}")
        conn.execute("UPDATE schema_version SET version = 1")
        conn.execute("INSERT INTO leads (source, name, status, first_seen_at, last_seen_at, created_at, updated_at) "
                     "VALUES ('manual', 'Empresa Antiga', 'respondeu', 'x', 'x', 'x', 'x')")
        conn.commit()
        conn.close()
        Database(path).init()
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT name, status, country, language, utc_offset_minutes FROM leads").fetchone()
        self.assertEqual(tuple(row), ("Empresa Antiga", "respondeu", "BR", "pt", None))
        self.assertEqual(conn.execute("SELECT version FROM schema_version").fetchone()[0], 3)


if __name__ == "__main__":
    unittest.main()
