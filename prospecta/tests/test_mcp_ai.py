import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from starlette.testclient import TestClient

from app.ai import ClaudeWriter, generate
from app.main import create_app
from mcp_server import server as mcp

from tests.helpers import ADMIN, FakePlacesHttp, make_place, make_services
from tests.test_units import SELLER, lead


class FakeClaude:
    def __init__(self, payload: dict | str):
        self.payload = payload
        self.requests = []

    def __call__(self, url, headers, payload, timeout):
        self.requests.append({"url": url, "headers": headers, "payload": payload})
        text = self.payload if isinstance(self.payload, str) else json.dumps(self.payload, ensure_ascii=False)
        return {"content": [{"type": "text", "text": text}]}


GOOD_AI = {
    "resumo": "Academia no Batel com nota 4,8 e sem site próprio identificado.",
    "justificativa": "Um site poderia reunir planos e horários em um só lugar.",
    "hipoteses": ["Pode receber muitas perguntas sobre horários pelo telefone."],
    "mensagem": "Boa tarde, tudo bem? Sou o Eduardo, trabalho com criação de sites há mais de 3 anos. Encontrei a Academia Teste no Google Maps e não encontrei um site próprio de vocês. Uma página simples poderia mostrar planos, horários e modalidades. Você cuida dessa parte? Posso mostrar uma proposta sem compromisso.",
}


class AiTests(unittest.TestCase):
    def test_ai_message_used_when_clean(self):
        fake = FakeClaude(GOOD_AI)
        w = ClaudeWriter("key", "claude-haiku-5-5", post=fake)
        out = generate(lead(), "sem_site", SELLER, "America/Sao_Paulo", w, True)
        self.assertEqual(out["generated_by"], "ia")
        self.assertEqual(out["message"], GOOD_AI["mensagem"])
        req = fake.requests[0]
        self.assertEqual(req["payload"]["model"], "claude-haiku-5-5")
        self.assertEqual(req["headers"]["anthropic-version"], "2023-06-01")
        self.assertIn("Nota 4,8 com 212 avaliações", req["payload"]["messages"][0]["content"])
        self.assertIn("NÃO preparou prévia", req["payload"]["messages"][0]["content"])
        # Fatos verificados continuam vindo do sistema, não da IA
        self.assertTrue(all("fonte" in f for f in out["analysis"]["fatos_verificados"]))
        self.assertEqual(out["analysis"]["hipoteses_ia"], GOOD_AI["hipoteses"])

    def test_ai_message_rejected_by_lint(self):
        bad = dict(GOOD_AI, mensagem="Olá! Vocês estão perdendo clientes sem site. Garanto resultados!")
        out = generate(lead(), "sem_site", SELLER, "America/Sao_Paulo", ClaudeWriter("k", "m", post=FakeClaude(bad)), True)
        self.assertEqual(out["generated_by"], "modelo")
        self.assertTrue(any("descartado" in w["motivo"] for w in out["warnings"]))

    def test_ai_failure_falls_back(self):
        out = generate(lead(), "sem_site", SELLER, "America/Sao_Paulo", ClaudeWriter("k", "m", post=FakeClaude("não é json")), True)
        self.assertEqual(out["generated_by"], "modelo")
        self.assertTrue(any("IA indisponível" in w["motivo"] for w in out["warnings"]))


class TestClientSession:
    """Adapta o TestClient do Starlette para a interface requests.Session usada pelo servidor MCP."""

    def __init__(self, client):
        self.client = client

    def request(self, method, url, json=None, params=None, headers=None, timeout=None):
        return self.client.request(method, url.replace("http://mcp-test", ""), json=json, params=params, headers=headers)


class McpTests(unittest.TestCase):
    def setUp(self):
        self.svc = make_services(FakePlacesHttp([[make_place(1), make_place(2, websiteUri="https://instagram.com/x")]]))
        self.app = create_app(self.svc.config, self.svc, start_worker=True)
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        token = self.svc.repo.create_token("claude", ["leads:read", "leads:write", "search:run", "export"])
        mcp.api = mcp.Api("http://mcp-test", token, session=TestClientSession(self.client))
        mcp.EXPORT_DIR = Path(tempfile.mkdtemp())

    def call(self, name, **args):
        result = asyncio.run(mcp.server.call_tool(name, args))
        self.assertFalse(getattr(result, "is_error", False) or getattr(result, "isError", False), result)
        sc = getattr(result, "structured_content", None) or getattr(result, "structuredContent", None)
        if sc is not None:
            return sc.get("result", sc)
        return json.loads(result.content[0].text)

    def test_tools_listed_with_annotations(self):
        tools = {t.name: t for t in asyncio.run(mcp.server.list_tools())}
        expected = {"search_companies", "get_search_status", "list_leads", "get_company_details", "analyze_online_presence",
                    "score_lead", "generate_outreach_message", "save_lead", "update_lead_status", "log_interaction",
                    "create_follow_up_task", "list_follow_up_tasks", "export_leads"}
        self.assertEqual(set(tools), expected)
        self.assertTrue(tools["list_leads"].annotations.read_only_hint if hasattr(tools["list_leads"].annotations, "read_only_hint") else tools["list_leads"].annotations.readOnlyHint)

    def test_end_to_end_through_mcp(self):
        out = self.call("search_companies", segment="academias", city="Curitiba", state="PR", website_filter="todos", wait_seconds=20)
        self.assertEqual(out["status"], "concluida", out)
        self.assertEqual(len(out["leads"]), 2)
        lead_id = out["leads"][0]["id"]
        details = self.call("get_company_details", lead_id=lead_id)
        self.assertIn("fatos_verificados", details["analise"])
        msg = self.call("generate_outreach_message", lead_id=lead_id)
        self.assertIn("Academia Teste", msg["mensagem"])
        self.assertIn("revisão", msg["lembrete"])
        task = self.call("create_follow_up_task", lead_id=lead_id, title="Retomar contato", due_date="2026-11-03")
        self.assertIn("id", task)
        self.assertEqual(self.call("update_lead_status", lead_id=lead_id, status="qualificado")["status"], "qualificado")
        exp = self.call("export_leads", priority="alta")
        self.assertTrue(Path(exp["arquivo"]).exists())
        # A IA não consegue registrar envio de mensagem nem excluir supressões
        r = asyncio.run(mcp.server.call_tool("update_lead_status", {"lead_id": lead_id, "status": "nao_contatar"}))
        with self.assertRaises(Exception) as ctx:
            asyncio.run(mcp.server.call_tool("update_lead_status", {"lead_id": lead_id, "status": "qualificado"}))
        self.assertIn("administrador", str(ctx.exception))
        audit = self.client.get("/api/audit", headers={"Authorization": f"Bearer {ADMIN}"}).json()["items"]
        self.assertTrue(any(a["actor"] == "claude" and a["path"] == "/api/searches" for a in audit))


if __name__ == "__main__":
    unittest.main()
