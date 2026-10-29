import unittest
from datetime import datetime, timedelta, timezone

from app.messages import build_analysis, choose_variant, lint_message, render_template
from app.phones import normalize_br_phone, whatsapp_link
from app.pipeline import contact_check, contact_stats, next_action
from app.scoring import score_lead
from app.site_analysis import FetchResult, UnsafeURL, analyze_website, assert_public_host, classify_url
from app.sources.csv_import import parse_csv
from app.sources.places import PlacesClient, PlacesError, QuotaExceeded, SEARCH_FIELD_MASK, map_place

from tests.helpers import GOOD_HTML, OLD_HTML, FakePlacesHttp, fake_fetcher, make_place

SELLER = {"nome": "Eduardo Felix", "primeiro_nome": "Eduardo", "experiencia": "há mais de 3 anos", "empresa": ""}
NOW = datetime(2026, 10, 26, 15, 0, tzinfo=timezone.utc)  # 12h em São Paulo, segunda-feira


class PhoneTests(unittest.TestCase):
    def test_mobile_landline_special(self):
        p = normalize_br_phone("+55 (41) 99876-5432")
        self.assertEqual((p.kind, p.e164, p.display()), ("celular", "+5541998765432", "(41) 99876-5432"))
        p = normalize_br_phone("41 3333-4444")
        self.assertEqual((p.kind, p.e164), ("fixo", "+554133334444"))
        self.assertEqual(normalize_br_phone("0800 123 4567").kind, "especial")
        self.assertEqual(normalize_br_phone("12345").kind, "invalido")
        self.assertIsNone(normalize_br_phone(""))

    def test_whatsapp_link_encodes_text(self):
        url = whatsapp_link("+5541998765432", "Olá, tudo bem? R$ & site")
        self.assertTrue(url.startswith("https://wa.me/5541998765432?text="))
        self.assertIn("Ol%C3%A1%2C%20tudo%20bem%3F", url)
        self.assertNotIn("&", url.split("?text=")[1])


class SiteAnalysisTests(unittest.TestCase):
    def test_classification_without_network(self):
        self.assertEqual(classify_url(None)[0], "sem_site")
        self.assertEqual(classify_url("https://www.instagram.com/x"), ("rede_social", "Instagram"))
        self.assertEqual(classify_url("linktr.ee/abc"), ("agregador_links", "Linktree"))
        self.assertEqual(classify_url("https://abc.business.site")[0], "google_descontinuado")
        self.assertEqual(classify_url("https://www.ifood.com.br/delivery/x"), ("plataforma_terceiros", "iFood"))
        self.assertEqual(classify_url("https://x.wixsite.com/y"), ("proprio", "Wix (gratuito)"))
        self.assertEqual(classify_url("https://academia.com.br"), ("proprio", None))

    def test_social_link_is_never_fetched(self):
        f = fake_fetcher({})
        r = analyze_website("https://instagram.com/empresa", f)
        self.assertEqual(r["kind"], "rede_social")
        self.assertEqual(f.calls, [])

    def test_good_site(self):
        f = fake_fetcher({"https://academiaboa.com.br": FetchResult("https://academiaboa.com.br", 200, GOOD_HTML, 300)})
        r = analyze_website("https://academiaboa.com.br", f, now=NOW)
        self.assertTrue(r["fetched"])
        self.assertEqual([i["code"] for i in r["issues"]], [])
        self.assertTrue(r["signals"]["link_whatsapp"])
        self.assertIn("Instagram", r["social_links"])

    def test_old_site_issues_with_basis(self):
        f = fake_fetcher({"http://oficina.com.br": FetchResult("http://oficina.com.br", 200, OLD_HTML, 5200)})
        r = analyze_website("oficina.com.br", f, now=NOW)
        codes = {i["code"]: i["basis"] for i in r["issues"]}
        for code in ("sem_https", "sem_meta_viewport", "tecnologia_obsoleta", "sem_titulo", "sem_contato_direto"):
            self.assertEqual(codes.get(code), "verificado", code)
        self.assertEqual(codes["rodape_desatualizado"], "hipotese")
        self.assertEqual(codes["lento"], "hipotese")
        self.assertEqual(r["signals"]["ano_rodape"], 2016)

    def test_offline_and_robots(self):
        f = fake_fetcher({"http://fora.com.br": ConnectionError("timeout")})
        r = analyze_website("fora.com.br", f, now=NOW)
        self.assertEqual(r["issues"][0]["code"], "site_fora_do_ar")
        f = fake_fetcher({"http://bloq.com.br/robots.txt": FetchResult("http://bloq.com.br/robots.txt", 200, "User-agent: *\nDisallow: /", 5)})
        r = analyze_website("bloq.com.br", f, user_agent="ProspectaBot", now=NOW)
        self.assertIn("robots.txt", r["skipped_reason"])
        self.assertEqual(f.calls, ["http://bloq.com.br/robots.txt"])

    def test_ssrf_guard(self):
        for host in ("localhost", "127.0.0.1", "10.0.0.5", "169.254.169.254"):
            with self.assertRaises(UnsafeURL):
                assert_public_host(host)
        f = lambda url: (_ for _ in ()).throw(UnsafeURL("interno"))  # noqa: E731
        r = analyze_website("http://intranet.local", f, now=NOW)
        self.assertIn("bloqueado", r["skipped_reason"])


