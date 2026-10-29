"""Servidor MCP do Prospecta: expõe a prospecção como ferramentas para o Claude.

O servidor MCP não acessa o banco diretamente. Ele chama a API REST do Prospecta com um
token próprio, e as permissões desse token definem o que a IA pode fazer. Todas as chamadas
ficam registradas na auditoria. Nenhuma ferramenta envia mensagens: o envio é sempre humano.

Variáveis de ambiente:
  PROSPECTA_API_URL   (padrão http://127.0.0.1:8000)
  PROSPECTA_TOKEN     token criado com: python -m app.cli create-token --name claude --scopes ...
  PROSPECTA_EXPORT_DIR pasta para exportações CSV (padrão: ./exports ao lado do projeto)

Uso (stdio):  python mcp_server/server.py
"""
from __future__ import annotations

import csv
import io
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

import requests
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

API_URL = os.environ.get("PROSPECTA_API_URL", "http://127.0.0.1:8000").rstrip("/")
EXPORT_DIR = Path(os.environ.get("PROSPECTA_EXPORT_DIR", Path(__file__).resolve().parent.parent / "exports"))

INSTRUCTIONS = """Ferramentas de prospecção de empresas locais para venda de sites (Prospecta).
Regras: use só dados retornados pelas ferramentas; diferencie fatos verificados de hipóteses;
nunca afirme que a empresa perde clientes; não prometa resultados. As mensagens são rascunhos
para revisão humana: você não envia mensagens. Respeite leads com status 'nao_contatar'.
Pesquisas no Google consomem cota paga: confirme com o usuário antes de pesquisas grandes."""

server = MCPServer("prospecta", instructions=INSTRUCTIONS, version="1.0.0")

READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
SEARCH = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True)


class Api:
    """Cliente HTTP da API REST. `session` pode ser substituída nos testes."""

    def __init__(self, base_url: str, token: str, session=None):
        self.base_url = base_url
        self.token = token
        self.session = session or requests.Session()

    def call(self, method: str, path: str, json: dict | None = None, params: dict | None = None, raw: bool = False):
        if not self.token:
            raise ToolError("PROSPECTA_TOKEN não configurado no servidor MCP.")
        try:
            r = self.session.request(method, self.base_url + path, json=json, params=params,
                                     headers={"Authorization": f"Bearer {self.token}"}, timeout=60)
        except requests.RequestException as e:
            raise ToolError(f"Não foi possível falar com o Prospecta em {self.base_url}. O servidor está rodando? ({e})")
        if r.status_code >= 400:
            try:
                data = r.json()
            except ValueError:
                data = {"erro": r.text[:300]}
            msg = data.get("erro", "Erro")
            extra = data.get("bloqueios") or data.get("detalhes")
            raise ToolError(f"{msg} (HTTP {r.status_code}){': ' + str(extra) if extra else ''}")
        return r.content if raw else r.json()


api = Api(API_URL, os.environ.get("PROSPECTA_TOKEN", ""))


def _lead_summary(item: dict) -> dict:
    keys = ("id", "name", "category", "neighborhood", "city", "country", "phone", "phone_kind", "website", "presence_kind",
            "rating", "reviews_count", "score", "priority", "status")
    return {k: item.get(k) for k in keys}


@server.tool(annotations=SEARCH)
def search_companies(segment: str, city: str, state: str = "", country: Literal["BR", "US", "CA", "GB", "AU"] = "BR",
                     regions: Optional[list[str]] = None, max_results: int = 20,
                     website_filter: Literal["todos", "sem_site", "sem_site_proprio", "com_site"] = "sem_site_proprio",
                     min_rating: Optional[float] = None, min_reviews: Optional[int] = None, only_mobile: bool = False,
                     wait_seconds: int = 90) -> dict:
    """Pesquisa empresas no Google (Places API oficial) por segmento e cidade, salva, analisa e pontua.
    `country`: BR (padrão), US, CA, GB ou AU. Fora do Brasil, escreva o segmento em inglês (ex.: "dentists")
    e as mensagens saem em inglês. Consome cota da API do Google (cada 20 resultados ≈ 1 chamada).
    Bairros em `regions` geram uma consulta por bairro. Aguarda até `wait_seconds` e devolve os leads por pontuação."""
    body = {"country": country, "segment": segment, "city": city, "state": state or None, "regions": regions or [], "max_results": max_results,
            "filters": {"website": website_filter, "min_rating": min_rating, "min_reviews": min_reviews,
                        "require_phone": True, "only_mobile": only_mobile}}
    job = api.call("POST", "/api/searches", json=body)
    deadline = time.monotonic() + max(0, min(wait_seconds, 300))
    while job["status"] in ("na_fila", "executando") and time.monotonic() < deadline:
        time.sleep(2)
        job = api.call("GET", f"/api/searches/{job['id']}")
    result = {"search_id": job["id"], "status": job["status"], "etapa": job["stage"], "encontradas": job["found"],
              "novas": job["saved_new"], "atualizadas": job["updated"], "descartadas": job["discard_reasons"],
              "alta_prioridade": job["high_priority"], "chamadas_google": job["api_calls"], "erro": job["error"]}
    if job["status"] in ("na_fila", "executando"):
        result["aviso"] = "A pesquisa continua em andamento. Consulte com get_search_status."
    else:
        leads = api.call("GET", "/api/leads", params={"search_id": job["id"], "sort": "score", "page_size": 25})
        result["leads"] = [_lead_summary(i) for i in leads["items"]]
    return result


