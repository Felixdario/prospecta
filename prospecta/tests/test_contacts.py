"""Contatos publicados pela empresa, recomendação de canal, mensagens por canal e painel de resultados."""
import unittest

from starlette.testclient import TestClient

from app.channels import recommend_channels
from app.insights import compute
from app.jobs import Worker
from app.main import create_app
from app.site_analysis import FetchResult, analyze_website

from tests.helpers import ADMIN, FakePlacesHttp, fake_fetcher, make_place, make_services

H = {"Authorization": f"Bearer {ADMIN}"}

SITE = """<html><head><title>Barbearia</title><meta name="viewport" content="w"><meta name="description" content="d"></head>
<body><a href="https://api.whatsapp.com/send?phone=5541988887777&amp;text=Oi">Agende</a>
<a href="https://www.instagram.com/barbearia.cortefino/">Instagram</a><a href="/contato">Fale conosco</a>{}</body></html>""".format("Texto. " * 60)
CONTACT_PAGE = '<html><body><a href="mailto:contato@cortefino.com.br">Escreva</a> ícone@2x.png</body></html>'
LINKTREE = ('<html><body><a href="https://wa.me/5541977776666">WhatsApp</a><a href="mailto:oi@pizzaria.com">E-mail</a>'
            '<a href="https://instagram.com/pizzaria.boa">Instagram</a></body></html>')


def fetcher():
    return fake_fetcher({
        "https://cortefino.com.br": FetchResult("https://cortefino.com.br", 200, SITE, 150),
        "https://cortefino.com.br/contato": FetchResult("https://cortefino.com.br/contato", 200, CONTACT_PAGE, 80),
        "https://linktr.ee/pizzariaboa": FetchResult("https://linktr.ee/pizzariaboa", 200, LINKTREE, 90),
    })


class ExtractionTests(unittest.TestCase):
    def test_site_and_contact_page(self):
        r = analyze_website("https://cortefino.com.br", fetcher())
        self.assertEqual(r["contacts"]["whatsapp"], ["+5541988887777"])
        self.assertEqual(r["contacts"]["emails"], ["contato@cortefino.com.br"])
        self.assertEqual(r["contacts"]["instagram"], "https://www.instagram.com/barbearia.cortefino/")

    def test_link_in_bio_and_wa_link_as_website(self):
        r = analyze_website("https://linktr.ee/pizzariaboa", fetcher())
        self.assertEqual(r["kind"], "agregador_links")
        self.assertEqual((r["contacts"]["whatsapp"], r["contacts"]["emails"]), (["+5541977776666"], ["oi@pizzaria.com"]))
        r = analyze_website("https://wa.me/5541966665555", fake_fetcher({}))
        self.assertEqual(r["contacts"]["whatsapp"], ["+5541966665555"])

    def test_no_solicitation_notice_skips_emails(self):
        for text in ("Não aceitamos propaganda por e-mail.", "No solicitations, please.", "Please do not send unsolicited offers."):
            html = f'<a href="mailto:oi@loja.com">oi@loja.com</a><p>{text}</p>'
            r = analyze_website("https://loja.com", fake_fetcher({"https://loja.com": FetchResult("https://loja.com", 200, html, 10)}))
            self.assertEqual((r["contacts"]["emails"], r["contacts"]["sem_ofertas"]), ([], True), text)
        ok = '<a href="mailto:oi@loja.com">Fale com a gente</a><p>Enviamos ofertas para clientes cadastrados.</p>'
        r = analyze_website("https://loja.com", fake_fetcher({"https://loja.com": FetchResult("https://loja.com", 200, ok, 10)}))
        self.assertEqual((r["contacts"]["emails"], r["contacts"]["sem_ofertas"]), (["oi@loja.com"], False))

    def test_emails_not_harvested_outside_brazil(self):
        html = '<a href="mailto:hi@shop.com">Email us</a><a href="https://wa.me/15125550123">WhatsApp</a>'
        for country in ("US", "CA", "GB", "AU"):
            r = analyze_website("https://shop.com", fake_fetcher({"https://shop.com": FetchResult("https://shop.com", 200, html, 10)}), country=country)
            self.assertEqual(r["contacts"]["emails"], [], country)
            self.assertEqual(r["contacts"]["whatsapp"], ["+15125550123"], country)

    def test_us_wa_link_without_country_code(self):
        html = '<a href="https://wa.me/5125550123">WhatsApp</a>'
        r = analyze_website("https://a.com", fake_fetcher({"https://a.com": FetchResult("https://a.com", 200, html, 10)}), country="US")
        self.assertEqual(r["contacts"]["whatsapp"], ["+15125550123"])


