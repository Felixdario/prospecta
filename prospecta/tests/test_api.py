import csv
import io
import unittest

from starlette.testclient import TestClient

from app.jobs import Worker
from app.main import create_app
from app.site_analysis import FetchResult

from tests.helpers import ADMIN, GOOD_HTML, OLD_HTML, FakePlacesHttp, fake_fetcher, make_place, make_services

H = {"Authorization": f"Bearer {ADMIN}"}


def search_pages():
    return [[
        make_place(1),  # sem site, ótima reputação
        make_place(2, websiteUri="https://www.instagram.com/academia2"),
        make_place(3, websiteUri="https://academia3.com.br"),  # site bom
        make_place(4, websiteUri="http://academia4.com.br"),  # site antigo
        make_place(5, businessStatus="CLOSED_PERMANENTLY"),
        make_place(6, nationalPhoneNumber=None, internationalPhoneNumber=None),
    ]]


class ApiFlowTests(unittest.TestCase):
    def setUp(self):
        fetcher = fake_fetcher({
            "https://academia3.com.br": FetchResult("https://academia3.com.br", 200, GOOD_HTML, 200),
            "http://academia4.com.br": FetchResult("http://academia4.com.br", 200, OLD_HTML, 800),
        })
        self.svc = make_services(FakePlacesHttp(search_pages()), fetcher=fetcher)
        self.app = create_app(self.svc.config, self.svc, start_worker=False)
        self.client = TestClient(self.app)
        self.worker = Worker(self.svc)

    def run_search(self, **over):
        body = {"segment": "academias", "city": "Curitiba", "state": "PR", "max_results": 40, **over}
        r = self.client.post("/api/searches", json=body, headers=H)
        self.assertEqual(r.status_code, 202, r.text)
        self.assertTrue(self.worker.process_next())
        return self.client.get(f"/api/searches/{r.json()['id']}", headers=H).json()

    def test_auth_required(self):
        self.assertEqual(self.client.get("/api/leads").status_code, 401)
        self.assertEqual(self.client.get("/api/leads", headers={"Authorization": "Bearer errado"}).status_code, 401)
        self.assertEqual(self.client.get("/api/health").status_code, 200)
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Content-Security-Policy", r.headers)

    def test_search_flow_dedupe_scoring_messages(self):
        job = self.run_search()
        self.assertEqual(job["status"], "concluida", job)
        self.assertEqual(job["found"], 6)
        self.assertEqual(job["saved_new"], 4)
        self.assertEqual(job["discard_reasons"], {"fechada": 1, "sem_telefone": 1})
        self.assertEqual(job["api_calls"], 1)
        leads = self.client.get("/api/leads?sort=score", headers=H).json()
        self.assertEqual(leads["total"], 4)
        by_name = {l["name"]: l for l in leads["items"]}
        self.assertEqual(by_name["Academia Teste 1"]["presence_kind"], "sem_site")
        self.assertEqual(by_name["Academia Teste 1"]["priority"], "alta")
        self.assertEqual(by_name["Academia Teste 2"]["presence_kind"], "rede_social")
        self.assertEqual(by_name["Academia Teste 3"]["priority"], "media")
        self.assertEqual(leads["items"][0]["name"], "Academia Teste 1")
        # Alta prioridade recebe mensagem automática (modelo) e vai para revisão
        detail = self.client.get(f"/api/leads/{by_name['Academia Teste 1']['id']}", headers=H).json()
        self.assertEqual(detail["lead"]["status"], "aguardando_revisao")
        self.assertIn("Academia Teste 1", detail["lead"]["suggested_message"])
        self.assertTrue(detail["whatsapp_link"].startswith("https://wa.me/5541999990001?text="))
        self.assertEqual(detail["lead"]["segment"], "academia")
        # Site antigo: problemas verificados aparecem na análise
        old = self.client.get(f"/api/leads/{by_name['Academia Teste 4']['id']}", headers=H).json()
        codes = [i["code"] for i in old["lead"]["site_analysis"]["issues"]]
        self.assertIn("sem_meta_viewport", codes)
        # Segunda pesquisa: sem duplicatas, histórico preservado
        job2 = self.run_search()
        self.assertEqual((job2["saved_new"], job2["updated"]), (0, 4))
        self.assertEqual(self.client.get("/api/leads", headers=H).json()["total"], 4)
        self.assertEqual(self.client.get(f"/api/leads?search_id={job2['id']}", headers=H).json()["total"], 4)

    def test_filters(self):
        job = self.run_search(filters={"website": "sem_site_proprio", "min_reviews": 10, "only_mobile": True})
        self.assertEqual(job["saved_new"], 2)
        self.assertEqual(job["discard_reasons"].get("tem_site_proprio"), 2)

    def test_contact_flow_and_suppression(self):
        self.run_search()
        lead_id = self.client.get("/api/leads?q=Teste 1", headers=H).json()["items"][0]["id"]
        r = self.client.post(f"/api/leads/{lead_id}/interactions", json={"type": "mensagem_enviada", "channel": "whatsapp"}, headers=H)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["lead"]["status"], "contato_realizado")
        # Segundo envio logo em seguida é bloqueado (intervalo mínimo)
        r = self.client.post(f"/api/leads/{lead_id}/interactions", json={"type": "mensagem_enviada"}, headers=H)
        self.assertEqual(r.status_code, 409)
        self.assertTrue(any("menos de 3 dias" in b for b in r.json()["bloqueios"]))
        # Resposta e opt-out
        r = self.client.post(f"/api/leads/{lead_id}/interactions", json={"type": "resposta_recebida", "summary": "Pediu para não mandar mais"}, headers=H)
        self.assertEqual(r.json()["lead"]["status"], "respondeu")
        r = self.client.post(f"/api/leads/{lead_id}/interactions", json={"type": "opt_out"}, headers=H)
        self.assertEqual(r.json()["lead"]["status"], "nao_contatar")
        self.assertIsNone(r.json()["whatsapp_link"])
        sup = self.client.get("/api/suppression", headers=H).json()["items"]
        self.assertEqual({s["kind"] for s in sup}, {"phone", "place_id"})
        r = self.client.post(f"/api/leads/{lead_id}/interactions", json={"type": "mensagem_enviada", "override_reason": "teste"}, headers=H)
        self.assertEqual(r.status_code, 409)
        r = self.client.post(f"/api/leads/{lead_id}/message", json={"variant": "sem_site"}, headers=H)
        self.assertEqual(r.status_code, 400)
        r = self.client.post(f"/api/leads/{lead_id}/message", json={"variant": "opt_out"}, headers=H)
        self.assertEqual(r.status_code, 200)
        # Nova pesquisa não traz de volta quem está suprimido
        job = self.run_search()
        self.assertEqual(job["discard_reasons"].get("lista_de_supressao"), 1)

    def test_scoped_token_restrictions_and_audit(self):
        self.run_search()
        token = self.svc.repo.create_token("claude", ["leads:read", "leads:write"])
        T = {"Authorization": f"Bearer {token}"}
        lead_id = self.client.get("/api/leads?q=Teste 1", headers=T).json()["items"][0]["id"]
        self.assertEqual(self.client.post("/api/searches", json={"segment": "x1", "city": "Curitiba"}, headers=T).status_code, 403)
        self.assertEqual(self.client.get("/api/export.csv", headers=T).status_code, 403)
        self.assertEqual(self.client.delete(f"/api/leads/{lead_id}", headers=T).status_code, 403)
        r = self.client.post(f"/api/leads/{lead_id}/interactions", json={"type": "mensagem_enviada"}, headers=T)
        self.assertEqual(r.status_code, 403)
        self.assertIn("contacts:record", r.json()["erro"])
        self.client.post(f"/api/leads/{lead_id}/status", json={"status": "nao_contatar"}, headers=T)
        r = self.client.post(f"/api/leads/{lead_id}/status", json={"status": "qualificado"}, headers=T)
        self.assertEqual(r.status_code, 403)
        audit = self.client.get("/api/audit", headers=H).json()["items"]
        self.assertTrue(any(a["actor"] == "claude" and a["status"] == 403 for a in audit))
        self.assertTrue(any(a["actor"] == "claude" and a["method"] == "GET" for a in audit))

    def test_validation_errors(self):
        r = self.client.post("/api/searches", json={"segment": "a", "city": "Curitiba"}, headers=H)
        self.assertEqual(r.status_code, 422)
        r = self.client.post("/api/searches", json={"segment": "academias", "city": "Curitiba", "max_results": 9999}, headers=H)
        self.assertEqual(r.status_code, 422)
        r = self.client.post("/api/searches", json={"segment": "academias", "city": "Curitiba", "hack": 1}, headers=H)
        self.assertEqual(r.status_code, 422)
        r = self.client.put("/api/settings", json={"scoring": {"thresholds": {"alta": 10, "media": 50}}}, headers=H)
        self.assertEqual(r.status_code, 400)

    def test_export_import_tasks_settings_delete(self):
        self.run_search()
        r = self.client.get("/api/export.csv?priority=alta", headers=H)
        self.assertEqual(r.status_code, 200)
        text = r.content.decode("utf-8-sig")
        rows = list(csv.reader(io.StringIO(text), delimiter=";"))
        self.assertEqual(rows[0][:3], ["id", "empresa", "categoria"])
        self.assertTrue(all(row[16] == "alta" for row in rows[1:]))
        # Importação de planilha (formato do google-maps-scraper-kit)
        kit = "title,phone,website,category,address,review_rating,review_count\nBarbearia Kit,(41) 98888-1111,,Barbearia,Curitiba,4.9,120\nAcademia Teste 1,(41) 99999-0001,,Academia,Curitiba,4.7,150\n"
        r = self.client.post("/api/import", files={"file": ("leads.csv", kit.encode(), "text/csv")}, headers=H)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((r.json()["novos"], r.json()["atualizados"]), (1, 1))
        self.assertTrue(self.worker.process_next())
        imported = self.client.get("/api/leads?source=csv_importacao", headers=H).json()["items"][0]
        self.assertEqual(imported["segment"], "beleza")
        self.assertIsNotNone(imported["score"])
        # Tarefas
        r = self.client.post(f"/api/leads/{imported['id']}/tasks", json={"title": "Ligar à tarde", "due_date": "2026-01-01"}, headers=H)
        self.assertEqual(r.status_code, 201)
        overdue = self.client.get("/api/tasks?scope=overdue", headers=H).json()["items"]
        self.assertEqual(overdue[0]["lead_name"], "Barbearia Kit")
        self.assertEqual(self.client.patch(f"/api/tasks/{overdue[0]['id']}", json={"done": True}, headers=H).status_code, 200)
        # Configurações alteram a pontuação de todos
        r = self.client.put("/api/settings", json={"scoring": {"presence": {"sem_site": 0, "rede_social": 0}, "site_issue_cap": 0}}, headers=H)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.client.get("/api/leads?priority=alta", headers=H).json()["total"], 0)
        # Exclusão com supressão (direito de eliminação)
        r = self.client.delete(f"/api/leads/{imported['id']}?suppress=1", headers=H)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.get(f"/api/leads/{imported['id']}", headers=H).status_code, 404)
        self.assertTrue(any(s["value"] == "+5541988881111" for s in self.client.get("/api/suppression", headers=H).json()["items"]))

    def test_quota_stops_search(self):
        self.svc.config.google_textsearch_monthly_limit = 0
        job = self.run_search()
        self.assertEqual(job["status"], "falhou")
        self.assertIn("limite", job["error"])

    def test_google_cache_purge_and_refresh(self):
        self.run_search()
        lead = self.client.get("/api/leads?q=Teste 1", headers=H).json()["items"][0]
        with self.svc.repo.db.tx() as conn:
            conn.execute("UPDATE leads SET google_fetched_at = '2020-01-01T00:00:00+00:00', status = 'qualificado'")
        rep = self.client.post("/api/maintenance/google-cache", json={"mode": "report"}, headers=H).json()
        self.assertEqual(rep["expirados"], 4)
        self.svc.places_http.details[lead["place_id"]] = make_place(1, rating=4.9)
        self.client.post(f"/api/leads/{lead['id']}/status", json={"status": "respondeu"}, headers=H)
        out = self.client.post("/api/maintenance/google-cache", json={"mode": "refresh"}, headers=H).json()
        self.assertEqual((out["atualizados"], out["removidos"]), (1, 3), out)
        refreshed = self.client.get(f"/api/leads/{lead['id']}", headers=H).json()["lead"]
        self.assertEqual(refreshed["rating"], 4.9)
        purged = self.client.get("/api/leads?q=expirados", headers=H).json()
        self.assertEqual(purged["total"], 3)
        p = self.client.get(f"/api/leads/{purged['items'][0]['id']}", headers=H).json()["lead"]
        self.assertIsNone(p["phone"])
        self.assertTrue(p["place_id"])


if __name__ == "__main__":
    unittest.main()