@server.tool(annotations=READ)
def get_search_status(search_id: int) -> dict:
    """Consulta o andamento de uma pesquisa iniciada com search_companies."""
    return api.call("GET", f"/api/searches/{search_id}")


@server.tool(annotations=READ)
def list_leads(query: str = "", status: str = "", priority: str = "", presence: str = "", city: str = "", country: str = "",
               min_score: Optional[int] = None, sort: Literal["score", "recent", "name", "updated", "reviews"] = "score",
               limit: int = 20) -> dict:
    """Lista leads salvos com filtros. status/priority/presence aceitam vários valores separados por vírgula.
    presence: sem_site, com_site, limitada, rede_social, plataforma_terceiros, google_descontinuado."""
    params = {"q": query, "status": status, "priority": priority, "presence": presence, "city": city, "country": country,
              "min_score": min_score, "sort": sort, "page_size": max(1, min(limit, 50))}
    data = api.call("GET", "/api/leads", params={k: v for k, v in params.items() if v not in ("", None)})
    return {"total": data["total"], "leads": [_lead_summary(i) for i in data["items"]]}


@server.tool(annotations=READ)
def get_company_details(lead_id: int) -> dict:
    """Detalhes de um lead: dados coletados, diagnóstico do site, pontuação explicada, análise
    (fatos verificados x hipóteses), mensagem sugerida, política de contato, histórico e tarefas."""
    d = api.call("GET", f"/api/leads/{lead_id}")
    lead = d["lead"]
    keep = ("id", "name", "category", "segment", "address", "neighborhood", "city", "state", "country", "language",
            "utc_offset_minutes", "phone", "phone_e164", "phone_kind", "website", "whatsapp_e164", "whatsapp_source",
            "whatsapp_status", "emails", "message_channel", "message_subject",
            "maps_url", "rating", "reviews_count", "opening_hours", "business_status", "presence_kind", "social_links",
            "score", "priority", "status", "consent_status", "responsible_name", "notes", "suggested_message",
            "message_variant", "message_warnings", "preview_ready", "source", "google_fetched_at")
    return {
        "lead": {k: lead.get(k) for k in keep},
        "pontuacao": lead.get("score_breakdown"),
        "diagnostico_site": lead.get("site_analysis"),
        "analise": lead.get("analysis"),
        "proxima_acao": d["next_action"],
        "contato": {k: d["contact"].get(k) for k in ("allowed", "blockers", "warnings", "outbound_total", "last_outbound_at", "last_reply_at")},
        "hipotese_whatsapp": d["whatsapp_hypothesis"],
        "canais": d.get("channels"),
        "canal_recomendado": d.get("best_channel"),
        "historico": d["events"][:15],
        "tarefas_abertas": [t for t in d["tasks"] if not t["done"]],
    }


@server.tool(annotations=WRITE)
def analyze_online_presence(lead_id: int, refresh_site: bool = False, use_ai: bool = False) -> dict:
    """Analisa a presença digital (classifica o link do perfil e visita só a página inicial do site
    próprio, respeitando robots.txt) e recalcula a pontuação."""
    d = api.call("POST", f"/api/leads/{lead_id}/analyze", json={"refresh_site": refresh_site, "use_ai": use_ai})
    lead = d["lead"]
    return {"diagnostico_site": lead.get("site_analysis"), "pontuacao": lead.get("score_breakdown"), "analise": lead.get("analysis")}


@server.tool(annotations=WRITE)
def score_lead(lead_id: int) -> dict:
    """Recalcula a pontuação (0-100) com a explicação de cada critério (verificado x hipótese)."""
    return api.call("POST", f"/api/leads/{lead_id}/score", json={})