class ChannelTests(unittest.TestCase):
    def base(self, **over):
        lead = {"country": "BR", "phone_e164": "+554133334444", "phone_kind": "fixo", "social_links": {}, "emails": [],
                "site_analysis": {"kind": "sem_site", "signals": {}}, "name": "Pizzaria Boa", "city": "Curitiba"}
        lead.update(over)
        return lead

    def test_landline_brazil_prefers_call_over_unverified_whatsapp(self):
        keys = [(c["key"], c["basis"]) for c in recommend_channels(self.base())]
        self.assertEqual(keys, [("ligacao", "verificado"), ("whatsapp", "hipotese")])

    def test_verified_whatsapp_and_instagram_come_first(self):
        lead = self.base(whatsapp_e164="+5541977776666", social_links={"Instagram": "https://instagram.com/p"}, emails=["oi@p.com"])
        self.assertEqual([c["key"] for c in recommend_channels(lead)], ["whatsapp", "instagram", "ligacao", "email"])

    def test_no_whatsapp_mark_removes_guess(self):
        lead = self.base(phone_kind="celular", phone_e164="+5541999990000", whatsapp_status="sem_whatsapp")
        self.assertNotIn("whatsapp", [c["key"] for c in recommend_channels(lead)])

    def test_us_order(self):
        lead = self.base(country="US", phone_e164="+15125550101", phone_kind="indefinido", emails=["hi@a.com"],
                         site_analysis={"kind": "proprio", "signals": {"formulario": True}}, website="https://a.com")
        self.assertEqual([c["key"] for c in recommend_channels(lead)], ["ligacao", "email", "formulario"])
        self.assertIn("CAN-SPAM", recommend_channels(lead)[1]["reason"])
        lead["country"] = "GB"
        self.assertEqual([c["key"] for c in recommend_channels(lead)], ["ligacao", "formulario", "email", "whatsapp"])