def lead(**over):
    base = {"id": 1, "name": "Academia Teste", "source": "google_places", "segment": "academia", "category": "Academia",
            "city": "Curitiba", "state": "PR", "neighborhood": "Batel", "rating": 4.8, "reviews_count": 212,
            "phone": "(41) 99999-0001", "phone_e164": "+5541999990001", "phone_kind": "celular", "website": None,
            "business_status": "OPERATIONAL", "status": "identificado", "google_fetched_at": "2026-10-26T12:00:00+00:00",
            "site_analysis": {"kind": "sem_site", "issues": []}, "consent_status": "nao_registrado", "contact_count": 0}
    base.update(over)
    return base


class ScoringTests(unittest.TestCase):
    def test_no_site_great_reputation_is_high(self):
        r = score_lead(lead())
        self.assertEqual(r["priority"], "alta")
        self.assertEqual(r["score"], 40 + 20 + 10 + 10 + 5 + 10)
        bases = {i["code"]: i["basis"] for i in r["items"]}
        self.assertEqual(bases["presenca_sem_site"], "verificado")
        self.assertEqual(bases["segmento"], "hipotese")
        self.assertEqual(bases["celular"], "hipotese")

    def test_good_site_is_low(self):
        r = score_lead(lead(website="https://a.com.br", site_analysis={"kind": "proprio", "fetched": True, "issues": []}, rating=4.1, reviews_count=12))
        self.assertEqual(r["priority"], "baixa")
        self.assertIn("site_ok", [i["code"] for i in r["items"]])

    def test_issue_cap_and_penalties(self):
        issues = [{"code": c, "label": c, "basis": "verificado"} for c in ("site_fora_do_ar", "sem_https", "sem_meta_viewport")]
        r = score_lead(lead(website="http://x.com.br", site_analysis={"kind": "proprio", "issues": issues}, rating=3.2, reviews_count=2))
        site_points = sum(i["points"] for i in r["items"] if i["code"].startswith("site_"))
        self.assertEqual(site_points, 35)
        codes = [i["code"] for i in r["items"]]
        self.assertIn("nota_baixa", codes)
        self.assertIn("poucas_avaliacoes", codes)

    def test_closed_business_zero(self):
        r = score_lead(lead(business_status="CLOSED_PERMANENTLY"))
        self.assertEqual((r["score"], r["priority"]), (0, "baixa"))

    def test_config_override(self):
        r = score_lead(lead(), {"presence": {"sem_site": 10}, "thresholds": {"alta": 90, "media": 50}})
        self.assertEqual(r["score"], 10 + 20 + 10 + 10 + 5 + 10)
        self.assertEqual(r["priority"], "media")


