# Integração com o Claude (servidor MCP)

## Por que MCP

| Opção | Prós | Contras | Decisão |
|---|---|---|---|
| **Servidor MCP local (stdio)** | Padrão aberto suportado pelo Claude Desktop e pelo Claude Code; ferramentas aparecem direto na conversa; roda no seu computador | Funciona onde o app desktop roda, não no celular | **Implementado** |
| API REST + "tools" na API do Claude | Bom para automações próprias (scripts, agendamentos) | Você mantém o laço de chamadas | A API REST existe e está documentada; pode ser usada assim |
| Conector remoto (MCP via HTTPS) | Funciona no navegador e no celular | Exige servidor público com HTTPS e OAuth | Não implementado. O SDK usado suporta o transporte HTTP; falta a camada de autenticação OAuth e a hospedagem |
| Integração com CRM (Zoho) | Dados no CRM que você já usa | Não dá à IA as ferramentas de análise | Futuro, como sincronização |

O servidor MCP **não acessa o banco**. Ele chama a API REST com um token próprio, então a IA
herda as mesmas proteções do painel: escopos, validação de entrada, limite de requisições e auditoria.

## Ferramentas

| Ferramenta | O que faz | Escopo exigido |
|---|---|---|
| `search_companies` | Pesquisa no Google (gasta cota), filtra, salva, analisa e devolve os leads por pontuação. Aceita `country` (BR, US, CA, GB, AU) | `search:run` |
| `get_search_status` | Andamento de uma pesquisa | `leads:read` |
| `list_leads` | Lista com filtros (prioridade, status, presença, cidade, nota mínima) | `leads:read` |
| `get_company_details` | Dados, diagnóstico do site, pontuação explicada, fatos x hipóteses, política de contato, histórico | `leads:read` |
| `analyze_online_presence` | Refaz o diagnóstico do site e a pontuação | `leads:write` |
| `score_lead` | Recalcula a pontuação com explicação | `leads:write` |
| `generate_outreach_message` | Gera **rascunho** de mensagem (com avisos do verificador) | `leads:write` |
| `save_lead` | Cadastra uma empresa manualmente | `leads:write` |
| `update_lead_status` | Muda a etapa comercial | `leads:write` |
| `log_interaction` | Registra resposta, ligação, reunião, proposta, anotação ou opt-out | `leads:write` |
| `create_follow_up_task` / `list_follow_up_tasks` | Tarefas de acompanhamento | `leads:write` / `leads:read` |
| `export_leads` | Gera um CSV na pasta `exports/` | `export` |

### O que a IA não consegue fazer (de propósito)

- Enviar mensagens (não existe ferramenta para isso).
- Registrar que uma mensagem foi enviada (exige o escopo `contacts:record`, que não deve ser dado à IA).
- Excluir leads, remover itens da lista de "não contatar", mudar configurações ou ler a auditoria (só administrador).
- Tirar uma empresa do status "Não contatar novamente".

## Configuração no Claude Desktop

1. Deixe o Prospecta rodando (`python -m app`).
2. Crie um token para a IA:
   ```bash
   python -m app.cli create-token --name claude --scopes leads:read,leads:write,search:run,export
   ```
   Para a IA só consultar, sem gastar cota do Google: `--scopes leads:read`.
3. No Claude Desktop, abra **Configurações → Desenvolvedor → Editar configuração** e adicione
   (ajuste os caminhos para a pasta do projeto):

   **Windows**
   ```json
   {
     "mcpServers": {
       "prospecta": {
         "command": "C:\\Users\\voce\\prospecta\\.venv\\Scripts\\python.exe",
         "args": ["C:\\Users\\voce\\prospecta\\mcp_server\\server.py"],
         "env": {
           "PROSPECTA_API_URL": "http://127.0.0.1:8000",
           "PROSPECTA_TOKEN": "pk_cole_o_token_aqui"
         }
       }
     }
   }
   ```

   **macOS / Linux**
   ```json
   {
     "mcpServers": {
       "prospecta": {
         "command": "/Users/voce/prospecta/.venv/bin/python",
         "args": ["/Users/voce/prospecta/mcp_server/server.py"],
         "env": {
           "PROSPECTA_API_URL": "http://127.0.0.1:8000",
           "PROSPECTA_TOKEN": "pk_cole_o_token_aqui"
         }
       }
     }
   }
   ```
4. Reinicie o Claude Desktop. As ferramentas do Prospecta aparecem na conversa.

Exemplos de pedidos:

- "Pesquise 20 academias sem site próprio no Batel e no Água Verde, em Curitiba, e me mostre as 5 melhores."
- "Abra a Academia X, explique a pontuação e escreva um rascunho de mensagem."
- "Pesquise 20 dentistas sem site em Austin, Texas (EUA) e prepare o roteiro de ligação do melhor."
- "Quais tarefas de follow-up vencem hoje?"
- "A Clínica Y respondeu pedindo orçamento: registre e crie uma tarefa para sexta."

## Revogar acesso

```bash
python -m app.cli revoke-token --name claude
```

Todas as chamadas feitas pelo token aparecem em **Configurações → Ver registro de operações**.
