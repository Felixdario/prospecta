"""Integração opcional com a API do Claude (Anthropic) para redigir análises e mensagens.

Separação de responsabilidades:
- Fatos verificados e pontuação são calculados pelo sistema, nunca pela IA.
- A IA recebe apenas esses dados e escreve resumo, justificativa, hipóteses e mensagem.
- Toda mensagem da IA passa pelo verificador de linguagem; se houver problema bloqueante,
  o sistema usa o modelo padrão e registra o motivo.
Sem ANTHROPIC_API_KEY, nada aqui é chamado e o sistema funciona só com regras e modelos.
"""
from __future__ import annotations

import json
import re
from typing import Callable

from .messages import (COLD_VARIANTS, OPT_OUT_EN, OPT_OUT_HINT, VARIANTS, build_analysis, email_footer, has_blocking,
                       lead_language, lint_message, render_subject, render_template)
from .segments import get_segment

API_URL = "https://api.anthropic.com/v1/messages"

SYSTEM_PROMPT = """Você ajuda um profissional brasileiro que vende criação de sites a preparar abordagens comerciais para pequenas empresas locais.

Regras obrigatórias:
1. Use SOMENTE os fatos fornecidos em "fatos_verificados". Não invente números, nomes, serviços, problemas ou opiniões de clientes.
2. Nunca afirme que a empresa perde clientes, vendas ou dinheiro. Não prometa resultados. Não use pressão, urgência, exageros ou linguagem publicitária.
3. Se a empresa tem site próprio, não diga que ela não tem site e não diga que o site é ruim; cite só os pontos verificados.
4. Hipóteses devem ser escritas como possibilidades ("pode", "poderia"), nunca como fatos.
5. Mensagem no idioma pedido, tom cordial e natural, sem emojis, sem colchetes ou campos a preencher.
6. Comece falando da empresa (o que você viu nela), não do vendedor: a primeira linha é o que aparece na notificação.
7. Termine com UMA pergunta de interesse, fácil de responder com "sim" (ex.: "Posso te mandar uma ideia de como ficaria?"), em vez de pedir reunião.
8. Ofereça algo concreto e gratuito (uma ideia ou prévia do site). Não inclua links na primeira mensagem.
9. Tamanho: WhatsApp, Instagram ou formulário até 350 caracteres; e-mail com 50 a 125 palavras (sem assinatura).
Responda apenas com um objeto JSON válido, sem texto antes ou depois."""

USER_TEMPLATE = """Dados da empresa (verificados pelo sistema):
{facts}

Segmento: {segment} (um site para esse segmento costuma apresentar: {site_items})
Situação da abordagem: {variant_label}
Vendedor: {seller}
{preview}
Mensagem de referência (já funcionou, NÃO copie literalmente, use como inspiração de tom):
"{reference}"

Idioma da mensagem: {language}
Canal: {channel}
Mensagem base gerada pelo sistema (melhore a naturalidade mantendo os fatos e o tamanho):
"{base}"

Retorne JSON com as chaves:
- "resumo": 1 a 2 frases objetivas, em português, sobre a empresa e a presença digital.
- "justificativa": 2 a 3 frases, em português, explicando a oportunidade comercial sem afirmar perdas.
- "hipoteses": lista de 1 a 3 hipóteses em português (escritas como possibilidades).
- "mensagem": a mensagem para a empresa, no idioma indicado. Em e-mail, só o corpo (sem assinatura).
- "assunto": só para e-mail, de 3 a 6 palavras."""


class AIError(Exception):
    pass


def _default_post(url: str, headers: dict, payload: dict, timeout: int) -> dict:
    import requests

    r = requests.post(url, headers=headers, json=payload, timeout=timeout)
    if r.status_code >= 400:
        try:
            msg = r.json().get("error", {}).get("message", r.text[:200])
        except ValueError:
            msg = r.text[:200]
        raise AIError(f"API do Claude respondeu {r.status_code}: {msg}")
    return r.json()