class MessageTests(unittest.TestCase):
    def test_no_site_message_is_clean_and_personal(self):
        msg = render_template(lead(), "sem_site", SELLER, now=datetime(2026, 10, 26, 14, 0))
        # Começa pela empresa (não por "Meu nome é"), é curta e termina com pergunta de interesse
        self.assertTrue(msg.startswith("Oi, tudo bem? Vi a Academia Teste no Google: nota 4,8 com 212 avaliações"), msg)
        self.assertIn("Sou o Eduardo", msg)
        self.assertIn("planos, horários e modalidades", msg)
        self.assertTrue(msg.rstrip().endswith("Sem compromisso."))
        self.assertLess(len(msg), 400)
        self.assertEqual(lint_message(msg, lead(), "whatsapp", "sem_site"), [])

    def test_email_format_has_subject_signature_and_opt_out(self):
        from app.messages import render_subject
        seller = dict(SELLER, whatsapp="(41) 99999-0000", portfolio="https://exemplo.dev")
        msg = render_template(lead(), "sem_site", seller, channel="email")
        self.assertIn("\n\nEduardo Felix\nWhatsApp: (41) 99999-0000\nTrabalhos: https://exemplo.dev", msg)
        self.assertIn("responder \"não\"", msg)
        self.assertEqual(render_subject(lead(), "sem_site"), "Site para a Academia Teste")
        self.assertEqual(render_subject(lead(), "follow_up"), "Re: Site para a Academia Teste")
        self.assertEqual(lint_message(msg, lead(), "email", "sem_site"), [])
        no_optout = msg.split("\n\nSe não quiser")[0]
        self.assertTrue(any("não receber mais" in w["motivo"] for w in lint_message(no_optout, lead(), "email", "sem_site")))

    def test_articles_and_behavioral_lint(self):
        from app.messages import _articles
        self.assertEqual(_articles("Restaurante Sabor")["pela"], "pelo")
        self.assertEqual(_articles("Barbearia X")["da"], "da")
        self.assertIsNone(_articles("Corte & Cia"))
        msg = render_template(lead(name="Restaurante Sabor"), "abertura_curta", SELLER)
        self.assertIn("responsável pelo Restaurante Sabor?", msg)
        self.assertLess(len(msg), 220)
        warn = lint_message("Boa tarde, tudo bem? Meu nome é Eduardo e vendo sites. Veja https://x.com", lead(), "whatsapp", "sem_site")
        motivos = " ".join(w["motivo"] for w in warn)
        self.assertIn("Comece falando da empresa", motivos)
        self.assertIn("Link na primeira mensagem", motivos)

    def test_follow_up_sequence(self):
        from app.messages import choose_variant
        self.assertEqual(choose_variant(lead(status="contato_realizado", contact_count=1)), "follow_up")
        self.assertEqual(choose_variant(lead(status="contato_realizado", contact_count=2)), "follow_up_final")
        fu = render_template(lead(), "follow_up", SELLER)
        self.assertIn("Quer que eu te mande um exemplo?", fu)
        self.assertIn("sem problema", fu)
        self.assertIn("Vou parar de mandar mensagem", render_template(lead(), "follow_up_final", SELLER))

    def test_all_variants_pass_lint(self):
        cases = [lead(), lead(site_analysis={"kind": "rede_social", "platform": "Instagram", "issues": []}, website="https://instagram.com/x"),
                 lead(website="http://x.com.br", site_analysis={"kind": "proprio", "issues": [{"code": "sem_meta_viewport", "label": "x", "basis": "verificado"}]}),
                 lead(website="http://x.com.br", site_analysis={"kind": "proprio", "issues": []})]
        from app.messages import VARIANTS
        from app.messages import variant_incompatibility
        for ld in cases:
            for v in VARIANTS:
                if variant_incompatibility(ld, v):
                    continue  # o serviço recusa variações que não combinam com os dados
                msg = render_template(ld, v, SELLER)
                blocking = [w for w in lint_message(msg, ld) if w["nivel"] == "bloqueante"]
                self.assertEqual(blocking, [], f"{v}: {msg}")
                self.assertNotIn("  ", msg)
        site = cases[3]
        self.assertTrue(variant_incompatibility(site, "sem_site"))
        self.assertTrue(variant_incompatibility(site, "presenca_limitada"))
        self.assertTrue(variant_incompatibility(site, "site_desatualizado"))
        self.assertIsNone(variant_incompatibility(site, "site_existente"))
        # Mesmo se alguém escrever, o verificador barra "não encontrei site" para quem tem site
        self.assertTrue([w for w in lint_message("Reparei que vocês ainda não têm um site próprio.", site) if w["nivel"] == "bloqueante"])

    def test_lint_catches_bad_claims(self):
        site_lead = lead(website="http://x.com.br", site_analysis={"kind": "proprio", "issues": []})
        reasons = " ".join(w["motivo"] for w in lint_message("Vocês estão perdendo clientes! Garanto que vai dobrar as vendas. Não encontrei um site. Nota 3,9", site_lead))
        for expected in ("perde clientes", "garantia", "exagerada", "não há site", "Nota citada"):
            self.assertIn(expected, reasons)

    def test_variant_choice_and_preview(self):
        self.assertEqual(choose_variant(lead()), "sem_site")
        self.assertEqual(choose_variant(lead(site_analysis={"kind": "agregador_links", "issues": []})), "presenca_limitada")
        self.assertEqual(choose_variant(lead(site_analysis={"kind": "desconhecido", "issues": []})), "responsavel_nao_identificado")
        self.assertEqual(choose_variant(lead(status="nao_contatar")), "opt_out")
        msg = render_template(lead(preview_ready=True, preview_url="https://previa.exemplo/academia"), "sem_site", SELLER)
        self.assertIn("Montei uma prévia", msg)
        self.assertIn("Posso te mandar o link?", msg)
        self.assertNotIn("https://", msg)  # o link só vai depois que a pessoa aceitar
        self.assertNotIn("prévia", render_template(lead(), "sem_site", SELLER))

    def test_analysis_separates_facts_and_hypotheses(self):
        a = build_analysis(lead())
        facts = " ".join(f["texto"] for f in a["fatos_verificados"])
        self.assertIn("Nenhum site informado", facts)
        self.assertIn("Nota 4,8 com 212", facts)
        self.assertTrue(all("fonte" in f for f in a["fatos_verificados"]))
        self.assertTrue(any("não verificado" in h for h in a["hipoteses"]))