class FlowTests(unittest.TestCase):
    def setUp(self):
        pages = [[make_place(1, websiteUri="https://cortefino.com.br", nationalPhoneNumber="(41) 3333-4444",
                             internationalPhoneNumber="+55 41 3333-4444", primaryType="barber_shop", types=["barber_shop"]),
                  make_place(2, websiteUri="https://linktr.ee/pizzariaboa", primaryType="pizza_restaurant", types=["pizza_restaurant"])]]
        self.svc = make_services(FakePlacesHttp(pages), fetcher=fetcher())
        self.client = TestClient(create_app(self.svc.config, self.svc, start_worker=False))
        self.client.post("/api/searches", json={"segment": "barbearias", "city": "Curitiba", "state": "PR",
                                                "filters": {"website": "todos"}}, headers=H)
        Worker(self.svc).process_next()
        items = self.client.get("/api/leads?sort=name", headers=H).json()["items"]
        self.ids = {i["name"]: i["id"] for i in items}
        self.barber = self.ids["Academia Teste 1"]
        self.pizza = self.ids["Academia Teste 2"]

    def test_contacts_saved_and_channels_in_detail(self):
        d = self.client.get(f"/api/leads/{self.barber}", headers=H).json()
        lead = d["lead"]
        self.assertEqual((lead["whatsapp_e164"], lead["whatsapp_source"]), ("+5541988887777", "site"))
        self.assertEqual(lead["emails"], ["contato@cortefino.com.br"])
        self.assertEqual(lead["social_links"]["Instagram"], "https://www.instagram.com/barbearia.cortefino/")
        self.assertEqual(d["best_channel"], "whatsapp")
        self.assertEqual(d["whatsapp_target"], "+5541988887777")
        self.assertIn("WhatsApp publicado", " ".join(i["label"] for i in lead["score_breakdown"]["items"]))
        listed = next(i for i in self.client.get("/api/leads", headers=H).json()["items"] if i["id"] == self.barber)
        self.assertEqual((listed["has_whatsapp"], listed["has_email"], listed["has_instagram"]), (1, 1, 1))

    def test_email_message_with_subject_and_recorded_channel(self):
        r = self.client.post(f"/api/leads/{self.barber}/message", json={"channel": "email"}, headers=H)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["channel"], "email")
        self.assertTrue(body["subject"])
        self.assertIn("responder \"não\"", body["message"])
        self.assertEqual(body["lead"]["message_channel"], "email")
        r = self.client.post(f"/api/leads/{self.barber}/interactions", json={"type": "mensagem_enviada", "channel": "email"}, headers=H)
        self.assertEqual(r.status_code, 200, r.text)
        self.client.post(f"/api/leads/{self.barber}/interactions", json={"type": "resposta_recebida", "channel": "email"}, headers=H)
        call = self.client.post(f"/api/leads/{self.pizza}/message", json={"channel": "ligacao"}, headers=H).json()
        self.assertEqual(call["variant"], "roteiro_ligacao")
        ins = self.client.get("/api/insights", headers=H).json()
        self.assertEqual((ins["contatados"], ins["responderam"], ins["taxa"]), (1, 1, 100.0))
        self.assertEqual(ins["por_canal"][0]["chave"], "email")
        self.assertEqual(ins["por_abordagem"][0]["chave"], body["variant"])
        self.assertEqual(ins["resposta_por_tentativa"], [{"tentativa": 1, "respostas": 1}])

    def test_no_whatsapp_and_manual_contacts(self):
        r = self.client.post(f"/api/leads/{self.pizza}/interactions", json={"type": "sem_whatsapp"}, headers=H)
        self.assertEqual(r.status_code, 200, r.text)
        lead = r.json()["lead"]
        self.assertIsNone(lead["whatsapp_e164"])  # o WhatsApp do Linktree foi descartado
        r = self.client.patch(f"/api/leads/{self.pizza}", json={"whatsapp": "(41) 95555-4444", "emails": "dono@pizzaria.com; x"}, headers=H)
        lead = r.json()["lead"]
        self.assertEqual((lead["whatsapp_e164"], lead["whatsapp_source"]), ("+5541955554444", "manual"))
        self.assertEqual(lead["emails"], ["dono@pizzaria.com"])
        self.assertEqual(r.json()["channels"][0]["reason"].split(" ")[0], "WhatsApp")
        facts = {x["texto"]: x["fonte"] for x in lead["analysis"]["fatos_verificados"]}
        self.assertTrue(facts["E-mail: dono@pizzaria.com"].startswith("Informado por você"))  # não diz "publicado"
        self.assertEqual(facts["WhatsApp: +5541955554444"], "Informado por você")
        self.assertEqual(facts["Instagram: https://instagram.com/pizzaria.boa"], "Link publicado pela empresa")

    def test_instagram_edit_and_discarded_whatsapp_not_readded(self):
        r = self.client.patch(f"/api/leads/{self.pizza}", json={"instagram": "@pizzaria.da.vila"}, headers=H)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["lead"]["social_links"]["Instagram"], "https://www.instagram.com/pizzaria.da.vila/")
        self.assertEqual(self.client.patch(f"/api/leads/{self.pizza}", json={"instagram": "https://evil.com/x"}, headers=H).status_code, 422)
        self.client.post(f"/api/leads/{self.pizza}/interactions", json={"type": "sem_whatsapp"}, headers=H)
        self.svc.analyze(self.pizza, "teste", refresh_site=True)  # o Linktree ainda publica o mesmo número
        lead = self.client.get(f"/api/leads/{self.pizza}", headers=H).json()["lead"]
        self.assertIsNone(lead["whatsapp_e164"])
        self.assertEqual(lead["social_links"]["Instagram"], "https://www.instagram.com/pizzaria.da.vila/")  # a correção do usuário fica
        r = self.client.patch(f"/api/leads/{self.pizza}", json={"instagram": ""}, headers=H)
        self.assertNotIn("Instagram", r.json()["lead"]["social_links"] or {})

    def test_reanalyze_job(self):
        r = self.client.post("/api/maintenance/reanalyze", headers=H)
        self.assertEqual(r.status_code, 202, r.text)
        self.assertTrue(Worker(self.svc).process_next())
        job = self.client.get(f"/api/searches/{r.json()['id']}", headers=H).json()
        self.assertEqual((job["status"], job["found"]), ("concluida", 2))


