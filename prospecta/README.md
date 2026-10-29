# Prospecta

Ferramenta de prospecção para quem vende criação de sites. Ela encontra empresas locais pela
**API oficial do Google Places**, no **Brasil, nos EUA, no Canadá, no Reino Unido e na Austrália**, verifica a presença digital de cada uma, dá uma **pontuação
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
| Coleta | Pesquisa fora do Brasil: EUA, Canadá, Reino Unido e Austrália (idioma, formato de endereço e telefone de cada país) | Implementado. Testado com respostas simuladas |
| Coleta | Filtros: presença digital, nota mínima, avaliações, telefone, só celular | Implementado |
| Coleta | Importação de planilha CSV (português ou formato do google-maps-scraper-kit) | Implementado e testado |
| Coleta | Deduplicação por `place_id`, telefone ou nome+cidade | Implementado e testado |
| Qualificação | Classificação do link do perfil: sem site, rede social, Linktree, iFood/Booksy, site gratuito do Google descontinuado, site próprio | Implementado |
| Qualificação | Visita à página inicial do site próprio (HTTPS, adaptação ao celular, botão de WhatsApp, ano do rodapé, Flash, página em construção…) com robots.txt e proteção SSRF | Implementado |
| Qualificação | Pontuação 0–100 com pesos editáveis e cada critério marcado como "verificado" ou "hipótese" | Implementado |
| Contatos | WhatsApp (links `wa.me`), Instagram e, no Brasil, e-mail publicados pela empresa no site, na página de contato ou no Linktree. Sites que pedem para não receber ofertas são respeitados | Implementado e testado com páginas simuladas |
| Contatos | Canal recomendado por empresa (WhatsApp verificado, Instagram, Facebook, ligação, e-mail, formulário), com liberdade para escolher qualquer canal e adicionar o contato que falta, e botão "Não tem WhatsApp" | Implementado e testado |
| Abordagem | Mensagens por canal: curta para WhatsApp/Instagram, e-mail com assunto, assinatura e descadastro, roteiro de ligação para pedir permissão. Sequência com no máximo 2 retornos | Implementado |
| Abordagem | 13 variações em português e em inglês (sem site, só redes, site com problemas, abertura curta, ligação, retorno com proposta, encerramento, respostas, opt-out…) | Implementado |
| Abordagem | Verificador de linguagem (bloqueia "vocês estão perdendo clientes", promessas, pressão, nota inventada, "não tem site" para quem tem) | Implementado |
| Abordagem | Redação opcional com IA (API do Claude), com volta automática ao modelo se a IA errar | Implementado. Testado com respostas simuladas |
| CRM | 10 etapas comerciais, histórico, tarefas, anotações, próxima ação recomendada | Implementado |
| CRM | Exportação CSV (Excel/Google Sheets) | Implementado |
| Contato | Abrir no WhatsApp (`wa.me`), copiar e abrir o Instagram, abrir no e-mail (`mailto:`), copiar e abrir o site, ligar; registro do canal e da abordagem usados | Implementado |
| Resultados | Taxa de resposta por canal, abordagem, segmento e presença digital, e em qual tentativa responderam | Implementado e testado |
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

## Pesquisa com seletores

A pesquisa é montada só com escolhas, sem digitar: **segmento** (95 tipos de negócio em 10 grupos),
**país**, **estado** e **cidade**. A lista de cidades depende do estado escolhido:

- Brasil: os 5.571 municípios do IBGE, com a capital no topo.
- EUA, Canadá, Reino Unido e Austrália: cidades com mais de 15 mil habitantes (GeoNames).

Se o que você procura não estiver na lista, use "Digitar outro segmento…" ou "Outra cidade (digitar)…".
O segmento escolhido também define os benefícios citados nas mensagens e o peso do segmento na pontuação.
Fora do Brasil, o segmento aparece em português com o termo em inglês entre parênteses, que é o que vai para o Google.

