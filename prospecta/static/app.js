/* Prospecta — painel web (JavaScript puro, sem etapa de build). */
"use strict";

// ------------------------------------------------------------------ utilidades
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
const app = $("#app");

function esc(v) {
  return String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function safeUrl(u) {
  try { const url = new URL(u, location.href); return ["http:", "https:"].includes(url.protocol) ? url.href : "#"; } catch { return "#"; }
}
function store(key, value) {
  try { if (value === undefined) return localStorage.getItem(key); if (value === null) localStorage.removeItem(key); else localStorage.setItem(key, value); } catch { return null; }
}
function fmtDate(iso, withTime = true) {
  if (!iso) return "";
  const d = new Date(iso.length === 10 ? iso + "T12:00:00" : iso);
  return withTime ? d.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" }) : d.toLocaleDateString("pt-BR");
}
function fmtRating(r) { return r == null ? "" : Number(r).toFixed(1).replace(".", ","); }
function todayISO() { const d = new Date(); d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); return d.toISOString().slice(0, 10); }
function addDaysISO(n) { const d = new Date(); d.setDate(d.getDate() + n); d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); return d.toISOString().slice(0, 10); }

let toastTimer;
function toast(msg, isError = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast show" + (isError ? " error" : "");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.className = "toast"), isError ? 6000 : 3000);
}

// ------------------------------------------------------------------ API
const state = { token: store("prospecta_token"), meta: null, filters: { sort: "score", page: 1 }, pollTimer: null, lastJob: null };

class ApiError extends Error {
  constructor(status, data) {
    const extra = data.bloqueios ? " " + data.bloqueios.join(" ") : data.detalhes ? " " + data.detalhes.map((d) => `${d.campo}: ${d.motivo}`).join("; ") : "";
    super((data.erro || "Erro") + extra);
    this.status = status; this.data = data;
  }
}