@server.tool(annotations=WRITE)
def generate_outreach_message(lead_id: int, variant: Optional[Literal[
        "abertura_curta", "sem_site", "presenca_limitada", "site_desatualizado", "site_existente", "responsavel_nao_identificado",
        "roteiro_ligacao", "follow_up", "follow_up_final", "resposta_interesse", "pedido_informacoes", "outro_horario",
        "opt_out"]] = None,
        channel: Optional[Literal["whatsapp", "instagram", "facebook", "email", "formulario", "ligacao"]] = None,
        use_ai: bool = False) -> dict:
    """Gera um RASCUNHO de mensagem para revisão humana (o envio é sempre feito por uma pessoa).
    Sem `variant`, o sistema escolhe pela situação do lead; sem `channel`, usa o canal recomendado.
    E-mails vêm com assunto. Retorna avisos do verificador de linguagem."""
    d = api.call("POST", f"/api/leads/{lead_id}/message", json={"variant": variant, "channel": channel, "use_ai": use_ai})
    return {"mensagem": d["message"], "assunto": d.get("subject"), "canal": d.get("channel"), "variacao": d["variant"],
            "gerada_por": d["generated_by"], "avisos": d["warnings"],
            "pode_contatar_agora": d["contact"]["allowed"], "bloqueios": d["contact"]["blockers"],
            "lembrete": "Rascunho para revisão. Quem envia é o usuário, pelo painel ou WhatsApp."}


@server.tool(annotations=WRITE)
def save_lead(name: str, phone: str = "", website: str = "", category: str = "", city: str = "", state: str = "",
              neighborhood: str = "", notes: str = "") -> dict:
    """Cadastra manualmente uma empresa (sem consultar o Google). Duplicatas são unificadas por telefone ou nome+cidade."""
    body = {k: v for k, v in {"name": name, "phone": phone, "website": website, "category": category, "city": city,
                              "state": state, "neighborhood": neighborhood, "notes": notes}.items() if v}
    d = api.call("POST", "/api/leads", json=body)
    return {"id": d["id"], "novo": d["novo"], "pontuacao": d["lead"]["score"], "prioridade": d["lead"]["priority"]}


@server.tool(annotations=WRITE)
def update_lead_status(lead_id: int, status: Literal[
        "identificado", "qualificado", "aguardando_revisao", "contato_realizado", "respondeu", "reuniao_agendada",
        "proposta_enviada", "convertido", "sem_interesse", "nao_contatar"], note: str = "") -> dict:
    """Atualiza a etapa comercial. 'nao_contatar' adiciona a empresa à lista de supressão (irreversível sem o administrador)."""
    d = api.call("POST", f"/api/leads/{lead_id}/status", json={"status": status, "note": note or None})
    return {"id": lead_id, "status": d["lead"]["status"], "proxima_acao": d["next_action"]}


@server.tool(annotations=WRITE)
def log_interaction(lead_id: int, type: Literal["resposta_recebida", "ligacao", "reuniao", "proposta", "nota", "opt_out",
                                                "sem_whatsapp"],
                    summary: str, channel: Optional[Literal["whatsapp", "telefone", "email", "formulario_site", "instagram",
                                                            "facebook", "presencial", "outro"]] = None) -> dict:
    """Registra no histórico uma resposta, ligação, reunião, proposta, anotação, pedido de não contato (opt_out)
    ou que o número não tem WhatsApp (sem_whatsapp)."""
    d = api.call("POST", f"/api/leads/{lead_id}/interactions", json={"type": type, "summary": summary, "channel": channel})
    return {"id": lead_id, "status": d["lead"]["status"], "proxima_acao": d["next_action"]}


@server.tool(annotations=WRITE)
def create_follow_up_task(lead_id: int, title: str, due_date: str) -> dict:
    """Cria uma tarefa de acompanhamento. due_date no formato AAAA-MM-DD."""
    return api.call("POST", f"/api/leads/{lead_id}/tasks", json={"title": title, "due_date": due_date})


@server.tool(annotations=READ)
def list_follow_up_tasks(scope: Literal["today", "overdue", "open", "all"] = "today") -> dict:
    """Lista tarefas: today (vencem até hoje), overdue (atrasadas), open (abertas) ou all."""
    return api.call("GET", "/api/tasks", params={"scope": scope})


@server.tool(annotations=WRITE)
def export_leads(priority: str = "", status: str = "", presence: str = "", city: str = "", min_score: Optional[int] = None) -> dict:
    """Exporta leads filtrados para um arquivo CSV (separador ';', abre no Excel e no Google Sheets)."""
    params = {k: v for k, v in {"priority": priority, "status": status, "presence": presence, "city": city,
                                "min_score": min_score}.items() if v not in ("", None)}
    content = api.call("GET", "/api/export.csv", params=params, raw=True)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = EXPORT_DIR / f"leads-{datetime.now():%Y%m%d-%H%M%S}.csv"
    path.write_bytes(content)
    rows = list(csv.reader(io.StringIO(content.decode("utf-8-sig")), delimiter=";"))
    return {"arquivo": str(path), "linhas": max(0, len(rows) - 1)}


if __name__ == "__main__":
    server.run("stdio")