class AnyChannelTests(unittest.TestCase):
    """Dá para escolher qualquer canal, mesmo sem contato encontrado, e trocar a abordagem saindo da ligação."""

    def setUp(self):
        self.svc = make_services(FakePlacesHttp([]), fetcher=fake_fetcher({}))
        self.client = TestClient(create_app(self.svc.config, self.svc, start_worker=False))
        r = self.client.post("/api/leads", json={"name": "Legacy Nutrition", "country": "US", "phone": "(518) 212-2376",
                                                 "website": "http://www.facebook.com/legacynutrition518", "city": "Amsterdam",
                                                 "state": "NY"}, headers=H)
        self.assertIn(r.status_code, (200, 201), r.text)
        self.id = r.json()["id"]

    def test_options_list_every_channel_with_facebook_available(self):
        d = self.client.get(f"/api/leads/{self.id}", headers=H).json()
        opts = [(o["key"], o["available"]) for o in d["channel_options"]]
        self.assertEqual(opts[:2], [("ligacao", True), ("facebook", True)])
        self.assertEqual({k for k, _ in opts}, {"ligacao", "facebook", "email", "formulario", "instagram", "whatsapp"})
        self.assertEqual(d["messenger_url"], "https://m.me/legacynutrition518")
        wa = next(o for o in d["channel_options"] if o["key"] == "whatsapp")
        self.assertIn("TCPA", wa["reason"])  # EUA: sem WhatsApp suposto

    def test_written_variant_leaves_call_and_email_without_address(self):
        call = self.client.post(f"/api/leads/{self.id}/message", json={}, headers=H).json()
        self.assertEqual((call["channel"], call["variant"]), ("ligacao", "roteiro_ligacao"))
        r = self.client.post(f"/api/leads/{self.id}/message", json={"variant": "presenca_limitada", "channel": "ligacao"}, headers=H)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((r.json()["channel"], r.json()["variant"]), ("facebook", "presenca_limitada"))
        r = self.client.post(f"/api/leads/{self.id}/message", json={"channel": "email"}, headers=H).json()
        self.assertEqual(r["channel"], "email")
        self.assertTrue(r["subject"])
        self.assertTrue(any("Para" in w["motivo"] for w in r["warnings"]))
        self.assertIn("CAN-SPAM", " ".join(r["contact"]["warnings"]))
        r = self.client.patch(f"/api/leads/{self.id}", json={"emails": "info@legacynutrition.com"}, headers=H).json()
        self.assertEqual(r["channels"][1]["key"], "email")

    def test_facebook_patch(self):
        r = self.client.patch(f"/api/leads/{self.id}", json={"facebook": "fb.com/outra.pagina"}, headers=H)
        self.assertEqual(r.json()["lead"]["social_links"]["Facebook"], "https://www.facebook.com/outra.pagina")
        self.assertEqual(self.client.patch(f"/api/leads/{self.id}", json={"facebook": "https://evil.com/x"}, headers=H).status_code, 422)


class InsightsTests(unittest.TestCase):
    def test_counts_first_contact_and_attempt_of_reply(self):
        def ev(lead, type_, t, channel=None, variant=None):
            import json
            return {"lead_id": lead, "type": type_, "channel": channel, "created_at": t, "segment": "beleza", "country": "BR",
                    "status": "respondeu", "presence_kind": "sem_site", "details": json.dumps({"abordagem": variant}) if variant else None}
        rows = [ev(1, "mensagem_enviada", "1", "whatsapp", "sem_site"), ev(1, "mensagem_enviada", "2", "whatsapp", "follow_up"),
                ev(1, "resposta_recebida", "3"), ev(2, "mensagem_enviada", "1", "instagram", "abertura_curta"),
                ev(3, "sem_whatsapp", "1")]
        out = compute(rows)
        self.assertEqual((out["contatados"], out["responderam"], out["sem_whatsapp"]), (2, 1, 1))
        self.assertEqual(out["resposta_por_tentativa"], [{"tentativa": 2, "respostas": 1}])
        canais = {r["chave"]: (r["contatados"], r["responderam"]) for r in out["por_canal"]}
        self.assertEqual(canais, {"whatsapp": (1, 1), "instagram": (1, 0)})
        self.assertTrue(out["por_canal"][0]["amostra_pequena"])


if __name__ == "__main__":
    unittest.main()