class PolicyTests(unittest.TestCase):
    def ev(self, type_, days_ago):
        return {"type": type_, "created_at": (NOW - timedelta(days=days_ago)).isoformat()}

    def test_allowed_first_contact(self):
        r = contact_check(lead(), contact_stats([]), [], 0, {}, now=NOW)
        self.assertTrue(r["allowed"])
        self.assertTrue(any("consentimento" in w for w in r["warnings"]))

    def test_blockers(self):
        self.assertFalse(contact_check(lead(status="nao_contatar"), contact_stats([]), [], 0, {}, now=NOW)["allowed"])
        self.assertFalse(contact_check(lead(), contact_stats([]), [{"kind": "phone", "value": "+55"}], 0, {}, now=NOW)["allowed"])
        self.assertFalse(contact_check(lead(), contact_stats([]), [], 20, {"daily_limit": 20}, now=NOW)["allowed"])
        self.assertFalse(contact_check(lead(phone_e164=None), contact_stats([]), [], 0, {}, now=NOW)["allowed"])
        recent = contact_stats([self.ev("mensagem_enviada", 1)])
        r = contact_check(lead(status="contato_realizado"), recent, [], 0, {}, now=NOW)
        self.assertFalse(r["allowed"])
        self.assertIn("menos de 3 dias", r["blockers"][0])
        two = contact_stats([self.ev("mensagem_enviada", 10), self.ev("mensagem_enviada", 5)])
        self.assertTrue(contact_check(lead(status="contato_realizado"), two, [], 0, {}, now=NOW)["allowed"])  # ainda cabe o encerramento
        three = contact_stats([self.ev("mensagem_enviada", 15), self.ev("mensagem_enviada", 10), self.ev("mensagem_enviada", 5)])
        self.assertFalse(contact_check(lead(status="contato_realizado"), three, [], 0, {}, now=NOW)["allowed"])
        only_email = lead(phone_e164=None, emails=["contato@a.com"])
        self.assertTrue(contact_check(only_email, contact_stats([]), [], 0, {}, now=NOW)["allowed"])
        replied = contact_stats([self.ev("mensagem_enviada", 10), self.ev("mensagem_enviada", 5), self.ev("resposta_recebida", 4)])
        self.assertTrue(contact_check(lead(status="respondeu"), replied, [], 0, {}, now=NOW)["allowed"])

    def test_next_action(self):
        stats = contact_stats([self.ev("mensagem_enviada", 4)])
        self.assertEqual(next_action(lead(status="contato_realizado"), stats, [], {}, now=NOW), "Enviar o follow-up com uma proposta concreta")
        self.assertIn("Tarefa", next_action(lead(), {}, [{"title": "Ligar", "due_date": "2026-10-30"}], {}, now=NOW))


