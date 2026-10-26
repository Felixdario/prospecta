# Etapa 1: análise técnica

## 1. O repositório de referência

**Repositório:** [Mahanaicoach/google-maps-scraper-kit](https://github.com/Mahanaicoach/google-maps-scraper-kit)
(analisado em 26/10/2026, último commit "docs: guides and recipes for long-tail searches").

### Arquitetura real (verificada no código)

O kit é uma camada fina em volta de um motor de terceiros:

| Componente | O que é | Tamanho |
|---|---|---|
| Motor | Imagem Docker `gosom/google-maps-scraper:v1.18.1` (Go + Playwright), MIT, de outro autor. Abre um navegador headless no Google Maps e expõe uma API REST em `localhost:8080` **sem autenticação** | externo |
| `scripts/scrape.py` | CLI em Python só com biblioteca padrão: cria o job, faz polling, baixa o CSV, deduplica por `place_id`, geocodifica com OpenStreetMap Nominatim, divide a cidade em grade (`--grid`), extrai e-mails e redes sociais visitando os sites | 451 linhas |
| `scripts/scrape.sh` | Mesmo fluxo em shell | 84 linhas |
| `scripts/test_scrape.py` | Testes das funções puras (grade, deduplicação, regex de e-mail) | 183 linhas |
| `.claude/skills` e `.claude/commands` | Instruções para o Claude Code operar o motor | documentação |
| `docker-compose.yml` | Sobe o motor ligado só em 127.0.0.1 | — |

### O que funciona e o que não funciona

- Retorna até ~120 resultados por busca (limite do próprio Google Maps); `--grid` contorna com várias buscas.
- O motor é frágil: o histórico mostra que a versão v1.15.0 parou de funcionar porque o driver do
  Playwright foi removido do CDN da Microsoft, e o kit precisou fixar a v1.18.1 (commit `7c18757`).
- O próprio README declara: *"It is against Google's Terms of Service"* e alerta para bloqueio de IP
  ("temporarily rate-limited") em uso intenso, recomendando proxies rotativos.
- Coleta e-mails visitando os sites (e-mail é dado pessoal pela LGPD) e roda sem autenticação.

### O que foi reaproveitado (ideias, não código)

| Do kit | No Prospecta |
|---|---|
| Deduplicação por `place_id` com alternativas | `Repo._find_existing`: `place_id` → telefone → nome+cidade |
| Extração de redes sociais do próprio site da empresa | `site_analysis._social_from_links` (só links publicados no site da empresa) |
| Formato do CSV (title, phone, website, review_rating…) | Aceito na importação de planilhas |
| Busca por bairros/grade para passar do limite por consulta | Campo "Bairros": uma consulta por bairro |
| Skill com regras para o agente | Servidor MCP com permissões reais (token + escopos), não só instruções |

### O que não foi reaproveitado, e por quê

- **O motor de raspagem.** Viola os termos do Google, depende de um navegador automatizado que quebra
  com atualizações, exige Docker e proxies para volume, e não tem autenticação. O pedido original pede
  para preferir APIs oficiais e não ignorar restrições das fontes.
- **A coleta de e-mails.** Desnecessária para o fluxo por WhatsApp e aumenta o risco em LGPD (minimização).

## 2. Fontes de dados avaliadas

| Opção | Legalidade/termos | Estabilidade | Custo | Decisão |
|---|---|---|---|---|
| **Google Places API (New)** | Oficial, com regras de cache e atribuição | Alta | 1.000 chamadas/mês grátis por SKU, depois ~US$ 35/1.000 (Text Search Enterprise) | **Fonte principal** |
| Raspagem (gosom / kit) | Contra os termos do Google | Baixa (quebras, bloqueios de IP) | Grátis + proxies | Não adotado. CSV pode ser importado por conta e risco do usuário |
| Serviços de raspagem (Apify, Outscraper) | Transferem o risco de termos para o fornecedor, mas os dados continuam vindo de raspagem | Média | Por resultado | Não adotado. CSV desses serviços é importável |
| OpenStreetMap (Overpass) | Aberto (ODbL) | Alta | Grátis | Cobertura de telefone/site de pequenos negócios no Brasil é baixa. Possível fonte futura |

## 3. Serviços externos e credenciais

| Serviço | Credencial | Obrigatório? |
|---|---|---|
| Google Places API (New) | `GOOGLE_PLACES_API_KEY` (projeto no Google Cloud com faturamento) | Só para pesquisar. Sem ela, o sistema funciona com importação de planilhas |
| API do Claude (Anthropic) | `ANTHROPIC_API_KEY` | Não. Sem ela, análises e mensagens usam regras e modelos |
| WhatsApp | Nenhuma (link `wa.me`, envio manual) | — |
| Claude Desktop (MCP) | Token gerado pelo próprio sistema | Não |

## 4. Arquitetura escolhida

```
                ┌──────────── Painel web (HTML/CSS/JS, sem build) ────────────┐
                │                                                              │
Claude Desktop ─┤ MCP (stdio) ──► API REST (Starlette) ──► Serviços ──► SQLite (WAL)
                │                      │  token + escopos      │
                │                      │  validação Pydantic   ├─► Google Places API (New)
                │                      │  auditoria            ├─► página inicial dos sites
                │                      ▼                       └─► API do Claude (opcional)
                │                Fila no banco ◄── worker em segundo plano (1 trabalho por vez)
```

| Decisão | Motivo |
|---|---|
| **Python** | Melhor ecossistema para dados, scraping ético de uma página, IA e MCP; o usuário não precisa de Node |
| **Starlette + Uvicorn** | É a base do FastAPI, com menos dependências. Validação com Pydantic |
| **SQLite (WAL)** | Zero configuração, um arquivo para backup, aguenta dezenas de milhares de leads de um usuário. Todo o SQL fica em `repository.py` para facilitar a troca por PostgreSQL |
| **Fila no próprio banco + 1 worker** | Pesquisas longas não travam a tela; um trabalho por vez evita rajadas na API; sobrevive a reinícios (marca como "interrompida"). Redis/RQ só se houver vários usuários |
| **Pontuação por regras, IA só para redação** | A nota precisa ser explicável e reproduzível; a IA escreve, mas não decide nem inventa fatos |
| **Painel sem build** | Roda abrindo o navegador; nada de Node/Webpack para manter |
| **MCP chamando a API REST** | A IA herda autenticação, escopos, validação, limites e auditoria da API; nunca acessa o banco direto |

## 5. Limitações conhecidas

- **Não testado contra as APIs reais.** O ambiente de desenvolvimento não tinha acesso ao Google nem à
  Anthropic; os testes usam respostas simuladas no formato documentado. Faça a primeira pesquisa com
  poucos resultados.
- **Máximo de 60 resultados por consulta** na Places API (3 páginas de 20). Use bairros para cobrir uma cidade.
- **WhatsApp não verificado.** Celular sugere WhatsApp, mas não há como confirmar sem enviar mensagem.
- **Diagnóstico de site é heurístico.** Sites montados por JavaScript podem gerar falso "pouco texto"
  (marcado como hipótese). Não mede velocidade real em celular (sugestão: PageSpeed Insights).
- **Cache do Google.** Pelas regras do Google, o conteúdo (exceto `place_id`) não pode ser guardado
  indefinidamente: o sistema atualiza ou limpa após o prazo configurado.
- **Um usuário.** Não há cadastro de vários vendedores; há um administrador e tokens de integração.