class ClaudeWriter:
    def __init__(self, api_key: str, model: str, post: Callable[..., dict] | None = None, timeout: int = 60):
        self.api_key = api_key
        self.model = model
        self.post = post or _default_post
        self.timeout = timeout

    def _call(self, system: str, user: str) -> str:
        headers = {"x-api-key": self.api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
        payload = {"model": self.model, "max_tokens": 1200, "system": system, "messages": [{"role": "user", "content": user}]}
        data = self.post(API_URL, headers, payload, self.timeout)
        parts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
        if not parts:
            raise AIError("Resposta da IA sem texto")
        return "".join(parts)

    @staticmethod
    def _parse_json(text: str) -> dict:
        text = text.strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end < 0:
            raise AIError("A IA não retornou JSON")
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError as e:
            raise AIError(f"JSON inválido da IA: {e}") from e

    def write(self, lead: dict, variant: str, seller: dict, reference_message: str, channel: str = "whatsapp",
              base_message: str = "") -> dict:
        base = build_analysis(lead)
        seg = get_segment(lead.get("segment"))
        facts = "\n".join(f"- {f['texto']} (fonte: {f['fonte']})" for f in base["fatos_verificados"]) or "- (sem dados)"
        preview = ""
        if lead.get("preview_ready"):
            preview = "O vendedor JÁ preparou uma prévia do site para esta empresa" + (f": {lead['preview_url']}" if lead.get("preview_url") else "") + ". Mencione isso."
        else:
            preview = "O vendedor NÃO preparou prévia: não diga que já fez um site para a empresa."
        lang = lead_language(lead)
        exp = seller.get("experiencia_en", "") if lang == "en" else seller.get("experiencia", "")
        seller_txt = f"{seller.get('primeiro_nome') or seller.get('nome')}, trabalha com desenvolvimento de sites ({exp})".strip()
        if seller.get("empresa"):
            seller_txt += f", empresa {seller['empresa']}"
        user = USER_TEMPLATE.format(
            facts=f"Empresa: {lead.get('name')}\n{facts}", segment=seg.label, site_items=seg.site_items,
            variant_label=VARIANTS.get(variant, variant), seller=seller_txt, preview=preview, reference=reference_message,
            language="inglês (natural para pequenas empresas dos EUA; não traduza literalmente do português)" if lang == "en" else "português do Brasil",
            channel={"email": "e-mail", "instagram": "Direct do Instagram", "facebook": "Messenger da página do Facebook",
                     "formulario": "formulário de contato do site"}.get(channel, "WhatsApp"),
            base=base_message.split("\n\n" + seller.get("nome", "\0"))[0] if base_message else "",
        )
        out = self._parse_json(self._call(SYSTEM_PROMPT, user))
        for key in ("resumo", "justificativa", "mensagem"):
            if not isinstance(out.get(key), str) or not out[key].strip():
                raise AIError(f"Resposta da IA sem o campo '{key}'")
        hyps = out.get("hipoteses") or []
        if not isinstance(hyps, list):
            hyps = [str(hyps)]
        return {"resumo": out["resumo"].strip(), "justificativa": out["justificativa"].strip(),
                "hipoteses": [str(h).strip() for h in hyps][:3], "mensagem": out["mensagem"].strip(),
                "assunto": str(out.get("assunto") or "").strip()[:80]}


REFERENCE_MESSAGE = (
    "Olá, tudo bem? Meu nome é Eduardo e trabalho com desenvolvimento de sites para empresas. Conheci a "
    "empresa pelo Google e percebi que não encontrei um site próprio vinculado ao negócio. Tenho algumas ideias "
    "de como uma página profissional poderia ajudar a apresentar melhor os serviços e facilitar o contato com os "
    "clientes. Você seria a pessoa responsável por essa parte? Se fizer sentido, gostaria de apresentar uma "
    "proposta sem compromisso."
)


def generate(lead: dict, variant: str, seller: dict, tz: str, writer: ClaudeWriter | None, use_ai: bool,
             channel: str = "whatsapp") -> dict:
    """Gera análise + mensagem. Retorna dict com analysis, message, subject, generated_by e warnings."""
    analysis = build_analysis(lead)
    template_msg = render_template(lead, variant, seller, tz, channel=channel)
    subject = render_subject(lead, variant) if channel == "email" else None
    result = {"analysis": analysis, "message": template_msg, "subject": subject, "generated_by": "modelo",
              "warnings": lint_message(template_msg, lead, channel, variant)}
    if not (use_ai and writer):
        return result
    # Respostas curtas e roteiros de ligação: o modelo basta.
    if variant in ("outro_horario", "opt_out", "roteiro_ligacao"):
        return result
    try:
        ai = writer.write(lead, variant, seller, REFERENCE_MESSAGE, channel, template_msg)
    except Exception as e:
        result["warnings"] = result["warnings"] + [{"nivel": "aviso", "motivo": f"IA indisponível, usado o modelo padrão ({e})"}]
        return result
    analysis_ai = dict(analysis)
    analysis_ai.update({"resumo": ai["resumo"], "justificativa": ai["justificativa"], "hipoteses_ia": ai["hipoteses"]})
    message = ai["mensagem"]
    if channel == "email":
        message = f"{message}\n\n{email_footer(lead, seller, variant)}"
    elif lead_language(lead) == "en" and variant in COLD_VARIANTS and not OPT_OUT_HINT.search(message):
        message += OPT_OUT_EN
    warnings = lint_message(message, lead, channel, variant)
    if has_blocking(warnings):
        motivos = "; ".join(w["motivo"] for w in warnings if w["nivel"] == "bloqueante")
        return {"analysis": analysis_ai, "message": template_msg, "subject": subject, "generated_by": "modelo",
                "warnings": result["warnings"] + [{"nivel": "aviso", "motivo": f"Texto da IA descartado ({motivos}); usado o modelo padrão"}]}
    return {"analysis": analysis_ai, "message": message, "subject": (ai.get("assunto") or subject) if channel == "email" else None,
            "generated_by": "ia", "warnings": warnings}