class CsvTests(unittest.TestCase):
    def test_kit_format_and_portuguese(self):
        kit = b"title,phone,emails,website,category,address,review_rating,review_count\nAcademia X,+55 41 99999-0000,a@b.com,,Academia,\"Rua 1, Curitiba\",4.6,80\n"
        rows, errors = parse_csv(kit)
        self.assertEqual(errors, [])
        self.assertEqual(rows[0]["name"], "Academia X")
        self.assertEqual(rows[0]["emails"], "a@b.com")
        self.assertTrue(rows[0]["has_website_column"])
        pt = "nome;telefone;cidade;nota\nSalão Y;(41) 3333-4444;Curitiba;4,5\n;;;\n".encode("cp1252")
        rows, errors = parse_csv(pt)
        self.assertEqual((rows[0]["name"], rows[0]["rating"], rows[0]["has_website_column"]), ("Salão Y", 4.5, False))
        self.assertEqual(len(errors), 1)
        rows, errors = parse_csv(b"foo,bar\n1,2\n")
        self.assertEqual(rows, [])
        self.assertIn("Coluna de nome", errors[0])


class PlacesClientTests(unittest.TestCase):
    def client(self, http, limit=100):
        calls = {"n": 0}

        def guard(sku):
            calls["n"] += 1
            if calls["n"] > limit:
                raise QuotaExceeded("limite")
        return PlacesClient("key", guard, http=http, sleep=lambda s: None), calls

    def test_pagination_field_mask_and_cap(self):
        http = FakePlacesHttp([[make_place(i) for i in range(20)], [make_place(i) for i in range(20, 40)], [make_place(i) for i in range(40, 45)]])
        c, _ = self.client(http)
        places = list(c.search_text("academias em Curitiba - PR", max_results=60, min_rating=4.2))
        self.assertEqual(len(places), 45)
        self.assertEqual(len(http.requests), 3)
        first = http.requests[0]
        self.assertEqual(first["headers"]["X-Goog-FieldMask"], SEARCH_FIELD_MASK)
        self.assertIn("nextPageToken", SEARCH_FIELD_MASK)
        self.assertEqual(first["body"]["minRating"], 4.0)
        self.assertEqual(first["body"]["languageCode"], "pt-BR")
        self.assertEqual(http.requests[1]["body"]["pageToken"], "page-1")
        c2, _ = self.client(FakePlacesHttp([[make_place(i) for i in range(20)], [make_place(i) for i in range(20, 40)]]))
        self.assertEqual(len(list(c2.search_text("x", max_results=25))), 25)

    def test_retry_and_errors(self):
        http = FakePlacesHttp([[make_place(1)]], statuses=[503, 200])
        c, _ = self.client(http)
        self.assertEqual(len(list(c.search_text("x"))), 1)
        c, _ = self.client(FakePlacesHttp([[make_place(1)]], statuses=[403]))
        with self.assertRaises(PlacesError) as ctx:
            list(c.search_text("x"))
        self.assertIn("faturamento", str(ctx.exception))
        c, _ = self.client(FakePlacesHttp([[make_place(1)], [make_place(2)]]), limit=1)
        it = c.search_text("x")
        next(it)
        with self.assertRaises(QuotaExceeded):
            next(it)

    def test_map_place(self):
        d = map_place(make_place(7))
        self.assertEqual((d["name"], d["city"], d["state"], d["neighborhood"]), ("Academia Teste 7", "Curitiba", "PR", "Batel"))
        self.assertEqual(d["opening_hours"], ["segunda-feira: 06:00–22:00"])


if __name__ == "__main__":
    unittest.main()
