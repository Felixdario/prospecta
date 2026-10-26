# Prospecta

Ferramenta de prospecção para quem vende criação de sites. Ela encontra empresas locais pela
**API oficial do Google Places**, verifica a presença digital de cada uma, dá uma **pontuação
explicável de 0 a 100**, escreve uma **mensagem personalizada para revisão** e organiza o
acompanhamento comercial (status, histórico, tarefas e lista de "não contatar").

O envio é sempre feito por você: o sistema abre o WhatsApp com o texto pronto e registra o
resultado. Não há disparo automático nem envio em massa.

```
Pesquisa (Google Places) → filtros → diagnóstico do site → pontuação → mensagem → revisão humana
→ você envia pelo WhatsApp → registro do resultado → follow-up / tarefa / encerramento
```

## O que já funciona

| Área | Funcionalidade | Situação |
|---|---|---|
| Coleta | Pesquisa por segmento, cidade, UF e bairros (uma consulta por bairro) | Implementado. Testado com respostas simuladas da API |
| Coleta | Filtros: presença digital, nota mínima, avaliações, telefone, só celular | Implementado |
| Coleta | Importação de planilha CSV (português ou formato do google-maps-scraper-kit) | Implementado e testado |
| Coleta | Deduplicação por `place_id`, telefone ou nome+cidade | Implementado e testado |
| Qualificação | Classificação do link do perfil: sem site, rede social, Linktree, iFood/Booksy, site gratuito do Google descontinuado, site próprio | Implementado |
| Qualificação | Visita à página inicial do site próprio (HTTPS, adaptação ao celular, botão de WhatsApp, ano do rodapé, Flash, página em construção…) com robots.txt e proteção SSRF | Implementado |
| Qualificação | Pontuação 0–100 com pesos editáveis e cada critério marcado como "verificado" ou "hipótese" | Implementado |
| Abordagem | 10 variações de mensagem (sem site, só redes, site com problemas, follow-up, resposta com interesse, opt-out…) | Implementado |
| Abordagem | Verificador de linguagem (bloqueia "vocês estão perdendo clientes", promessas, pressão, nota inventada, "não tem site" para quem tem) | Implementado |
| Abordagem | Redação opcional com IA (API do Claude), com volta automática ao modelo se a IA errar | Implementado. Testado com respostas simuladas |
| CRM | 10 etapas comerciais, histórico, tarefas, anotações, próxima ação recomendada | Implementado |
| CRM | Exportação CSV (Excel/Google Sheets) | Implementado |
| Contato | Link `wa.me` com texto pronto + registro do envio | Implementado |
| Contato | Limite diário, intervalo mínimo, máximo de tentativas sem resposta, lista de supressão, opt-out, consentimento | Implementado e testado |
| IA | Servidor MCP com 13 ferramentas, token com permissões e auditoria | Implementado e testado via stdio |
| Conformidade | Cache do conteúdo do Google com prazo (30 dias) e rotina de atualização/limpeza | Implementado |
| Não implementado | Sincronização direta com Google Sheets/Zoho CRM, envio pela API oficial do WhatsApp, fila distribuída (Redis), PostgreSQL | Veja "Próximos passos" |

> **Importante:** nada aqui foi executado contra a API real do Google nem contra a API real do
> Claude: o ambiente onde o código foi escrito não tinha acesso a esses serviços. Todos os
> fluxos foram testados com respostas simuladas no formato documentado das APIs. A primeira
> pesquisa real vai acontecer na sua máquina, com a sua chave.

## Instalação

Requisitos: **Python 3.11 ou mais novo** (Windows, macOS ou Linux).

```bash
# 1. Entre na pasta do projeto
cd prospecta

# 2. Crie um ambiente virtual e instale as dependências
python -m venv .venv
# Windows:            .venv\Scripts\activate
# macOS / Linux:      source .venv/bin/activate
pip install -r requirements.txt

# 3. Crie o arquivo .env com um token de administrador e o banco de dados
python -m app.cli init

# 4. (Opcional) Coloque empresas FICTÍCIAS para conhecer o painel sem chave do Google
python -m app.cli seed-demo

# 5. Inicie o servidor
python -m app
```

Abra **http://127.0.0.1:8000** e entre com o `ADMIN_TOKEN` que o passo 3 mostrou (ele também
fica no arquivo `.env`).

## Configuração (.env)