As listas ficam em `static/geo/` e funcionam sem internet. Para atualizá-las, veja `scripts/build_geo.py`.
Créditos: municípios do IBGE via [kelvins/municipios-brasileiros](https://github.com/kelvins/municipios-brasileiros) (MIT);
cidades do [GeoNames](https://www.geonames.org/) via [datasets/world-cities](https://github.com/datasets/world-cities) (CC BY 4.0).

## Pesquisar fora do Brasil (EUA e outros)

No topo da tela *Leads*, escolha o país ao lado do estado: **Brasil, Estados Unidos, Canadá, Reino Unido ou Austrália**.

| O que muda | Como funciona |
|---|---|
| Pesquisa | Escolha o segmento na lista: o termo em inglês (*dentists*, *roofers*, *hair salons*) vai para o Google. A consulta vira "dentists in Austin, TX" e o Google responde em inglês, com resultados do país escolhido. Empresas de outros países são descartadas |
| Endereço | Cidade, estado e bairro no formato do país (nos EUA, a cidade, não o condado) |
| Telefone | Número internacional (+1, +44, +61). Nos EUA e no Canadá não dá para saber pelo número se é celular, então o filtro "Só celulares" some para esses países |
| Fuso horário | O sistema usa o fuso informado pelo Google e mostra a hora local da empresa ("agora são 14:20 lá"), avisando fora do horário comercial |
| Mensagens | Saem em inglês natural (o idioma pode ser trocado em cada empresa). As mensagens frias terminam com uma frase de descadastro |
| Primeiro contato nos EUA/Canadá | O sistema sugere um **roteiro de ligação** em inglês, não WhatsApp: lá o WhatsApp é pouco usado e mensagens de texto de marketing para celular podem exigir consentimento prévio. Também há mensagem escrita para usar no formulário do site da empresa |
| Registro | "Registrar contato feito" com o canal (ligação, formulário do site, e-mail…) |
| Filtros e exportação | Filtro "País" na lista; o CSV traz país, idioma e telefone internacional |

Antes de abordar empresas de fora, leia a seção "Fora do Brasil" em [docs/CONFORMIDADE.md](docs/CONFORMIDADE.md):
cada país tem regras próprias para ligações, e-mails e mensagens.

## Como usar no dia a dia

1. **Pesquisar:** na tela *Leads*, escolha "Procurar *Academias* em *Brasil* *Paraná* *Curitiba*", opcionalmente
   bairros (cada bairro vira uma consulta, o que ajuda a passar do limite de 60 resultados por
   consulta do Google) e filtros. O progresso aparece logo abaixo.
2. **Priorizar:** a lista vem ordenada pela pontuação. O marca-texto amarelo forte indica prioridade alta.
3. **Revisar:** abra a empresa. Veja *Por que X pontos* (cada critério com evidência), a análise
   (fatos verificados separados das hipóteses) e a mensagem. Ajuste o texto. Em *Personalizar*,
   informe o nome do responsável ou marque que já preparou uma prévia do site: a mensagem passa
   a mencionar isso (e só menciona quando você marca).
4. **Escolher o canal:** em *Abordagem*, o canal recomendado vem marcado (WhatsApp publicado pela
   empresa, Instagram, Facebook, ligação, e-mail ou formulário), mas você pode clicar em qualquer um: a
   mensagem é refeita para ele. Nos canais tracejados (sem contato), aparece um campo para digitar o
   WhatsApp, o @ do Instagram ou a página do Facebook; no e-mail, digite o endereço em "Para".
   Trocar a *situação* (ex.: "Presença digital limitada") estando em "Ligação" passa para o melhor canal escrito.
5. **Enviar:** "Abrir no WhatsApp", "Copiar e abrir o Instagram" ou "Abrir no e-mail" deixam o texto
   pronto; você revisa e envia. Se o WhatsApp disser que o número não existe, clique em **Não tem WhatsApp**.
   Depois clique em **Registrar contato feito**. O botão fica bloqueado quando a política de contato não permite.
6. **Acompanhar:** registre respostas, ligações, reuniões e propostas no *Histórico*. A etapa avança
   sozinha (ex.: resposta recebida → "Respondeu"). Crie tarefas com data. Use "Sugerir resposta"
   para gerar textos de resposta (interesse, pedido de informações, outro horário).
7. **Respeitar pedidos de parada:** "Pediu para não receber mensagens" ou "Não contatar novamente"
   coloca telefone e `place_id` na lista de supressão. Novas pesquisas e importações ignoram a empresa.
8. **Medir:** a aba *Resultados* mostra o que está trazendo resposta. Compare depois de uns 20 contatos por canal.
9. **Exportar:** "Exportar CSV" respeita os filtros atuais (separador `;`, abre direto no Excel e no Google Sheets).

Leads salvos antes desta versão: **Configurações → Atualizar contatos de todos os leads** busca
WhatsApp, Instagram e e-mail publicados (não usa a cota do Google). Por que as mensagens e os canais
são assim: [docs/ABORDAGEM.md](docs/ABORDAGEM.md).

### Importar uma planilha

Colunas aceitas (cabeçalho em português ou inglês): `nome`/`title`, `telefone`/`phone`, `site`/`website`,
`categoria`/`category`, `endereco`/`address`, `bairro`, `cidade`/`city`, `uf`/`state`, `nota`/`review_rating`,
`avaliacoes`/`review_count`, `link`, `place_id`, `pais`/`country` (BR, US, CA, GB, AU ou o nome do país).
Sem coluna de país, o sistema deduz pelo telefone (+1, +44, +61) e, na falta, assume Brasil. Também aceita
`whatsapp` e `email` (use só contatos que a própria empresa publicou ou te passou). Se a planilha não tiver
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

São 54 testes: telefones, classificação e análise de sites (incluindo bloqueio de endereços internos),
pontuação, mensagens e verificador de linguagem, política de contato, importação CSV, cliente da
Places API (paginação, máscara de campos, novas tentativas, cota), fluxo completo da API (pesquisa →
deduplicação → mensagem → envio → opt-out → supressão), permissões dos tokens, exportação,
manutenção do cache do Google, IA (com respostas simuladas), servidor MCP e pesquisa internacional
(telefones dos EUA/Reino Unido/Austrália, endereço dos EUA, consulta em inglês, mensagens em inglês,
supressão de telefone estrangeiro, importação com país e atualização de bancos da versão anterior).

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
  channels.py       canal recomendado por empresa
  insights.py       taxa de resposta por canal, abordagem e segmento
  countries.py      países suportados (idioma, formato da consulta)
  repository.py     todo o SQL
mcp_server/server.py  servidor MCP (stdio)
static/             painel web (HTML, CSS e JavaScript, sem build)
tests/              testes automatizados
docs/               abordagem, análise técnica, conformidade, mensagens e MCP
```

## Próximos passos sugeridos

1. Rodar a primeira pesquisa real com poucos resultados (ex.: 20) e conferir os dados.
2. Ajustar os pesos da pontuação e as abordagens depois das primeiras 30–50 tentativas, olhando a aba *Resultados*.
3. Sincronização com Google Sheets (conta de serviço) ou Zoho CRM (API REST), se a planilha/CRM virar o centro do trabalho.
4. Migrações de banco (Alembic) e PostgreSQL, se houver mais de um usuário.
5. Medir velocidade e uso em celular com a API PageSpeed Insights (grátis) para enriquecer o diagnóstico.
6. Avaliar a WhatsApp Business Platform **apenas** para quem já deu opt-in (ex.: follow-ups de quem respondeu).

Documentação complementar: [abordagem e canais](docs/ABORDAGEM.md), [análise técnica](docs/ANALISE_TECNICA.md), [conformidade](docs/CONFORMIDADE.md),
[guia de mensagens](docs/MENSAGENS.md) e [MCP](docs/MCP.md).