async function api(method, path, body, isForm = false) {
  const opts = { method, headers: { Authorization: "Bearer " + state.token } };
  if (body !== undefined) {
    if (isForm) opts.body = body;
    else { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
  }
  const res = await fetch(path, opts);
  if (res.status === 401) { logout(); throw new ApiError(401, { erro: "Sessão expirada. Entre novamente." }); }
  const type = res.headers.get("content-type") || "";
  const data = type.includes("json") ? await res.json() : await res.blob();
  if (!res.ok) throw new ApiError(res.status, data);
  return data;
}

async function run(btn, fn) {
  if (btn) btn.disabled = true;
  try { return await fn(); }
  catch (e) { toast(e.message, true); }
  finally { if (btn) btn.disabled = false; }
}

function logout() {
  state.token = null; store("prospecta_token", null);
  clearInterval(state.pollTimer);
  $("#topbar").hidden = true;
  renderLogin();
}
$("#logout").addEventListener("click", logout);

// ------------------------------------------------------------------ rótulos
const PRESENCE_SHORT = {
  sem_site: "Sem site", rede_social: "Só rede social", whatsapp: "Só WhatsApp", agregador_links: "Agregador de links",
  plataforma_terceiros: "Plataforma de terceiros", google_descontinuado: "Site do Google descontinuado", proprio: "Site próprio",
  desconhecido: "Não verificado",
};
const PHONE_KIND = { celular: "celular", fixo: "fixo", especial: "0800/especial", invalido: "inválido", indefinido: "celular ou fixo" };
const CHANNEL_NAMES = { whatsapp: "WhatsApp", instagram: "Instagram", facebook: "Messenger do Facebook", email: "e-mail", formulario: "formulário do site", ligacao: "ligação" };
const CHANNEL_LABELS = { whatsapp: "WhatsApp", telefone: "Ligação", email: "E-mail", formulario_site: "Formulário do site", instagram: "Instagram", facebook: "Facebook", presencial: "Presencial", outro: "Outro" };
const COUNTRY_EXAMPLES = {
  BR: { segment: "academias", city: "Curitiba", state: "PR", regions: "Batel, Água Verde, Centro", hint: "" },
  US: { segment: "gyms", city: "Austin", state: "TX", regions: "Downtown, South Congress", hint: "A busca no Google é feita em inglês. As mensagens saem em inglês e o primeiro contato sugerido é a ligação." },
  CA: { segment: "dentists", city: "Toronto", state: "ON", regions: "Downtown, North York", hint: "A busca é feita em inglês. No Canadá, mensagens comerciais eletrônicas seguem a lei CASL: prefira ligar." },
  GB: { segment: "plumbers", city: "Manchester", state: "", regions: "Didsbury, Chorlton", hint: "A busca é feita em inglês." },
  AU: { segment: "cafes", city: "Sydney", state: "NSW", regions: "Surry Hills, Newtown", hint: "A busca é feita em inglês." },
};
const countryName = (code) => ((state.meta && state.meta.countries.find((c) => c.code === code)) || { name: code }).name;
const prioLabel = (p) => ({ alta: "Prioridade alta", media: "Prioridade média", baixa: "Prioridade baixa" }[p] || "Sem pontuação");
const statusOptions = (current) => Object.entries(state.meta.statuses).map(([k, v]) => `<option value="${k}" ${k === current ? "selected" : ""}>${esc(v)}</option>`).join("");
function scoreBadge(score, priority, big = false) {
  return `<span class="score${big ? " score-big" : ""}" data-p="${esc(priority || "")}" title="${esc(prioLabel(priority))}">${score ?? "–"}</span>`;
}
function presenceTag(kind) {
  if (!kind) return `<span class="tag tag-none">A analisar</span>`;
  return `<span class="tag${kind === "proprio" ? "" : " tag-none"}">${esc(PRESENCE_SHORT[kind] || kind)}</span>`;
}
const basisTag = (b) => `<span class="basis basis-${b === "hipotese" ? "hipotese" : "verificado"}">${b === "hipotese" ? "hipótese" : "verificado"}</span>`;

// ------------------------------------------------------------------ roteamento
const routes = [
  [/^#?\/?$/, "leads", renderLeads],
  [/^#\/lead\/(\d+)$/, "leads", (m) => renderLead(+m[1])],
  [/^#\/tarefas$/, "tarefas", renderTasks],
  [/^#\/resultados$/, "resultados", renderResults],
  [/^#\/pesquisas$/, "pesquisas", renderJobs],
  [/^#\/supressao$/, "supressao", renderSuppression],
  [/^#\/config$/, "config", renderSettings],
  [/^#\/auditoria$/, "config", renderAudit],
];

async function router() {
  if (!state.token) return renderLogin();
  if (!state.meta) {
    try { state.meta = await api("GET", "/api/meta"); } catch (e) { if (e.status !== 401) toast(e.message, true); return; }
  }
  $("#topbar").hidden = false;
  const hash = location.hash || "#/";
  for (const [re, tab, fn] of routes) {
    const m = hash.match(re);
    if (m) {
      $$(".tabs a").forEach((a) => { if (a.dataset.tab === tab) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current"); });
      try { await fn(m); } catch (e) { app.innerHTML = `<div class="empty"><h2>Não foi possível carregar</h2><p>${esc(e.message)}</p><a class="btn" href="#/">Voltar para a lista</a></div>`; }
      return;
    }
  }
  location.hash = "#/";
}
window.addEventListener("hashchange", () => { window.scrollTo(0, 0); router(); });

// ------------------------------------------------------------------ login
function renderLogin() {
  $("#topbar").hidden = true;
  app.innerHTML = `
    <section class="login">
      <h1><span>Prospecta</span></h1>
      <p class="muted">Empresas locais com potencial para um site, analisadas e organizadas do primeiro contato ao fechamento.</p>
      <form id="login-form" class="stack">
        <div><label for="tok">Token de acesso</label>
        <input id="tok" type="password" autocomplete="current-password" required placeholder="adm_..."></div>
        <button class="btn-primary" type="submit">Entrar</button>
        <p class="small muted">O token de administrador está no arquivo <code>.env</code> (gerado com <code>python -m app.cli init</code>).</p>
      </form>
    </section>`;
  $("#login-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    state.token = $("#tok").value.trim();
    try {
      state.meta = await api("GET", "/api/meta");
      store("prospecta_token", state.token);
      router();
    } catch (e) { toast(e.status === 401 ? "Token inválido." : e.message, true); state.token = null; }
  });
  $("#tok").focus();
}

// ------------------------------------------------------------------ lista de leads + pesquisa
async function renderLeads() {
  const m = state.meta;
  const usage = (m.uso_google_mes || {}).text_search_enterprise || 0;
  const lastSearch = JSON.parse(store("prospecta_last_search") || "{}");
  app.innerHTML = `
    <section class="finder" aria-labelledby="finder-title">
      <h2 id="finder-title" class="muted small" style="font-weight:600;margin-bottom:8px">Nova pesquisa no Google</h2>
      <form id="finder">
        <div class="finder-sentence">
          <span>Procurar</span>
          <select class="w-seg" name="segment_pick" aria-label="Segmento"></select>
          <input class="w-custom" name="segment_custom" maxlength="80" aria-label="Outro segmento" hidden>
          <span>em</span>
          <select class="w-country" name="country" aria-label="País">${m.countries.map((c) => `<option value="${c.code}" ${c.code === (lastSearch.country || "BR") ? "selected" : ""}>${esc(c.name)}</option>`).join("")}</select>
          <select class="w-state" name="state" aria-label="Estado"></select>
          <select class="w-city" name="city" aria-label="Cidade" disabled></select>
          <input class="w-custom" name="city_custom" maxlength="80" aria-label="Outra cidade" hidden>
        </div>
        <p class="small muted" id="country-hint" style="margin:8px 0 0"></p>
        <div class="finder-options">
          <div class="wide"><label for="f-regions">Bairros ou regiões (opcional, separados por vírgula)</label>
            <input id="f-regions" type="text" name="regions" placeholder="Batel, Água Verde, Centro" value="${esc((lastSearch.regions || []).join(", "))}"></div>
          <div><label for="f-site">Presença digital</label>
            <select id="f-site" name="website">
              <option value="sem_site_proprio">Sem site próprio (inclui só redes)</option>
              <option value="sem_site">Sem nenhum site</option>
              <option value="com_site">Com site próprio</option>
              <option value="todos">Todas</option>
            </select></div>
          <div><label for="f-max">Máximo de empresas</label><input id="f-max" type="number" name="max_results" min="1" max="300" value="40"></div>
          <div><label for="f-rating">Nota mínima</label><input id="f-rating" type="number" name="min_rating" min="0" max="5" step="0.1" placeholder="ex.: 4,0"></div>
          <div><label for="f-reviews">Mínimo de avaliações</label><input id="f-reviews" type="number" name="min_reviews" min="0" placeholder="ex.: 10"></div>
        </div>
        <div class="finder-actions">
          <label class="check"><input type="checkbox" name="require_phone" checked> Só com telefone</label>
          <label class="check" id="only-mobile"><input type="checkbox" name="only_mobile"> Só celulares</label>
          <label class="check" title="${m.ia_configurada ? "" : "Configure ANTHROPIC_API_KEY no .env"}"><input type="checkbox" name="use_ai" ${m.ia_configurada ? "" : "disabled"}> Redigir mensagens com IA</label>
          <span class="spacer" style="flex:1"></span>
          <span class="quota">Google este mês: ${usage} de ${m.limites_google.text_search_enterprise} chamadas</span>
          <button class="btn-primary" type="submit" ${m.google_configurado ? "" : "disabled"}>Pesquisar no Google</button>
        </div>
        ${m.google_configurado ? "" : `<p class="banner">Para pesquisar no Google, coloque sua chave em <code>GOOGLE_PLACES_API_KEY</code> no arquivo <code>.env</code> e reinicie. Enquanto isso, você pode importar uma planilha.</p>`}
      </form>
      <div id="job"></div>
    </section>
    <div class="tally" id="tally"></div>
    <div class="toolbar">
      <input type="search" id="q" placeholder="Buscar por nome, bairro, telefone ou anotação" value="${esc(state.filters.q || "")}" aria-label="Buscar leads">
      <select id="fp" aria-label="Prioridade"><option value="">Todas as prioridades</option><option value="alta">Alta</option><option value="media">Média</option><option value="baixa">Baixa</option></select>
      <select id="fs" aria-label="Status"><option value="">Todos os status</option>${Object.entries(m.statuses).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("")}</select>
      <select id="fpr" aria-label="Presença digital"><option value="">Toda presença</option><option value="sem_site">Sem site</option><option value="limitada">Só redes ou plataformas</option><option value="com_site">Site próprio</option></select>
      <select id="fc" aria-label="País"><option value="">Todos os países</option>${m.countries.map((c) => `<option value="${c.code}">${esc(c.name)}</option>`).join("")}</select>
      <select id="fo" aria-label="Ordenar"><option value="score">Maior pontuação</option><option value="recent">Mais recentes</option><option value="reviews">Mais avaliações</option><option value="name">Nome</option></select>
      <span class="spacer"></span>
      <label class="btn" for="csv-file" tabindex="0">Importar planilha</label>
      <input id="csv-file" type="file" accept=".csv,text/csv" hidden>
      <button id="export" type="button">Exportar CSV</button>
    </div>
    <div id="search-scope"></div>
    <div class="table-wrap" id="table"></div>`;

  const f = state.filters;
  $("#fp").value = f.priority || ""; $("#fs").value = f.status || ""; $("#fpr").value = f.presence || ""; $("#fo").value = f.sort || "score"; $("#fc").value = f.country || "";
  let qTimer;
  $("#q").addEventListener("input", (e) => { clearTimeout(qTimer); qTimer = setTimeout(() => { f.q = e.target.value; f.page = 1; loadTable(); }, 300); });
  for (const [id, key] of [["fp", "priority"], ["fs", "status"], ["fpr", "presence"], ["fo", "sort"], ["fc", "country"]]) {
    $("#" + id).addEventListener("change", (e) => { f[key] = e.target.value; f.page = 1; loadTable(); });
  }
  $("#export").addEventListener("click", (e) => run(e.currentTarget, exportCsv));
  $("#csv-file").addEventListener("change", (e) => run(null, () => importCsv(e.target.files[0])));
  $("label[for=csv-file]").addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); $("#csv-file").click(); } });
  $("#finder").addEventListener("submit", startSearch);
  setupFinderSelects(lastSearch);

  loadTally(); loadTable();
  const jobs = await api("GET", "/api/searches?limit=1");
  if (jobs.items[0]) showJob(jobs.items[0]);
}

async function loadTally() {
  const s = await api("GET", "/api/stats");
  const el = $("#tally");
  if (!el) return;
  el.innerHTML = `
    <div><strong>${s.total}</strong><span>leads</span></div>
    <div><strong>${s.by_priority.alta || 0}</strong><span>prioridade alta</span></div>
    <div><strong>${s.sem_site}</strong><span>sem site</span></div>
    <div><strong>${s.by_status.aguardando_revisao || 0}</strong><span>mensagens para revisar</span></div>
    <div><strong>${s.contatos_hoje}/${s.limite_diario}</strong><span>contatos hoje</span></div>
    <div><a href="#/tarefas"><strong>${s.tarefas_hoje}</strong></a><span>tarefas para hoje</span></div>`;
}

function queryString(extra = {}) {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries({ ...state.filters, ...extra })) if (v !== "" && v != null) p.set(k, v);
  return p.toString();
}

async function loadTable() {
  const el = $("#table");
  if (!el) return;
  const data = await api("GET", "/api/leads?" + queryString({ page_size: 50 }));
  const scope = $("#search-scope");
  scope.innerHTML = state.filters.search_id ? `<p class="banner">Mostrando só a pesquisa nº ${esc(state.filters.search_id)}. <button class="link-btn" id="clear-scope" type="button">Ver todos os leads</button></p>` : "";
  if (state.filters.search_id) $("#clear-scope").addEventListener("click", () => { delete state.filters.search_id; loadTable(); });
  if (!data.items.length) {
    const filtered = ["q", "priority", "status", "presence", "search_id"].some((k) => state.filters[k]);
    el.innerHTML = `<div class="empty"><h2>${filtered ? "Nenhum lead com esses filtros" : "Nenhum lead ainda"}</h2>
      <p>${filtered ? "Ajuste ou limpe os filtros acima." : "Comece pela pesquisa acima (segmento e cidade) ou importe uma planilha com nome e telefone das empresas."}</p></div>`;
    return;
  }
  const rows = data.items.map((l) => `
    <tr data-id="${l.id}">
      <td class="c-score">${scoreBadge(l.score, l.priority)}</td>
      <td><a class="co-name" href="#/lead/${l.id}">${esc(l.name)}</a>
        <div class="co-meta">${esc([l.category, l.neighborhood, l.city, l.country && l.country !== "BR" ? countryName(l.country) : ""].filter(Boolean).join(", "))}${l.source === "demo" ? " (fictício)" : ""}</div></td>
      <td>${presenceTag(l.presence_kind)}</td>
      <td>${l.rating != null ? `${fmtRating(l.rating)} <span class="co-meta">(${l.reviews_count ?? 0})</span>` : `<span class="co-meta">sem nota</span>`}</td>
      <td>${l.phone ? `<span class="nowrap">${esc(l.phone)}</span><div class="co-meta">${esc(PHONE_KIND[l.phone_kind] || "")}</div>` : `<span class="co-meta">sem telefone</span>`}
        <div class="ch-badges">${l.has_whatsapp ? `<span class="chb" title="WhatsApp publicado pela empresa">WhatsApp</span>` : ""}${l.has_instagram ? `<span class="chb" title="Tem Instagram">Instagram</span>` : ""}${l.has_facebook ? `<span class="chb" title="Tem página no Facebook">Facebook</span>` : ""}${l.has_email ? `<span class="chb" title="E-mail cadastrado">E-mail</span>` : ""}</div></td>
      <td><select class="row-status" aria-label="Status de ${esc(l.name)}">${statusOptions(l.status)}</select></td>
      <td class="c-actions"><div class="actions">
        <button class="btn-small row-analyze" type="button">Analisar</button>
        <button class="btn-small row-msg" type="button">${l.has_message ? "Revisar mensagem" : "Gerar mensagem"}</button>
      </div></td>
    </tr>`).join("");
  const from = (data.page - 1) * data.page_size + 1;
  const to = Math.min(data.total, data.page * data.page_size);
  el.innerHTML = `
    <table>
      <thead><tr><th>Pontuação</th><th>Empresa</th><th>Presença digital</th><th>Google</th><th>Contatos</th><th>Status</th><th><span class="sr-only">Ações</span></th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
    <div class="pager"><span>Mostrando ${from}–${to} de ${data.total}. Dados de empresas: Google Maps e planilhas importadas.</span>
      <span><button class="btn-small" id="prev" ${data.page <= 1 ? "disabled" : ""}>Anterior</button>
      <button class="btn-small" id="next" ${to >= data.total ? "disabled" : ""}>Próxima</button></span></div>`;
  $("#prev").addEventListener("click", () => { state.filters.page--; loadTable(); });
  $("#next").addEventListener("click", () => { state.filters.page++; loadTable(); });
  $$("tbody tr", el).forEach((tr) => {
    const id = tr.dataset.id;
    $(".row-status", tr).addEventListener("change", (e) => run(e.target, async () => {
      await api("POST", `/api/leads/${id}/status`, { status: e.target.value });
      toast("Status atualizado."); loadTally();
    }));
    $(".row-analyze", tr).addEventListener("click", (e) => run(e.currentTarget, async () => {
      const d = await api("POST", `/api/leads/${id}/analyze`, {});
      toast(`Pontuação ${d.lead.score} (${d.lead.priority}).`); loadTable(); loadTally();
    }));
    $(".row-msg", tr).addEventListener("click", (e) => run(e.currentTarget, async () => {
      const hasMsg = e.currentTarget.textContent.includes("Revisar");
      if (!hasMsg) await api("POST", `/api/leads/${id}/message`, {});
      location.hash = `#/lead/${id}`;
    }));
  });
}

async function exportCsv() {
  const blob = await api("GET", "/api/export.csv?" + queryString({ page: "" }));
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `leads-${todayISO()}.csv`;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  toast("Exportação pronta (abre no Excel ou no Google Sheets).");
}

async function importCsv(file) {
  if (!file) return;
  const fd = new FormData();
  fd.append("file", file);
  const r = await api("POST", "/api/import", fd, true);
  $("#csv-file").value = "";
  toast(`Planilha: ${r.novos} novos, ${r.atualizados} atualizados, ${r.suprimidos} ignorados (não contatar).${r.erros.length ? " " + r.erros.length + " linha(s) com problema." : ""}`);
  if (r.analysis_job_id) pollJob(r.analysis_job_id);
  loadTable(); loadTally();
}

// ------------------------------------------------------------------ seletores de segmento e localidade
const geoCache = {};
let SEGMENT_INDEX = {};
function loadGeo(code) {
  if (!geoCache[code]) geoCache[code] = fetch(`/geo/${code}.json`).then((r) => { if (!r.ok) throw new Error("Lista de cidades indisponível"); return r.json(); });
  return geoCache[code];
}

function setupFinderSelects(last) {
  const m = state.meta;
  SEGMENT_INDEX = {};
  for (const g of m.segment_catalog) for (const it of g.items) SEGMENT_INDEX[it.id] = { ...it, group: g.group };
  const countrySel = $("select[name=country]"), segSel = $("select[name=segment_pick]"), stateSel = $("select[name=state]"), citySel = $("select[name=city]");
  const segCustom = $("input[name=segment_custom]"), cityCustom = $("input[name=city_custom]");

  const fillSegments = (code, keep) => {
    const lang = code === "BR" ? "pt" : "en";
    const groups = m.segment_catalog.map((g) => {
      const opts = g.items.filter((it) => it[lang]).map((it) => `<option value="${it.id}">${esc(lang === "pt" ? it.pt : `${it.pt || it.en} (${it.en})`)}</option>`).join("");
      return opts ? `<optgroup label="${esc(g.label)}">${opts}</optgroup>` : "";
    }).join("");
    segSel.innerHTML = `<option value="" disabled>Escolha o segmento</option>${groups}<optgroup label="Outro"><option value="__custom">Digitar outro segmento…</option></optgroup>`;
    segSel.value = keep && segSel.querySelector(`option[value="${CSS.escape(keep)}"]`) ? keep : "";
    toggleCustom(segSel, segCustom, code === "BR" ? "ex.: estúdios de fotografia" : "ex.: wedding photographers");
  };
  const toggleCustom = (sel, input, ph) => {
    const on = sel.value === "__custom";
    input.hidden = !on; input.required = on; input.placeholder = ph;
    if (on && document.activeElement === sel) input.focus();
  };
  const fillCities = async (code, stateCode, keepCity) => {
    citySel.disabled = true;
    if (!stateCode) { citySel.innerHTML = `<option value="">Escolha o estado</option>`; cityCustom.hidden = true; return; }
    const geo = await loadGeo(code);
    const st = geo.states.find((s) => s.code === stateCode);
    const cities = st ? st.cities : [];
    const cap = st && st.capital ? `<option value="${esc(st.capital)}">${esc(st.capital)} (capital)</option>` : "";
    citySel.innerHTML = `<option value="" disabled>Escolha a cidade (${cities.length})</option>${cap}`
      + cities.filter((c) => !st || c !== st.capital).map((c) => `<option value="${esc(c)}">${esc(c)}</option>`).join("")
      + `<option value="__custom">Outra cidade (digitar)…</option>`;
    citySel.disabled = false;
    if (keepCity && cities.includes(keepCity)) citySel.value = keepCity;
    else if (keepCity) { citySel.value = "__custom"; cityCustom.value = keepCity; }
    else citySel.value = "";
    toggleCustom(citySel, cityCustom, "nome da cidade");
  };
  const fillStates = async (code, keepState, keepCity) => {
    stateSel.innerHTML = `<option value="">Carregando…</option>`;
    try {
      const geo = await loadGeo(code);
      stateSel.innerHTML = `<option value="" disabled>${code === "GB" ? "Região" : "Estado"}</option>` + geo.states.map((s) => `<option value="${esc(s.code)}">${esc(code === "BR" ? `${s.name} (${s.code})` : s.name)}</option>`).join("");
      stateSel.value = keepState && geo.states.some((s) => s.code === keepState) ? keepState : "";
      await fillCities(code, stateSel.value, keepCity);
    } catch (e) { stateSel.innerHTML = `<option value="">${esc(e.message)}</option>`; }
  };
  const applyCountry = (keep = {}) => {
    const code = countrySel.value;
    const ex = COUNTRY_EXAMPLES[code] || COUNTRY_EXAMPLES.US;
    fillSegments(code, keep.segmentPick);
    if (keep.segmentCustom) { segSel.value = "__custom"; segCustom.value = keep.segmentCustom; toggleCustom(segSel, segCustom, ""); }
    fillStates(code, keep.state, keep.city);
    $("#f-regions").placeholder = ex.regions;
    $("#f-regions").previousElementSibling.textContent = code === "BR" ? "Bairros ou regiões (opcional, separados por vírgula)" : "Bairros ou regiões (opcional, em inglês, separados por vírgula)";
    $("#only-mobile").hidden = !["BR", "GB", "AU"].includes(code);
    $("#country-hint").textContent = ex.hint;
  };
  countrySel.addEventListener("change", () => applyCountry());
  segSel.addEventListener("change", () => toggleCustom(segSel, segCustom, segCustom.placeholder));
  stateSel.addEventListener("change", () => fillCities(countrySel.value, stateSel.value));
  citySel.addEventListener("change", () => toggleCustom(citySel, cityCustom, "nome da cidade"));
  applyCountry((last.country || "BR") === countrySel.value ? last : {});
}

async function startSearch(ev) {
  ev.preventDefault();
  const fd = new FormData(ev.target);
  const num = (k) => (fd.get(k) === "" || fd.get(k) == null ? null : Number(String(fd.get(k)).replace(",", ".")));
  const country = fd.get("country") || "BR";
  const segPick = fd.get("segment_pick");
  const item = SEGMENT_INDEX[segPick];
  const segment = segPick === "__custom" ? String(fd.get("segment_custom") || "").trim() : item ? item[country === "BR" ? "pt" : "en"] : "";
  const cityPick = fd.get("city");
  const city = cityPick === "__custom" ? String(fd.get("city_custom") || "").trim() : String(cityPick || "");
  if (segment.length < 2) { toast("Escolha o segmento (ou digite em “Outro segmento”).", true); return; }
  if (!fd.get("state")) { toast("Escolha o estado.", true); return; }
  if (city.length < 2) { toast("Escolha a cidade.", true); return; }
  const body = {
    country, segment, segment_group: item && segPick !== "__custom" ? item.group : null,
    city, state: fd.get("state") || null,
    regions: String(fd.get("regions") || "").split(/[,\n;]/).map((s) => s.trim()).filter(Boolean),
    max_results: num("max_results") || 40, use_ai: !!fd.get("use_ai"),
    filters: { website: fd.get("website"), min_rating: num("min_rating"), min_reviews: num("min_reviews"),
               require_phone: !!fd.get("require_phone"), only_mobile: !$("#only-mobile").hidden && !!fd.get("only_mobile") },
  };
  const btn = $("button[type=submit]", ev.target);
  await run(btn, async () => {
    const job = await api("POST", "/api/searches", body);
    store("prospecta_last_search", JSON.stringify({ country, segmentPick: segPick, segmentCustom: segPick === "__custom" ? segment : "", city, state: body.state, regions: body.regions }));
    toast("Pesquisa iniciada.");
    showJob(job); pollJob(job.id);
  });
}

const JOB_STATUS = { na_fila: "Na fila", executando: "Em andamento", concluida: "Concluída", concluida_com_erros: "Concluída com erros", falhou: "Falhou", cancelada: "Cancelada", interrompida: "Interrompida" };
const DISCARD = { fechada: "fechadas", tem_site: "com site", tem_site_proprio: "com site próprio", sem_site_proprio: "sem site próprio", nota_abaixo_do_minimo: "nota abaixo do mínimo", poucas_avaliacoes: "com poucas avaliações", avaliacoes_acima_do_maximo: "avaliações acima do máximo", sem_telefone: "sem telefone", telefone_nao_celular: "sem celular", lista_de_supressao: "na lista de não contatar", fora_do_pais: "de outro país" };

function showJob(job) {
  const el = $("#job");
  if (!el) return;
  const running = ["na_fila", "executando"].includes(job.status);
  const isSearch = (job.params || {}).kind !== "analise";
  const title = isSearch ? `${esc(job.params.segment || "")} em ${esc(job.params.city || "")}${job.params.state ? " - " + esc(job.params.state) : ""}` : "Análise de planilha importada";
  const pct = job.total ? Math.round((job.progress / job.total) * 100) : 0;
  const discards = Object.entries(job.discard_reasons || {}).map(([k, v]) => `${v} ${DISCARD[k] || k}`).join(", ");
  el.innerHTML = `
    <div class="job" aria-live="polite">
      <div class="job-head"><strong>${title}</strong><span class="small muted">${esc(JOB_STATUS[job.status] || job.status)}</span></div>
      ${running ? `<div class="bar ${job.total ? "" : "indeterminate"}"><span style="width:${pct}%"></span></div><div class="small muted">${esc(job.stage || "")}</div>` : ""}
      <p class="small" style="margin:8px 0 0">${isSearch ? `${job.found} encontradas, ${job.saved_new} novas, ${job.updated} já conhecidas` : `${job.found} analisadas`}${job.high_priority ? `, <strong>${job.high_priority} de alta prioridade</strong>` : ""}.${discards ? ` Descartadas: ${esc(discards)}.` : ""}${isSearch ? ` ${job.api_calls} chamada(s) ao Google.` : ""}</p>
      ${job.error ? `<p class="small" style="color:var(--alert)">${esc(job.error)}</p>` : ""}
      <div style="margin-top:8px;display:flex;gap:8px">
        ${running ? `<button class="btn-small" id="cancel-job" type="button">Cancelar</button>` : `<button class="btn-small" id="scope-job" type="button">Ver só esta pesquisa</button>`}
      </div>
    </div>`;
  if (running) $("#cancel-job").addEventListener("click", (e) => run(e.currentTarget, async () => { await api("POST", `/api/searches/${job.id}/cancel`); toast("Cancelando..."); }));
  else $("#scope-job").addEventListener("click", () => { state.filters = { sort: "score", page: 1, search_id: job.id }; loadTable(); });
  if (running && !state.pollTimer) pollJob(job.id);
}

function pollJob(id) {
  clearInterval(state.pollTimer);
  state.pollTimer = setInterval(async () => {
    try {
      const job = await api("GET", `/api/searches/${id}`);
      showJob(job);
      if (!["na_fila", "executando"].includes(job.status)) {
        clearInterval(state.pollTimer); state.pollTimer = null;
        state.meta = await api("GET", "/api/meta");
        loadTable(); loadTally();
        toast(`Pesquisa ${JOB_STATUS[job.status].toLowerCase()}.`);
      } else if (job.saved_new + job.updated > 0) { loadTable(); }
    } catch (e) { clearInterval(state.pollTimer); state.pollTimer = null; }
  }, 1500);
}

// ------------------------------------------------------------------ detalhe do lead
async function renderLead(id) {
  const d = await api("GET", `/api/leads/${id}`);
  drawLead(d);
}

function drawLead(d) {
  const l = d.lead, m = state.meta, c = d.contact, a = l.analysis || {}, sb = l.score_breakdown || {};
  const variant = l.message_variant || d.suggested_variant;
  let channel = l.message_channel || d.best_channel || (["US", "CA"].includes(l.country) ? "ligacao" : "whatsapp");
  const options = d.channel_options || d.channels;
  const shortTarget = (ch) => String(ch.target || "").replace(/^https?:\/\/(www\.)?/, "").replace(/\/$/, "");
  const hasInstagram = !!(l.social_links && l.social_links.Instagram);
  const banners = [];
  if (l.source === "demo") banners.push(`<p class="banner">Empresa fictícia de demonstração. O envio fica desativado.</p>`);
  if (l.google_content_purged) banners.push(`<p class="banner warn">Os dados do Google desta empresa expiraram e foram removidos (regra de cache do Google). Use "Atualizar dados do Google".</p>`);
  else if (d.google_data_stale) banners.push(`<p class="banner">Dados do Google com mais de ${m.cache_google_dias} dias. Atualize antes de abordar.</p>`);
  const hours = Array.isArray(l.opening_hours) ? l.opening_hours : [];
  const socials = Object.entries(l.social_links || {});
  const site = l.site_analysis || {};

  app.innerHTML = `
    <a class="back" href="#/">Voltar para a lista</a>
    <section class="lead-head">
      <div>${scoreBadge(l.score, l.priority, true)}<span class="prio">${esc(prioLabel(l.priority))}</span></div>
      <div>
        <h1>${esc(l.name)}</h1>
        <p class="sub">${esc([l.category, l.neighborhood, l.city && (l.city + (l.state ? " - " + l.state : "")), l.country && l.country !== "BR" ? countryName(l.country) : ""].filter(Boolean).join(", "))}</p>
        <p class="next-action">Próxima ação: <mark>${esc(d.next_action || "—")}</mark></p>
      </div>
      <div class="status-box"><label for="lead-status">Etapa comercial</label><select id="lead-status">${statusOptions(l.status)}</select></div>
    </section>
    ${banners.join("")}
    <div class="lead-grid">
      <div>
        <section class="section" aria-labelledby="h-msg">
          <header><h2 id="h-msg">Abordagem</h2><span class="small muted">${l.message_generated_at ? `Gerada por ${l.message_generated_by === "ia" ? "IA" : "modelo"} em ${fmtDate(l.message_generated_at)}` : "Ainda não gerada"}</span></header>
          <div class="channels" role="group" aria-label="Por onde contatar">
            ${options.map((ch) => `<button type="button" class="channel${ch.key === channel ? " active" : ""}${ch.available ? "" : " missing"}" data-channel="${ch.key}" aria-pressed="${ch.key === channel}">
                <span class="ch-name">${esc(ch.label)}${ch.key === d.best_channel && ch.available ? ` <span class="ch-best">recomendado</span>` : ""}</span>
                <span class="ch-target">${ch.available ? `${esc(shortTarget(ch))}${ch.basis === "hipotese" ? " (não verificado)" : ""}` : ch.key === "formulario" ? (ch.target ? "não achado na página inicial" : "sem site") : "sem contato: adicionar"}</span>
              </button>`).join("")}
          </div>
          <p class="small muted channel-reason" id="channel-reason"></p>
          ${hasInstagram ? "" : `<p class="small"><a href="${esc(safeUrl(d.instagram_search_url))}" target="_blank" rel="noopener noreferrer">Procurar o Instagram da empresa no Google</a> e, se encontrar, clique em “Direct do Instagram” para salvar.</p>`}
          <div class="composer">
            <div class="row">
              <select id="variant" aria-label="Situação da mensagem">${Object.entries(m.variants).map(([k, v]) => `<option value="${k}" ${k === variant ? "selected" : ""}>${esc(v)}${k === d.suggested_variant ? " (sugerida)" : ""}</option>`).join("")}</select>
              ${m.ia_configurada ? `<label class="check"><input type="checkbox" id="use-ai"> Redigir com IA</label>` : ""}
              <select id="lang" aria-label="Idioma da mensagem" style="flex:0 0 auto;width:auto"><option value="pt" ${l.language === "pt" ? "selected" : ""}>Português</option><option value="en" ${l.language === "en" ? "selected" : ""}>Inglês</option></select>
              <button id="gen" type="button">${l.suggested_message ? "Gerar de novo" : "Gerar mensagem"}</button>
            </div>
            <div id="subject-row" class="form-grid" ${channel === "email" ? "" : "hidden"}>
              <div><label for="to">Para</label><input id="to" type="email" maxlength="120" value="${esc((l.emails || [])[0] || "")}" placeholder="e-mail da empresa" autocomplete="off"></div>
              <div><label for="subject">Assunto</label><input id="subject" type="text" maxlength="200" value="${esc(l.message_subject || "")}"></div>
            </div>
            <label for="msg" id="msg-label">${channel === "ligacao" ? "Roteiro: use como guia, fale com naturalidade" : "Revise e ajuste antes de enviar"}</label>
            <textarea id="msg" maxlength="2000" placeholder="Clique em “Gerar mensagem”.">${esc(l.suggested_message || "")}</textarea>
            <div class="counter"><span id="msg-count">0</span> caracteres</div>
            ${l.message_channel && l.message_channel !== channel ? `<p class="small" style="color:var(--alert)">Esta mensagem foi escrita para ${esc(CHANNEL_NAMES[l.message_channel] || l.message_channel)}. Clique em “Gerar de novo” para o canal escolhido.</p>` : ""}
            ${(l.message_warnings || []).length ? `<ul class="checks">${l.message_warnings.map((w) => `<li class="${w.nivel === "bloqueante" ? "block" : "warn"}">${esc(w.motivo)}</li>`).join("")}</ul>` : ""}
            <div class="row send-row" id="send-actions"></div>
            <div class="row">
              <button id="sent" type="button" ${c.allowed ? "" : "disabled"}>Registrar contato feito</button>
              <span class="small muted" id="sent-hint"></span>
            </div>
            <ul class="checks">
              ${c.blockers.map((b) => `<li class="block">${esc(b)}</li>`).join("")}
              ${c.allowed ? `<li class="ok">Contato permitido pela política (${c.sent_today} de ${c.daily_limit} hoje).</li>` : ""}
              ${c.warnings.map((w) => `<li class="warn">${esc(w)}</li>`).join("")}
            </ul>
          </div>
          <details class="more" style="margin-top:12px">
            <summary>Personalizar (responsável e prévia)</summary>
            <form id="perso" class="form-grid">
              <div><label for="resp">Nome do responsável</label><input id="resp" type="text" name="responsible_name" maxlength="120" value="${esc(l.responsible_name || "")}"></div>
              <div><label for="purl">Link da prévia do site</label><input id="purl" type="url" name="preview_url" maxlength="300" value="${esc(l.preview_url || "")}" placeholder="https://"></div>
              <label class="check full"><input type="checkbox" name="preview_ready" ${l.preview_ready ? "checked" : ""}> Já preparei uma prévia para esta empresa (a mensagem oferece mandar o link)</label>
              <div><button type="submit">Salvar</button></div>
            </form>
          </details>
        </section>

        <section class="section" aria-labelledby="h-score">
          <header><h2 id="h-score">Por que ${l.score ?? "–"} pontos</h2><button class="btn-small" id="reanalyze" type="button">Analisar de novo</button></header>
          ${(sb.items || []).length ? `<ul class="breakdown">${sb.items.map((i) => `
            <li><span class="pts ${i.points < 0 ? "neg" : i.points === 0 ? "zero" : ""}">${i.points > 0 ? "+" : ""}${i.points}</span>
            <span>${esc(i.label)} ${basisTag(i.basis)}<span class="evidence">${esc(i.evidence || "")}</span></span></li>`).join("")}</ul>` : `<p class="muted">Ainda não pontuado.</p>`}
          <p class="small muted" style="margin-top:8px">Pesos ajustáveis em Configurações. “Hipótese” indica interpretação, não fato verificado.</p>
        </section>

        <section class="section" aria-labelledby="h-analysis">
          <header><h2 id="h-analysis">Análise comercial</h2>${m.ia_configurada ? `<button class="btn-small" id="reanalyze-ai" type="button">Reescrever com IA</button>` : ""}</header>
          ${a.resumo ? `<p>${esc(a.resumo)}</p><p>${esc(a.justificativa || "")}</p>
            <h3 style="margin-top:14px">Fatos verificados</h3>
            <ul class="facts">${(a.fatos_verificados || []).map((f) => `<li>${esc(f.texto)} <span class="small muted">(${esc(f.fonte)})</span></li>`).join("")}</ul>
            <h3>Hipóteses</h3>
            <ul class="facts hyp">${(a.hipoteses || []).map((h) => `<li>${esc(h)}</li>`).join("")}${(a.hipoteses_ia || []).map((h) => `<li>${esc(h)} (sugerida pela IA)</li>`).join("")}</ul>
            <p class="small muted">${l.analysis_generated_by === "ia" ? "Resumo e justificativa redigidos pela IA a partir dos fatos verificados." : "Análise gerada por regras, sem IA."}</p>` : `<p class="muted">Clique em “Analisar de novo” para gerar a análise.</p>`}
        </section>
      </div>

      <div>
        <section class="section" aria-labelledby="h-data">
          <header><h2 id="h-data">Dados da empresa</h2>${l.source === "google_places" ? `<span class="small muted">Fonte: Google Maps</span>` : ""}${l.place_id ? `<button class="btn-small" id="refresh" type="button">Atualizar dados do Google</button>` : ""}</header>
          <dl class="data">
            <dt>Telefone</dt><dd>${esc(l.phone || "—")}${l.whatsapp_status === "sem_whatsapp" ? ` <span class="small muted">(sem WhatsApp)</span>` : ""}</dd>
            <dt>WhatsApp</dt><dd>${l.whatsapp_e164 ? `${esc(l.whatsapp_e164)} <span class="small muted">(${esc({ site: "publicado no site/links", manual: "informado por você", planilha: "da planilha", cadastro: "do cadastro" }[l.whatsapp_source] || "publicado")})</span>` : l.whatsapp_source === "descartado" ? "O número publicado não tem WhatsApp" : "Não encontrado"}</dd>
            <dt>E-mail</dt><dd>${(l.emails || []).length ? l.emails.map((e) => esc(e)).join(", ") : "Não encontrado"}</dd>
            <dt>Site</dt><dd>${l.website ? `<a href="${esc(safeUrl(l.website))}" target="_blank" rel="noopener noreferrer">${esc(l.website)}</a>` : "Nenhum informado"}</dd>
            <dt>Segmento</dt><dd><select id="seg" class="inline-select" aria-label="Segmento da empresa">${state.meta.segments.map((sg) => `<option value="${sg.key}" ${sg.key === l.segment ? "selected" : ""}>${esc(sg.label)}</option>`).join("")}</select></dd>
            <dt>Presença</dt><dd>${esc(site.kind_label || PRESENCE_SHORT[l.presence_kind] || "A analisar")}${site.platform ? ` (${esc(site.platform)})` : ""}</dd>
            <dt>Google</dt><dd>${l.rating != null ? `Nota ${fmtRating(l.rating)} com ${l.reviews_count ?? 0} avaliações` : "Sem nota"}${l.maps_url ? ` <a href="${esc(safeUrl(l.maps_url))}" target="_blank" rel="noopener noreferrer">ver no Maps</a>` : ""}</dd>
            <dt>Endereço</dt><dd>${esc(l.address || "—")}</dd>
            ${socials.length ? `<dt>Redes</dt><dd>${socials.map(([k, u]) => `<a href="${esc(safeUrl(u))}" target="_blank" rel="noopener noreferrer">${esc(k)}</a>`).join(", ")}</dd>` : ""}
            ${hours.length ? `<dt>Horário</dt><dd><details class="more"><summary>Ver horários</summary>${hours.map((h) => `<div class="small">${esc(h)}</div>`).join("")}</details></dd>` : ""}
            <dt>Contatos</dt><dd><details class="more"><summary>Adicionar ou corrigir WhatsApp, e-mail, Instagram e Facebook</summary>
              <form id="contacts-form" class="form-grid">
                <div><label for="c-wa">WhatsApp</label><input id="c-wa" type="text" name="whatsapp" maxlength="40" value="${esc(l.whatsapp_e164 || "")}" placeholder="(41) 99999-9999"></div>
                <div><label for="c-em">E-mail</label><input id="c-em" type="text" name="emails" maxlength="300" value="${esc((l.emails || []).join(", "))}" placeholder="contato@empresa.com"></div>
                <div class="full"><label for="c-fb">Página no Facebook</label><input id="c-fb" type="text" name="facebook" maxlength="300" value="${esc((l.social_links || {}).Facebook || "")}" placeholder="facebook.com/empresa" autocomplete="off"></div>
                <div class="full"><label for="c-ig">Instagram (link do perfil ou @)</label><input id="c-ig" type="text" name="instagram" maxlength="200" value="${esc((l.social_links || {}).Instagram || "")}" placeholder="@empresa ou https://instagram.com/empresa" autocomplete="off"></div>
                <div><button type="submit">Salvar contatos</button></div>
              </form>
              <p class="small muted">Dica: o WhatsApp e o e-mail costumam estar na bio do Instagram da empresa.</p></details></dd>
            <dt>Origem</dt><dd class="small">${esc({ google_places: "Google Places API", csv_importacao: "Planilha importada", manual: "Cadastro manual", demo: "Demonstração (fictício)" }[l.source] || l.source)}, coletado em ${fmtDate(l.created_at, false)}${l.google_fetched_at ? `, dados do Google de ${fmtDate(l.google_fetched_at, false)}` : ""}</dd>
          </dl>
        </section>

        <section class="section" aria-labelledby="h-hist">
          <header><h2 id="h-hist">Histórico</h2></header>
          <form id="interaction" class="form-grid">
            <div><label for="it-type">Registrar</label><select id="it-type" name="type">
              ${["resposta_recebida", "ligacao", "reuniao", "proposta", "nota", "opt_out"].map((t) => `<option value="${t}">${esc(m.event_types[t])}</option>`).join("")}</select></div>
            <div><label for="it-ch">Canal</label><select id="it-ch" name="channel"><option value="">—</option>${m.channels.map((ch) => `<option>${ch}</option>`).join("")}</select></div>
            <div class="full"><label for="it-sum">Resumo</label><input id="it-sum" type="text" name="summary" maxlength="1000" placeholder="Ex.: pediu orçamento para site com agendamento"></div>
            <div class="full" style="display:flex;gap:8px;flex-wrap:wrap">
              <button type="submit">Registrar</button>
              <button type="button" class="btn-small" id="reply-msgs">Sugerir resposta</button>
            </div>
          </form>
          <ul class="timeline">${d.events.map((e) => `
            <li class="${e.type === "mensagem_enviada" ? "contact" : e.type === "resposta_recebida" ? "reply" : e.type === "opt_out" ? "stop" : ""}">
              <time>${fmtDate(e.created_at)}, ${esc(e.actor)}</time>${esc(e.summary || m.event_types[e.type] || e.type)}</li>`).join("")}</ul>
        </section>

        <section class="section" aria-labelledby="h-tasks">
          <header><h2 id="h-tasks">Tarefas</h2></header>
          <ul class="tasks">${d.tasks.map((t) => `<li class="${t.done ? "done" : ""}"><input type="checkbox" data-task="${t.id}" ${t.done ? "checked" : ""} aria-label="Concluir ${esc(t.title)}">
            <span>${esc(t.title)} <span class="small ${!t.done && t.due_date < todayISO() ? "overdue" : "muted"}">até ${fmtDate(t.due_date, false)}</span></span></li>`).join("") || `<li class="muted small">Nenhuma tarefa.</li>`}</ul>
          <form id="task-form" class="form-grid">
            <div class="full"><label for="t-title">Nova tarefa</label><input id="t-title" type="text" name="title" required minlength="2" maxlength="200" placeholder="Ex.: retomar contato"></div>
            <div><label for="t-date">Até</label><input id="t-date" type="date" name="due_date" required value="${addDaysISO(3)}"></div>
            <div><button type="submit">Criar tarefa</button></div>
          </form>
        </section>

        <section class="section" aria-labelledby="h-notes">
          <header><h2 id="h-notes">Anotações</h2></header>
          <textarea id="notes" rows="4" maxlength="5000" placeholder="Observações sobre a empresa e a conversa">${esc(l.notes || "")}</textarea>
          <button id="save-notes" type="button" style="margin-top:8px">Salvar anotações</button>
        </section>

        <section class="section" aria-labelledby="h-privacy">
          <header><h2 id="h-privacy">Privacidade</h2></header>
          <p class="small muted">Consentimento: <strong>${esc({ nao_registrado: "não registrado", opt_in: "autorizou contato", opt_out: "pediu para não ser contatada" }[l.consent_status] || l.consent_status)}</strong>${l.consent_at ? ` em ${fmtDate(l.consent_at)}` : ""}.</p>
          <div style="display:flex;gap:8px;flex-wrap:wrap">
            <button class="btn-small" id="optin" type="button" ${l.consent_status === "opt_in" ? "disabled" : ""}>Registrar que autorizou contato</button>
            <button class="btn-small btn-danger" id="dnc" type="button" ${l.status === "nao_contatar" ? "disabled" : ""}>Não contatar novamente</button>
            <button class="btn-small btn-danger" id="del" type="button">Excluir dados</button>
          </div>
        </section>
      </div>
    </div>`;

  const id = l.id;
  const msg = $("#msg");
  const copyText = async () => {
    try { await navigator.clipboard.writeText(msg.value); return true; } catch { msg.select(); toast("Selecione e copie com Ctrl+C.", true); return false; }
  };
  const option = (key) => options.find((ch) => ch.key === key) || {};
  const target = (key) => option(key).available ? option(key).target : null;
  const EMAIL_OK = /^[^\s@]+@[^\s@]+\.[A-Za-z]{2,}$/;
  // Canal sem contato: um campo para adicionar e salvar sem sair da abordagem
  const ADD_FIELD = {
    whatsapp: { field: "whatsapp", label: "WhatsApp da empresa", ph: l.country === "BR" ? "(41) 99999-9999" : "+1 512 555 0123", type: "text" },
    instagram: { field: "instagram", label: "Instagram da empresa", ph: "@empresa ou link do perfil", type: "text" },
    facebook: { field: "facebook", label: "Página no Facebook", ph: "facebook.com/empresa", type: "text" },
    ligacao: { field: "phone", label: "Telefone", ph: "", type: "text" },
  };
  const renderSendActions = () => {
    const off = c.allowed ? "" : 'aria-disabled="true" tabindex="-1" style="pointer-events:none;opacity:.45"';
    const box = $("#send-actions");
    let html = `<button id="copy" type="button">Copiar</button>`;
    let add = "";
    if (channel === "whatsapp" && target("whatsapp")) {
      html += `<a id="wa" class="btn btn-send" target="_blank" rel="noopener noreferrer" ${off}>Abrir no WhatsApp</a>
               <button id="no-wa" class="btn-small" type="button" title="O WhatsApp avisou que o número não está no app">Não tem WhatsApp</button>`;
    } else if (channel === "instagram" && target("instagram")) {
      html += `<button id="ig" class="btn btn-send" type="button" ${off}>Copiar e abrir o Instagram</button>`;
    } else if (channel === "facebook" && target("facebook")) {
      html += `<button id="fb" class="btn btn-send" type="button" ${off}>Copiar e abrir o Messenger</button>`;
    } else if (channel === "email") {
      html += `<a id="mail" class="btn btn-send" ${off}>Abrir no e-mail</a>`;
    } else if (channel === "formulario" && option("formulario").target) {
      html += `<button id="form-open" class="btn btn-send" type="button" ${off}>Copiar e abrir o site</button>`;
    } else if (channel === "ligacao" && target("ligacao")) {
      html += `<a class="btn btn-send" href="tel:${esc(target("ligacao"))}" ${off}>Ligar ${esc(l.phone || "")}</a>`;
    } else if (ADD_FIELD[channel]) {
      const f = ADD_FIELD[channel];
      add = `<form id="add-contact" class="add-contact"><label for="add-val">${esc(f.label)}</label>
               <div class="row"><input id="add-val" type="${f.type}" maxlength="200" placeholder="${esc(f.ph)}" required autocomplete="off"><button type="submit">Salvar</button></div>
               ${channel === "instagram" ? `<a class="small" href="${esc(safeUrl(d.instagram_search_url))}" target="_blank" rel="noopener noreferrer">Procurar o Instagram no Google</a>` : ""}</form>`;
    } else {
      html += `<span class="small muted">Esta empresa não tem site cadastrado.</span>`;
    }
    box.innerHTML = add + html;
    $("#copy").addEventListener("click", async () => { if (await copyText()) toast("Mensagem copiada."); });
    if ($("#no-wa")) $("#no-wa").addEventListener("click", (e) => run(e.currentTarget, async () => {
      reload(await api("POST", `/api/leads/${id}/interactions`, { type: "sem_whatsapp" }));
      toast("Anotado. O próximo canal recomendado foi atualizado.");
    }));
    const copyOpen = (btnId, url, done) => { if ($(btnId)) $(btnId).addEventListener("click", async () => { await copyText(); window.open(safeUrl(url), "_blank", "noopener"); toast(done); }); };
    copyOpen("#ig", target("instagram"), "Mensagem copiada. Cole no Direct.");
    copyOpen("#fb", d.messenger_url || target("facebook"), "Mensagem copiada. Cole na conversa do Messenger.");
    copyOpen("#form-open", option("formulario").target, "Mensagem copiada. Cole no formulário de contato do site.");
    if ($("#add-contact")) $("#add-contact").addEventListener("submit", (e) => { e.preventDefault(); run($("button", e.target), async () => {
      const r = await api("PATCH", `/api/leads/${id}`, { [ADD_FIELD[channel].field]: $("#add-val").value.trim() });
      toast("Contato salvo."); reload(r);
    }); });
    $("#channel-reason").textContent = option(channel).reason || "";
    $("#sent-hint").textContent = channel === "ligacao" ? "Registre depois de ligar." : "Registre depois de enviar.";
    updateLinks();
  };
  const updateLinks = () => {
    $("#msg-count").textContent = msg.value.length;
    if ($("#wa")) $("#wa").href = `https://wa.me/${target("whatsapp").replace("+", "")}?text=${encodeURIComponent(msg.value)}`;
    const to = $("#to").value.trim();
    if ($("#mail")) $("#mail").href = `mailto:${EMAIL_OK.test(to) ? to : ""}?subject=${encodeURIComponent($("#subject").value)}&body=${encodeURIComponent(msg.value)}`;
  };
  $("#to").addEventListener("input", updateLinks);
  $("#to").addEventListener("change", () => run(null, async () => {
    const to = $("#to").value.trim().toLowerCase();
    if (!to || (l.emails || []).includes(to)) return;
    if (!EMAIL_OK.test(to)) { toast("E-mail inválido.", true); return; }
    await api("PATCH", `/api/leads/${id}`, { emails: [to, ...(l.emails || [])].join(", ") });
    l.emails = [to, ...(l.emails || [])];
    toast("E-mail salvo na empresa.");
  }));
  msg.addEventListener("input", updateLinks);
  $("#subject").addEventListener("input", updateLinks);
  $("#subject").addEventListener("change", () => run(null, async () => { await api("PATCH", `/api/leads/${id}`, { message_subject: $("#subject").value }); }));
  renderSendActions();
  const savedText = l.suggested_message || "";
  $("#variant").addEventListener("change", () => {
    if (msg.value.trim() && msg.value !== savedText) { toast("Você editou o texto. Clique em “Gerar de novo” para trocar a abordagem.", true); return; }
    $("#gen").click();
  });
  $$(".channel").forEach((btn) => btn.addEventListener("click", () => run(btn, async () => {
    channel = btn.dataset.channel;
    const r = await api("POST", `/api/leads/${id}/message`, { channel, use_ai: !!($("#use-ai") || {}).checked });
    toast(`Mensagem para ${CHANNEL_NAMES[channel] || channel} gerada.`);
    reload(r);
  })));
  msg.addEventListener("change", () => run(null, async () => { await api("PATCH", `/api/leads/${id}`, { suggested_message: msg.value }); toast("Mensagem salva."); }));
  const reload = async (data) => drawLead(data && data.lead ? data : await api("GET", `/api/leads/${id}`));

  $("#lead-status").addEventListener("change", (e) => run(e.target, async () => reload(await api("POST", `/api/leads/${id}/status`, { status: e.target.value }))));
  $("#lang").addEventListener("change", (e) => run(e.target, async () => {
    await api("PATCH", `/api/leads/${id}`, { language: e.target.value });
    l.language = e.target.value;
    toast("Idioma alterado. Clique em “Gerar” para refazer a mensagem.");
  }));
  $("#gen").addEventListener("click", (e) => run(e.currentTarget, async () => {
    const r = await api("POST", `/api/leads/${id}/message`, { variant: $("#variant").value, channel, use_ai: !!($("#use-ai") || {}).checked });
    const moved = r.channel && r.channel !== channel ? ` Canal trocado para ${CHANNEL_NAMES[r.channel] || r.channel}.` : "";
    toast((r.generated_by === "ia" ? "Mensagem redigida pela IA." : "Mensagem gerada.") + moved); reload(r);
  }));
  $("#seg").addEventListener("change", (e) => run(e.currentTarget, async () => {
    const r = await api("PATCH", `/api/leads/${id}`, { segment: e.currentTarget.value });
    toast("Segmento alterado. Gere a mensagem de novo para usar os exemplos do novo segmento."); reload(r);
  }));
  $("#contacts-form").addEventListener("submit", (e) => { e.preventDefault(); run($("button", e.target), async () => {
    const fd = new FormData(e.target);
    const val = (k) => String(fd.get(k) || "").trim();
    const body = {};  // só o que mudou (não transforma o WhatsApp do site em "informado por você")
    if (val("whatsapp") !== (l.whatsapp_e164 || "")) body.whatsapp = val("whatsapp") || null;
    if (val("emails") !== (l.emails || []).join(", ")) body.emails = val("emails") || null;
    if (val("instagram") !== ((l.social_links || {}).Instagram || "")) body.instagram = val("instagram");
    if (val("facebook") !== ((l.social_links || {}).Facebook || "")) body.facebook = val("facebook");
    if (!Object.keys(body).length) { toast("Nada mudou."); return; }
    const r = await api("PATCH", `/api/leads/${id}`, body);
    toast("Contatos salvos."); reload(r);
  }); });
  $("#sent").addEventListener("click", (e) => run(e.currentTarget, async () => {
    reload(await api("POST", `/api/leads/${id}/interactions`, { type: "mensagem_enviada", channel, message_text: msg.value }));
    toast("Contato registrado.");
  }));
  $("#perso").addEventListener("submit", (e) => { e.preventDefault(); run($("button", e.target), async () => {
    const fd = new FormData(e.target);
    reload(await api("PATCH", `/api/leads/${id}`, { responsible_name: fd.get("responsible_name") || null, preview_url: fd.get("preview_url") || null, preview_ready: !!fd.get("preview_ready") }));
    toast("Salvo. Gere a mensagem de novo para aplicar.");
  }); });
  $("#reanalyze").addEventListener("click", (e) => run(e.currentTarget, async () => { reload(await api("POST", `/api/leads/${id}/analyze`, { refresh_site: true })); toast("Análise atualizada."); }));
  if ($("#reanalyze-ai")) $("#reanalyze-ai").addEventListener("click", (e) => run(e.currentTarget, async () => { reload(await api("POST", `/api/leads/${id}/analyze`, { use_ai: true })); toast("Análise reescrita."); }));
  if ($("#refresh")) $("#refresh").addEventListener("click", (e) => run(e.currentTarget, async () => { reload(await api("POST", `/api/leads/${id}/refresh`, {})); toast("Dados atualizados pelo Google."); }));
  $("#interaction").addEventListener("submit", (e) => { e.preventDefault(); run($("button[type=submit]", e.target), async () => {
    const fd = new FormData(e.target);
    reload(await api("POST", `/api/leads/${id}/interactions`, { type: fd.get("type"), channel: fd.get("channel") || null, summary: fd.get("summary") || null }));
    toast("Registrado.");
  }); });
  $("#reply-msgs").addEventListener("click", () => {
    const t = $("#it-type").value;
    const map = { resposta_recebida: "resposta_interesse", opt_out: "opt_out" };
    $("#variant").value = map[t] || "pedido_informacoes";
    $("#variant").focus();
    toast("Escolha a situação da resposta e clique em “Gerar”.");
  });
  $$("[data-task]").forEach((cb) => cb.addEventListener("change", () => run(cb, async () => { await api("PATCH", `/api/tasks/${cb.dataset.task}`, { done: cb.checked }); reload(); })));
  $("#task-form").addEventListener("submit", (e) => { e.preventDefault(); run($("button", e.target), async () => {
    const fd = new FormData(e.target);
    await api("POST", `/api/leads/${id}/tasks`, { title: fd.get("title"), due_date: fd.get("due_date") });
    toast("Tarefa criada."); reload();
  }); });
  $("#save-notes").addEventListener("click", (e) => run(e.currentTarget, async () => { reload(await api("PATCH", `/api/leads/${id}`, { notes: $("#notes").value })); toast("Anotações salvas."); }));
  $("#optin").addEventListener("click", (e) => run(e.currentTarget, async () => reload(await api("POST", `/api/leads/${id}/consent`, { status: "opt_in", note: "Autorizou contato (registrado manualmente)" }))));
  confirmTwice($("#dnc"), "Confirmar: não contatar", async () => { reload(await api("POST", `/api/leads/${id}/status`, { status: "nao_contatar", note: "Marcado manualmente" })); toast("Empresa adicionada à lista de não contatar."); });
  confirmTwice($("#del"), "Confirmar exclusão", async () => { await api("DELETE", `/api/leads/${id}?suppress=1`); toast("Dados excluídos. O telefone ficou na lista de não contatar."); location.hash = "#/"; });
}

function confirmTwice(btn, confirmText, action) {
  const original = btn.textContent;
  let armed = false, timer;
  btn.addEventListener("click", () => {
    if (!armed) { armed = true; btn.textContent = confirmText; timer = setTimeout(() => { armed = false; btn.textContent = original; }, 4000); return; }
    clearTimeout(timer); armed = false; btn.textContent = original;
    run(btn, action);
  });
}

// ------------------------------------------------------------------ tarefas
async function renderTasks() {
  const [overdue, today, open] = await Promise.all([api("GET", "/api/tasks?scope=overdue"), api("GET", "/api/tasks?scope=today"), api("GET", "/api/tasks?scope=open")]);
  const todayOnly = today.items.filter((t) => !overdue.items.some((o) => o.id === t.id));
  const later = open.items.filter((t) => t.due_date > todayISO());
  const list = (items, empty) => items.length ? `<ul class="tasks">${items.map((t) => `<li><input type="checkbox" data-task="${t.id}" aria-label="Concluir ${esc(t.title)}"><span>${esc(t.title)} <a href="#/lead/${t.lead_id}">${esc(t.lead_name)}</a> <span class="small muted">até ${fmtDate(t.due_date, false)}</span></span></li>`).join("")}</ul>` : `<p class="muted small">${empty}</p>`;
  app.innerHTML = `
    <div class="page-head"><h1>Tarefas</h1></div>
    <div class="grid-2">
      <section class="panel"><h2>Atrasadas</h2>${list(overdue.items, "Nada atrasado.")}</section>
      <section class="panel"><h2>Para hoje</h2>${list(todayOnly, "Nenhuma tarefa para hoje.")}</section>
    </div>
    <section class="panel"><h2>Próximas</h2>${list(later, "Nenhuma tarefa futura. Crie tarefas na página de cada empresa.")}</section>`;
  $$("[data-task]").forEach((cb) => cb.addEventListener("change", () => run(cb, async () => { await api("PATCH", `/api/tasks/${cb.dataset.task}`, { done: cb.checked }); toast("Tarefa concluída."); renderTasks(); })));
}

// ------------------------------------------------------------------ resultados
const PLAYBOOK = [
  ["Comece pela empresa, não por você", "A primeira frase fala de algo real deles (nota, avaliações, o que fazem). Mensagem que parece genérica é a principal causa de ninguém responder."],
  ["Primeira mensagem curta, sem link e sem preço", "No WhatsApp e no Instagram, até umas 5 linhas. No e-mail, de 50 a 125 palavras. Link só depois que a pessoa disser que quer ver."],
  ["Peça interesse, não reunião", "“Posso te mandar uma ideia de como ficaria?” é fácil de responder. Numa análise de mais de 300 mil e-mails, esse tipo de pergunta foi o que mais gerou reuniões no primeiro contato."],
  ["Dê algo antes de pedir", "Uma prévia do site deles ou uma ideia concreta (cardápio online, agendamento, página no Google) dá motivo para responder."],
  ["Use o canal que a empresa usa", "WhatsApp publicado no site ou no Instagram, Direct do Instagram, ligação pedindo permissão. E-mail quando a empresa publica um."],
  ["No máximo 2 retornos, sempre com algo novo", "Um follow-up aumenta bastante as respostas; a partir do terceiro, crescem os pedidos para parar. O último encerra com educação."],
  ["Meça antes de concluir", "Compare canais e abordagens só depois de uns 20 contatos em cada. Com menos que isso, a diferença pode ser sorte."],
];

async function renderResults() {
  const ins = await api("GET", "/api/insights");
  const pct = (v) => `${String(v).replace(".", ",")}%`;
  const rate = (r) => `<div class="rate"><span class="bar"><i style="width:${Math.min(100, r.taxa)}%"></i></span><b>${pct(r.taxa)}</b></div>`;
  const small = `<span class="chb" title="Menos de ${ins.amostra_minima} contatos: o número ainda pode mudar muito">poucos dados</span>`;
  const table = (title, col, rows, label = (r) => r.rotulo) => `<section class="panel"><h2>${title}</h2>${rows.length ? `
    <div class="table-wrap"><table><thead><tr><th>${col}</th><th>Contatadas</th><th>Responderam</th><th>Taxa de resposta</th></tr></thead><tbody>
    ${rows.map((r) => `<tr><td>${esc(label(r))} ${r.amostra_pequena ? small : ""}</td><td>${r.contatados}</td><td>${r.responderam}</td><td>${rate(r)}</td></tr>`).join("")}
    </tbody></table></div>` : `<p class="muted small">Sem dados ainda.</p>`}</section>`;
  const attemptName = (n) => n === 1 ? "na primeira mensagem" : n === 2 ? "no primeiro retorno" : n === 3 ? "no segundo retorno" : `na ${n}ª tentativa`;
  const playbook = `<section class="panel"><h2>Como aumentar as respostas</h2>
      <p class="muted small">O que a pesquisa sobre prospecção mostra, já aplicado nas mensagens geradas.</p>
      <ol class="playbook">${PLAYBOOK.map(([t, d]) => `<li><strong>${esc(t)}</strong><br><span class="small muted">${esc(d)}</span></li>`).join("")}</ol></section>`;
  if (!ins.contatados) {
    app.innerHTML = `<div class="page-head"><h1>Resultados</h1><p class="muted">Quais canais e abordagens trazem respostas.</p></div>
      <div class="empty"><h2>Nenhum contato registrado ainda</h2><p>Depois de enviar uma mensagem ou ligar, clique em “Registrar contato feito” na página da empresa. Quando a pessoa responder, registre a resposta. Os números aparecem aqui.</p></div>
      ${playbook}`;
    return;
  }
  app.innerHTML = `
    <div class="page-head"><h1>Resultados</h1><p class="muted">Cada empresa conta uma vez, pelo canal e pela abordagem do primeiro contato. “Respondeu” vale para qualquer resposta registrada depois dele.</p></div>
    <div class="kpis">
      <div class="kpi"><b>${ins.contatados}</b><span>empresas contatadas</span></div>
      <div class="kpi"><b>${ins.responderam}</b><span>responderam (${pct(ins.taxa)})</span></div>
      <div class="kpi"><b>${ins.avancaram}</b><span>chegaram a reunião ou proposta</span></div>
      <div class="kpi"><b>${ins.convertidos}</b><span>fecharam</span></div>
      <div class="kpi"><b>${ins.sem_whatsapp}</b><span>números sem WhatsApp</span></div>
      <div class="kpi"><b>${ins.pediram_para_parar}</b><span>pediram para parar</span></div>
    </div>
    ${ins.contatados < ins.amostra_minima ? `<p class="banner">Ainda são poucos contatos (${ins.contatados}). Use os números como pista, não como conclusão.</p>` : ""}
    <div class="results-grid">
      ${table("Por canal", "Canal", ins.por_canal)}
      ${table("Por abordagem", "Abordagem da 1ª mensagem", ins.por_abordagem)}
      ${table("Por segmento", "Segmento", ins.por_segmento)}
      ${table("Por presença digital", "Presença", ins.por_presenca, (r) => PRESENCE_SHORT[r.chave] || r.chave)}
      ${ins.por_pais.length > 1 ? table("Por país", "País", ins.por_pais, (r) => countryName(r.chave)) : ""}
      <section class="panel"><h2>Quando responderam</h2>${ins.resposta_por_tentativa.length ? `<ul class="facts">${ins.resposta_por_tentativa.map((a) => `<li>${a.respostas} ${a.respostas === 1 ? "resposta" : "respostas"} ${attemptName(a.tentativa)}</li>`).join("")}</ul>
        <p class="small muted">Se muitas respostas vêm no retorno, vale manter o follow-up. Mais de 2 retornos raramente compensa.</p>` : `<p class="muted small">Nenhuma resposta registrada ainda.</p>`}</section>
    </div>
    ${playbook}`;
}

// ------------------------------------------------------------------ histórico de pesquisas
async function renderJobs() {
  const data = await api("GET", "/api/searches?limit=50");
  app.innerHTML = `
    <div class="page-head"><h1>Pesquisas</h1><p class="muted">Histórico de execuções, com o que foi encontrado, descartado e quantas chamadas ao Google cada uma usou.</p></div>
    <div class="table-wrap">${data.items.length ? `<table><thead><tr><th>Nº</th><th>Pesquisa</th><th>Situação</th><th>Resultado</th><th>Google</th><th>Quando</th></tr></thead><tbody>
      ${data.items.map((j) => {
        const p = j.params || {};
        const name = p.kind === "analise" ? (p.origem === "reanalise" ? "Atualização de contatos e diagnósticos" : "Análise de planilha") : `${esc(p.segment)} em ${esc(p.city)}${p.state ? " - " + esc(p.state) : ""}${(p.regions || []).length ? ` (${esc(p.regions.join(", "))})` : ""}`;
        return `<tr><td>${j.id}</td><td>${name}<div class="co-meta">${esc(j.actor)}</div></td><td>${esc(JOB_STATUS[j.status] || j.status)}${j.error ? `<div class="co-meta" style="color:var(--alert)">${esc(j.error)}</div>` : ""}</td>
          <td>${j.found} encontradas, ${j.saved_new} novas, ${j.high_priority} alta prioridade<div class="co-meta">${esc(Object.entries(j.discard_reasons || {}).map(([k, v]) => `${v} ${DISCARD[k] || k}`).join(", "))}</div></td>
          <td>${j.api_calls}</td><td class="small">${fmtDate(j.created_at)}</td></tr>`;
      }).join("")}</tbody></table>` : `<div class="empty"><h2>Nenhuma pesquisa ainda</h2><p>As pesquisas feitas na tela de leads aparecem aqui.</p></div>`}</div>`;
}

// ------------------------------------------------------------------ lista de supressão
async function renderSuppression() {
  const data = await api("GET", "/api/suppression");
  const isAdmin = state.meta.voce.escopos.includes("admin");
  const KIND = { phone: "Telefone", place_id: "Google (place_id)", domain: "Domínio" };
  app.innerHTML = `
    <div class="page-head"><h1>Não contatar</h1>
      <p class="muted">Empresas que pediram para não receber mensagens ou foram excluídas. Novas pesquisas e importações ignoram esses registros, e o envio fica bloqueado.</p></div>
    <section class="panel">
      <h2>Adicionar</h2>
      <form id="sup-form" class="form-grid">
        <div><label for="s-kind">Tipo</label><select id="s-kind" name="kind"><option value="phone">Telefone</option><option value="domain">Domínio do site</option><option value="place_id">place_id do Google</option></select></div>
        <div><label for="s-val">Valor</label><input id="s-val" type="text" name="value" required minlength="3" maxlength="200" placeholder="(41) 99999-9999"></div>
        <div><label for="s-country">País do telefone</label><select id="s-country" name="country">${state.meta.countries.map((c) => `<option value="${c.code}">${esc(c.name)}</option>`).join("")}</select></div>
        <div><label for="s-reason">Motivo</label><input id="s-reason" type="text" name="reason" maxlength="300" placeholder="Pediu para não ser contatado"></div>
        <div><button type="submit">Adicionar</button></div>
      </form>
    </section>
    <div class="table-wrap">${data.items.length ? `<table><thead><tr><th>Tipo</th><th>Valor</th><th>Motivo</th><th>Quando</th><th></th></tr></thead><tbody>
      ${data.items.map((s) => `<tr><td>${esc(KIND[s.kind] || s.kind)}</td><td class="mono">${esc(s.value)}</td><td>${esc(s.reason || "")}<div class="co-meta">${esc(s.actor)}</div></td><td class="small">${fmtDate(s.created_at)}</td>
        <td>${isAdmin ? `<button class="btn-small btn-danger" data-sup="${s.id}" type="button">Remover</button>` : ""}</td></tr>`).join("")}</tbody></table>`
      : `<div class="empty"><h2>Lista vazia</h2><p>Quando alguém pedir para não ser contatado, registre no histórico da empresa: ela entra aqui automaticamente.</p></div>`}</div>`;
  $("#sup-form").addEventListener("submit", (e) => { e.preventDefault(); run($("button", e.target), async () => {
    const fd = new FormData(e.target);
    await api("POST", "/api/suppression", { kind: fd.get("kind"), value: fd.get("value"), reason: fd.get("reason"), country: fd.get("country") });
    toast("Adicionado à lista."); renderSuppression();
  }); });
  $$("[data-sup]").forEach((b) => confirmTwice(b, "Confirmar remoção", async () => { await api("DELETE", `/api/suppression/${b.dataset.sup}`); toast("Removido."); renderSuppression(); }));
}

// ------------------------------------------------------------------ configurações
async function renderSettings() {
  const s = await api("GET", "/api/settings");
  const isAdmin = state.meta.voce.escopos.includes("admin");
  const sc = s.scoring_efetivo;
  const num = (name, value, min, max, label) => `<div><label for="${name}">${esc(label)}</label><input id="${name}" name="${name}" type="number" min="${min}" max="${max}" value="${value}" ${isAdmin ? "" : "disabled"}></div>`;
  const days = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"];
  const usage = state.meta.uso_google_mes || {};
  app.innerHTML = `
    <div class="page-head"><h1>Configurações</h1>${isAdmin ? `<a href="#/auditoria" class="small">Ver registro de operações</a>` : ""}</div>
    <div class="grid-2">
      <section class="panel"><h2>Seu perfil nas mensagens</h2><p class="muted small">Usado na apresentação das mensagens.</p>
        <form id="seller" class="form-grid">
          <div><label for="s-nome">Nome completo</label><input id="s-nome" type="text" name="nome" value="${esc(s.seller.nome)}" required></div>
          <div><label for="s-pn">Como se apresenta</label><input id="s-pn" type="text" name="primeiro_nome" value="${esc(s.seller.primeiro_nome)}" required></div>
          <div><label for="s-exp">Experiência</label><input id="s-exp" type="text" name="experiencia" value="${esc(s.seller.experiencia)}" placeholder="há mais de 3 anos"></div>
          <div><label for="s-exp-en">Experiência (inglês)</label><input id="s-exp-en" type="text" name="experiencia_en" value="${esc(s.seller.experiencia_en || "")}" placeholder="for over 3 years"></div>
          <div><label for="s-emp">Empresa (opcional)</label><input id="s-emp" type="text" name="empresa" value="${esc(s.seller.empresa)}"></div>
          <div><label for="s-wa">Seu WhatsApp (assinatura do e-mail)</label><input id="s-wa" type="text" name="whatsapp" maxlength="40" value="${esc(s.seller.whatsapp || "")}" placeholder="(41) 99999-9999"></div>
          <div class="full"><label for="s-port">Link do portfólio (assinatura do e-mail)</label><input id="s-port" type="url" name="portfolio" maxlength="200" value="${esc(s.seller.portfolio || "")}" placeholder="https://"></div>
          <div class="full"><label for="s-end">Endereço comercial (obrigatório em e-mails para EUA e Canadá)</label><input id="s-end" type="text" name="endereco" maxlength="200" value="${esc(s.seller.endereco || "")}" placeholder="Cidade - UF, ou endereço completo"></div>
          <div><button type="submit" ${isAdmin ? "" : "disabled"}>Salvar perfil</button></div>
        </form></section>
      <section class="panel"><h2>Política de contato</h2><p class="muted small">Limites que protegem sua reputação e seu número.</p>
        <form id="policy" class="form-grid">
          ${num("daily_limit", s.contact_policy.daily_limit, 1, 200, "Contatos por dia")}
          ${num("min_days_between_contacts", s.contact_policy.min_days_between_contacts, 1, 60, "Dias entre tentativas")}
          ${num("max_unanswered_attempts", s.contact_policy.max_unanswered_attempts, 1, 5, "Tentativas sem resposta")}
          ${num("h_start", s.contact_policy.business_hours[0], 0, 23, "Início do horário")}
          ${num("h_end", s.contact_policy.business_hours[1], 1, 24, "Fim do horário")}
          <div class="full"><label>Dias de contato</label><div style="display:flex;gap:12px;flex-wrap:wrap">${days.map((d, i) => `<label class="check"><input type="checkbox" name="day" value="${i}" ${s.contact_policy.business_days.includes(i) ? "checked" : ""}> ${d}</label>`).join("")}</div></div>
          <div><button type="submit" ${isAdmin ? "" : "disabled"}>Salvar política</button></div>
        </form></section>
    </div>
    <section class="panel"><h2>Pontuação</h2><p class="muted small">Ao salvar, todos os leads são pontuados de novo.</p>
      <form id="scoring" class="stack">
        <div class="form-grid">
          ${num("th_alta", sc.thresholds.alta, 1, 100, "Prioridade alta a partir de")}
          ${num("th_media", sc.thresholds.media, 1, 99, "Prioridade média a partir de")}
          ${num("pr_sem_site", sc.presence.sem_site, 0, 100, "Sem site")}
          ${num("pr_rede_social", sc.presence.rede_social, 0, 100, "Só rede social")}
          ${num("pr_agregador_links", sc.presence.agregador_links, 0, 100, "Agregador de links")}
          ${num("pr_plataforma_terceiros", sc.presence.plataforma_terceiros, 0, 100, "Plataforma de terceiros")}
          ${num("pr_google_descontinuado", sc.presence.google_descontinuado, 0, 100, "Site do Google descontinuado")}
          ${num("site_issue_cap", sc.site_issue_cap, 0, 100, "Máximo por problemas no site")}
          ${num("ct_telefone", sc.contact.telefone, 0, 100, "Tem telefone")}
          ${num("ct_celular", sc.contact.celular, 0, 100, "É celular")}
        </div>
        <details class="more"><summary>Avançado: todos os pesos (JSON)</summary>
          <textarea id="scoring-json" rows="14" class="mono" ${isAdmin ? "" : "disabled"}>${esc(JSON.stringify(sc, null, 2))}</textarea>
          <p class="small muted">Se você editar o JSON, ele tem prioridade sobre os campos acima.</p></details>
        <div><button type="submit" ${isAdmin ? "" : "disabled"}>Salvar e repontuar</button></div>
      </form></section>
    <div class="grid-2">
      <section class="panel"><h2>Automação</h2>
        <form id="pipeline" class="stack">
          <div><label for="p-auto">Gerar mensagem automaticamente após a pesquisa para</label>
            <select id="p-auto" name="auto_message_min_priority" ${isAdmin ? "" : "disabled"}>
              ${[["alta", "Prioridade alta"], ["media", "Prioridade média ou alta"], ["baixa", "Todos os leads"], ["nenhuma", "Nenhum (só manual)"]].map(([k, v]) => `<option value="${k}" ${s.pipeline.auto_message_min_priority === k ? "selected" : ""}>${v}</option>`).join("")}</select></div>
          <label class="check"><input type="checkbox" name="analyze_sites" ${s.pipeline.analyze_sites ? "checked" : ""} ${isAdmin ? "" : "disabled"}> Visitar a página inicial dos sites para o diagnóstico</label>
          <p class="small muted">Mensagens automáticas são sempre rascunhos: nada é enviado sem você.</p>
          <div><button type="submit" ${isAdmin ? "" : "disabled"}>Salvar</button></div>
        </form>
        <h3 style="margin-top:18px">Contatos dos leads já salvos</h3>
        <p class="small muted">Visita de novo o site e a página de links de cada lead em andamento para achar WhatsApp, e-mail e Instagram publicados pela empresa. Não usa a cota do Google.</p>
        <button class="btn-small" id="reanalyze" type="button" ${isAdmin ? "" : "disabled"}>Atualizar contatos de todos os leads</button>
        <p class="small" id="reanalyze-out"></p></section>
      <section class="panel"><h2>Google Places</h2>
        <p class="small">${state.meta.google_configurado ? "Chave configurada." : "Chave não configurada (GOOGLE_PLACES_API_KEY)."} Este mês: ${usage.text_search_enterprise || 0} de ${state.meta.limites_google.text_search_enterprise} pesquisas e ${usage.place_details_enterprise || 0} de ${state.meta.limites_google.place_details_enterprise} atualizações.</p>
        <p class="small muted">Pelas regras do Google, os dados (exceto o identificador do lugar) devem ser atualizados ou removidos após ${state.meta.cache_google_dias} dias.</p>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <button class="btn-small" id="cache-report" type="button" ${isAdmin ? "" : "disabled"}>Verificar dados expirados</button>
          <button class="btn-small" id="cache-refresh" type="button" ${isAdmin ? "" : "disabled"}>Atualizar ativos e limpar o resto</button>
        </div>
        <p class="small" id="cache-out"></p>
        <h3 style="margin-top:14px">IA</h3>
        <p class="small">${state.meta.ia_configurada ? `Ativa (${esc(state.meta.modelo_ia)}).` : "Desativada. Para usar, coloque ANTHROPIC_API_KEY no .env. Sem IA, as mensagens usam modelos próprios."}</p>
      </section>
    </div>
    <p class="small muted">Listas de cidades: municípios do IBGE (via kelvins/municipios-brasileiros, licença MIT) e cidades do
      <a href="https://www.geonames.org/" target="_blank" rel="noopener noreferrer">GeoNames</a> (licença CC BY 4.0, via datasets/world-cities).</p>`;

  const save = async (payload, btn, msgText) => run(btn, async () => { await api("PUT", "/api/settings", payload); toast(msgText); renderSettings(); });
  $("#seller").addEventListener("submit", (e) => { e.preventDefault(); const fd = new FormData(e.target); save({ seller: Object.fromEntries(fd) }, $("button", e.target), "Perfil salvo."); });
  $("#policy").addEventListener("submit", (e) => {
    e.preventDefault(); const fd = new FormData(e.target);
    save({ contact_policy: { daily_limit: +fd.get("daily_limit"), min_days_between_contacts: +fd.get("min_days_between_contacts"), max_unanswered_attempts: +fd.get("max_unanswered_attempts"),
      business_hours: [+fd.get("h_start"), +fd.get("h_end")], business_days: fd.getAll("day").map(Number) } }, $("button", e.target), "Política salva.");
  });
  $("#pipeline").addEventListener("submit", (e) => { e.preventDefault(); const fd = new FormData(e.target); save({ pipeline: { auto_message_min_priority: fd.get("auto_message_min_priority"), analyze_sites: !!fd.get("analyze_sites") } }, $("button", e.target), "Automação salva."); });
  const original = JSON.stringify(sc, null, 2);
  $("#scoring").addEventListener("submit", (e) => {
    e.preventDefault(); const fd = new FormData(e.target);
    let cfg;
    const raw = $("#scoring-json").value;
    if (raw.trim() !== original.trim()) {
      try { cfg = JSON.parse(raw); } catch { toast("JSON inválido na configuração avançada.", true); return; }
    } else {
      cfg = JSON.parse(original);
      cfg.thresholds = { alta: +fd.get("th_alta"), media: +fd.get("th_media") };
      for (const k of ["sem_site", "rede_social", "agregador_links", "plataforma_terceiros", "google_descontinuado"]) cfg.presence[k] = +fd.get("pr_" + k);
      cfg.presence.whatsapp = cfg.presence.rede_social;
      cfg.site_issue_cap = +fd.get("site_issue_cap");
      cfg.contact = { ...cfg.contact, telefone: +fd.get("ct_telefone"), celular: +fd.get("ct_celular") };
    }
    save({ scoring: cfg }, $("button[type=submit]", e.target), "Pontuação salva e leads repontuados.");
  });
  const cache = async (mode, btn) => run(btn, async () => {
    const r = await api("POST", "/api/maintenance/google-cache", { mode });
    $("#cache-out").textContent = mode === "report" ? `${r.expirados} lead(s) com dados do Google com mais de ${r.prazo_dias} dias.` : `${r.atualizados} atualizado(s), ${r.removidos} limpo(s).${r.erros.length ? " Erros: " + r.erros.join("; ") : ""}`;
  });
  $("#cache-report").addEventListener("click", (e) => cache("report", e.currentTarget));
  confirmTwice($("#cache-refresh"), "Confirmar (usa a cota do Google)", () => cache("refresh", $("#cache-refresh")));
  confirmTwice($("#reanalyze"), "Confirmar atualização", async () => {
    const job = await api("POST", "/api/maintenance/reanalyze");
    $("#reanalyze-out").innerHTML = `Na fila: ${job.params.lead_ids.length} lead(s). Acompanhe em <a href="#/pesquisas">Pesquisas</a>.`;
  });
}

async function renderAudit() {
  const data = await api("GET", "/api/audit?limit=300");
  app.innerHTML = `
    <a class="back" href="#/config">Voltar para Configurações</a>
    <div class="page-head"><h1>Registro de operações</h1><p class="muted">Alterações feitas por você e todas as chamadas feitas por tokens de integração (como o Claude).</p></div>
    <div class="table-wrap"><table><thead><tr><th>Quando</th><th>Quem</th><th>Operação</th><th>Resultado</th></tr></thead><tbody>
      ${data.items.map((a) => `<tr><td class="small">${fmtDate(a.at)}</td><td>${esc(a.actor)}</td><td class="mono">${esc(a.method)} ${esc(a.path)}${a.detail ? `<div class="co-meta">${esc(a.detail)}</div>` : ""}</td><td>${a.status}</td></tr>`).join("")}
    </tbody></table></div>`;
}

router();