| Variável | Obrigatória | Para que serve |
|---|---|---|
| `ADMIN_TOKEN` | Sim | Acesso ao painel. Gerado pelo `init` |
| `GOOGLE_PLACES_API_KEY` | Para pesquisar | Chave da Places API (New) |
| `GOOGLE_TEXTSEARCH_MONTHLY_LIMIT` | Não (900) | Teto de pesquisas por mês. O sistema para antes de passar daí |
| `GOOGLE_DETAILS_MONTHLY_LIMIT` | Não (900) | Teto de atualizações de leads por mês |
| `GOOGLE_CACHE_DAYS` | Não (30) | Prazo para atualizar ou remover dados do Google |
| `ANTHROPIC_API_KEY` | Não | Ativa a redação com IA |
| `AI_MODEL` | Não | Padrão `claude-haiku-5-5` |
| `HOST` / `PORT` | Não | Padrão `127.0.0.1:8000` (só o seu computador) |
| `SITE_ANALYSIS_USER_AGENT` | Não | Identificação usada ao visitar sites |

### Como obter a chave do Google (5 minutos)

1. Acesse o [Google Cloud Console](https://console.cloud.google.com/) e crie um projeto.
2. Em **Faturamento**, vincule uma forma de pagamento. Isso é exigido mesmo para usar só a cota grátis.
3. Em **APIs e serviços → Biblioteca**, ative a **Places API (New)**.
4. Em **Credenciais**, crie uma **chave de API** e restrinja-a à Places API (New).
5. Cole a chave em `GOOGLE_PLACES_API_KEY` no `.env` e reinicie o servidor.

Recomendo também criar um **alerta de orçamento** no Cloud Console (por exemplo, US$ 5) como segunda proteção.

## O que é grátis e o que é pago

| Serviço | Custo |
|---|---|
| Prospecta (este código), SQLite, painel, MCP | Grátis |
| Google Places, pesquisa (Text Search Enterprise) | **1.000 chamadas grátis por mês**, depois ~US$ 35 por 1.000. Cada chamada traz até 20 empresas, então dá ~20 mil empresas/mês sem custo. O sistema para em 900 por padrão |
| Google Places, atualização de lead (Place Details Enterprise) | 1.000 grátis por mês, depois ~US$ 20 por 1.000 |
| Análise dos sites | Grátis (o próprio sistema visita a página inicial) |
| IA (opcional, Claude Haiku 5.5) | Cerca de US$ 0,10 por milhão de tokens de entrada e US$ 0,50 de saída: frações de centavo por lead |
| WhatsApp (link `wa.me`, envio manual) | Grátis |
| WhatsApp Business Platform (API oficial) | Pago por conversa e **exige opt-in prévio**. Não implementado (veja docs/CONFORMIDADE.md) |

Preços conferidos em outubro de 2026. Confirme nas páginas oficiais antes de usar em volume.

## Como usar no dia a dia

1. **Pesquisar:** na tela *Leads*, preencha "Procurar *academias* em *Curitiba* *PR*", opcionalmente
   bairros (cada bairro vira uma consulta, o que ajuda a passar do limite de 60 resultados por
   consulta do Google) e filtros. O progresso aparece logo abaixo.
2. **Priorizar:** a lista vem ordenada pela pontuação. O marca-texto amarelo forte indica prioridade alta.
3. **Revisar:** abra a empresa. Veja *Por que X pontos* (cada critério com evidência), a análise
   (fatos verificados separados das hipóteses) e a mensagem. Ajuste o texto. Em *Personalizar*,
   informe o nome do responsável ou marque que já preparou uma prévia do site: a mensagem passa
   a mencionar isso (e só menciona quando você marca).
4. **Enviar:** "Abrir no WhatsApp" abre a conversa com o texto preenchido. Você revisa e envia.
   Depois clique em **Registrar envio**. O botão fica bloqueado quando a política de contato não permite.
5. **Acompanhar:** registre respostas, ligações, reuniões e propostas no *Histórico*. A etapa avança
   sozinha (ex.: resposta recebida → "Respondeu"). Crie tarefas com data. Use "Sugerir resposta"
   para gerar textos de resposta (interesse, pedido de informações, outro horário).
6. **Respeitar pedidos de parada:** "Pediu para não receber mensagens" ou "Não contatar novamente"
   coloca telefone e `place_id` na lista de supressão. Novas pesquisas e importações ignoram a empresa.
7. **Exportar:** "Exportar CSV" respeita os filtros atuais (separador `;`, abre direto no Excel e no Google Sheets).

### Importar uma planilha

Colunas aceitas (cabeçalho em português ou inglês): `nome`/`title`, `telefone`/`phone`, `site`/`website`,
`categoria`/`category`, `endereco`/`address`, `bairro`, `cidade`/`city`, `uf`/`state`, `nota`/`review_rating`,
`avaliacoes`/`review_count`, `link`, `place_id`. E-mails são ignorados de propósito. Se a planilha não tiver
coluna de site, a presença digital fica como "não verificada" e o sistema não afirma que a empresa não tem site.

## Integração com o Claude (MCP)

```bash
python -m app.cli create-token --name claude --scopes leads:read,leads:write,search:run,export
```

Depois configure o Claude Desktop conforme [docs/MCP.md](docs/MCP.md). O Claude passa a conseguir
pesquisar, analisar, pontuar, redigir rascunhos, atualizar etapas e criar tarefas. Ele **não**
consegue registrar envios, excluir dados, remover alguém da lista de "não contatar" nem tirar uma
empresa do status "Não contatar novamente".

## Comandos de administração

```bash
python -m app.cli init                          # cria .env e banco
python -m app.cli create-token --name X --scopes ...   # token para integrações
python -m app.cli list-tokens | revoke-token --name X
python -m app.cli import-csv planilha.csv       # importa e analisa
python -m app.cli google-cache report           # quantos leads têm dados do Google vencidos
python -m app.cli google-cache refresh          # atualiza os ativos e limpa o resto
python -m app.cli run-jobs                      # processa a fila sem subir o painel
```

Escopos disponíveis: `admin`, `leads:read`, `leads:write`, `search:run` (gasta cota do Google),
`export`, `contacts:record` (registrar envio de mensagem).

## Testes

```bash
pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

São 39 testes: telefones, classificação e análise de sites (incluindo bloqueio de endereços internos),
pontuação, mensagens e verificador de linguagem, política de contato, importação CSV, cliente da
Places API (paginação, máscara de campos, novas tentativas, cota), fluxo completo da API (pesquisa →
deduplicação → mensagem → envio → opt-out → supressão), permissões dos tokens, exportação,
manutenção do cache do Google, IA (com respostas simuladas) e servidor MCP.

## Implantação

O uso recomendado é **local** (`HOST=127.0.0.1`). Para acessar de outros lugares:

- Rode atrás de um proxy reverso com HTTPS (Caddy ou Nginx) e use `HOST=0.0.0.0` só dentro da rede do servidor.
- Use um `ADMIN_TOKEN` longo e guarde o `.env` fora do controle de versão.
- Faça backup do arquivo `data/prospecta.db` (é um único arquivo SQLite).
- Há um `Dockerfile` de referência (não testado neste ambiente).

Para manter os dados do Google dentro do prazo, agende `python -m app.cli google-cache refresh`
uma vez por semana (Agendador de Tarefas do Windows ou cron).

## Estrutura

```
app/
  api.py            rotas REST, autenticação, permissões, auditoria
  services.py       regras de negócio (análise, mensagens, status, contatos)
  jobs.py           fila de pesquisas em segundo plano
  sources/places.py cliente da Google Places API (New)
  sources/csv_import.py
  site_analysis.py  diagnóstico do site (com proteção SSRF e robots.txt)
  scoring.py        pontuação explicável
  messages.py       análise determinística, variações de mensagem e verificador de linguagem
  ai.py             redação opcional com a API do Claude
  pipeline.py       etapas, próxima ação e política de contato
  repository.py     todo o SQL
mcp_server/server.py  servidor MCP (stdio)
static/             painel web (HTML, CSS e JavaScript, sem build)
tests/              testes automatizados
docs/               análise técnica, conformidade, mensagens e MCP
```

## Próximos passos sugeridos

1. Rodar a primeira pesquisa real com poucos resultados (ex.: 20) e conferir os dados.
2. Ajustar os pesos da pontuação depois das primeiras 30–50 abordagens (o que gerou resposta?).
3. Sincronização com Google Sheets (conta de serviço) ou Zoho CRM (API REST), se a planilha/CRM virar o centro do trabalho.
4. Migrações de banco (Alembic) e PostgreSQL, se houver mais de um usuário.
5. Medir velocidade e uso em celular com a API PageSpeed Insights (grátis) para enriquecer o diagnóstico.
6. Avaliar a WhatsApp Business Platform **apenas** para quem já deu opt-in (ex.: follow-ups de quem respondeu).

Documentação complementar: [análise técnica](docs/ANALISE_TECNICA.md), [conformidade](docs/CONFORMIDADE.md),
[guia de mensagens](docs/MENSAGENS.md) e [MCP](docs/MCP.md).
