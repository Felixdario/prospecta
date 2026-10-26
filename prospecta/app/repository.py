"""Acesso aos dados. Todo SQL do sistema fica aqui."""
from __future__ import annotations

import copy
import hashlib
import hmac
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from .db import Database, dumps, loads, utcnow
from .phones import normalize_br_phone
from .pipeline import DEFAULT_CONTACT_POLICY
from .site_analysis import classify_url

JSON_FIELDS = ("opening_hours", "social_links", "site_analysis", "score_breakdown", "analysis", "message_warnings")
GOOGLE_FIELDS = ("name", "category", "primary_type", "address", "neighborhood", "city", "state", "phone", "phone_e164",
                 "phone_kind", "website", "maps_url", "rating", "reviews_count", "opening_hours", "business_status")
EDITABLE_FIELDS = ("name", "category", "segment", "address", "neighborhood", "city", "state", "phone", "website",
                   "notes", "responsible_name", "preview_ready", "preview_url", "suggested_message")

DEFAULT_SETTINGS: dict[str, Any] = {
    "seller": {"nome": "Eduardo Felix", "primeiro_nome": "Eduardo", "experiencia": "há mais de 3 anos", "empresa": ""},
    "contact_policy": dict(DEFAULT_CONTACT_POLICY),
    "pipeline": {"auto_message_min_priority": "alta", "analyze_sites": True},
    "scoring": {},
}

ALL_SCOPES = ("admin", "leads:read", "leads:write", "search:run", "export", "contacts:record")


class NotFound(Exception):
    pass


def lead_from_row(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    d = dict(row)
    for f in JSON_FIELDS:
        d[f] = loads(d.get(f))
    d["preview_ready"] = bool(d.get("preview_ready"))
    d["google_content_purged"] = bool(d.get("google_content_purged"))
    return d


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _month(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).strftime("%Y-%m")


class Repo:
    def __init__(self, db: Database):
        self.db = db

    # ------------------------------------------------------------------ leads
    def _find_existing(self, conn, data: dict) -> sqlite3.Row | None:
        if data.get("place_id"):
            row = conn.execute("SELECT * FROM leads WHERE place_id = ?", (data["place_id"],)).fetchone()
            if row:
                return row
        if data.get("phone_e164"):
            row = conn.execute("SELECT * FROM leads WHERE phone_e164 = ? ORDER BY id LIMIT 1", (data["phone_e164"],)).fetchone()
            if row:
                return row
        if data.get("name") and data.get("city"):
            return conn.execute(
                "SELECT * FROM leads WHERE lower(name) = lower(?) AND lower(coalesce(city,'')) = lower(?) LIMIT 1",
                (data["name"], data["city"]),
            ).fetchone()
        return None

    def upsert_lead(self, data: dict, source: str, actor: str, search_id: int | None = None,
                    website_known: bool = True) -> tuple[int, bool]:
        """Insere ou atualiza um lead, evitando duplicatas por place_id, telefone ou nome+cidade.
        Nunca altera status, histórico ou anotações de um lead existente."""
        now = utcnow()
        data = {k: v for k, v in data.items() if k in GOOGLE_FIELDS + ("place_id", "segment")}
        phone = normalize_br_phone(data.get("phone"))
        if phone:
            data["phone"] = phone.display()
            data["phone_e164"] = phone.e164
            data["phone_kind"] = phone.kind
        if "opening_hours" in data:
            data["opening_hours"] = dumps(data["opening_hours"])
        with self.db.tx() as conn:
            existing = self._find_existing(conn, data)
            if existing:
                updates = {k: v for k, v in data.items() if v is not None}
                if existing["place_id"] and updates.get("place_id") and updates["place_id"] != existing["place_id"]:
                    updates.pop("place_id")
                if "website" in updates and updates["website"] != existing["website"]:
                    updates.update({"site_analysis": None, "site_analyzed_at": None, "presence_kind": None})
                if existing["segment"]:
                    updates.pop("segment", None)
                updates["last_seen_at"] = now
                updates["updated_at"] = now
                if source == "google_places":
                    updates["google_fetched_at"] = now
                    updates["google_content_purged"] = 0
                cols = ", ".join(f"{k} = ?" for k in updates)
                conn.execute(f"UPDATE leads SET {cols} WHERE id = ?", (*updates.values(), existing["id"]))
                return existing["id"], False
            row = dict(data)
            if not website_known and not row.get("website"):
                row["site_analysis"] = dumps({"kind": "desconhecido", "kind_label": "Presença digital desconhecida", "issues": []})
                row["presence_kind"] = "desconhecido"
            elif not row.get("website"):
                row["presence_kind"] = "sem_site"
            row.update({
                "source": source, "status": "identificado", "first_search_id": search_id,
                "first_seen_at": now, "last_seen_at": now, "created_at": now, "updated_at": now,
                "google_fetched_at": now if source == "google_places" else None,
            })
            cols = ", ".join(row)
            cur = conn.execute(f"INSERT INTO leads ({cols}) VALUES ({', '.join('?' * len(row))})", tuple(row.values()))
            lead_id = cur.lastrowid
            origin = {"google_places": "Google Places API", "csv_importacao": "importação de planilha", "manual": "cadastro manual", "demo": "dados fictícios de demonstração"}.get(source, source)
            self._event(conn, lead_id, actor, "coleta", f"Lead coletado via {origin}", details={"search_id": search_id})
            return lead_id, True

    def get_lead(self, lead_id: int) -> dict:
        with self.db.read() as conn:
            lead = lead_from_row(conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone())
        if not lead:
            raise NotFound(f"Lead {lead_id} não encontrado")
        return lead

    def get_lead_by_place(self, place_id: str) -> dict | None:
        with self.db.read() as conn:
            return lead_from_row(conn.execute("SELECT * FROM leads WHERE place_id = ?", (place_id,)).fetchone())

    def update_lead(self, lead_id: int, fields: dict) -> None:
        if not fields:
            return
        fields = dict(fields)
        for f in JSON_FIELDS:
            if f in fields and not isinstance(fields[f], str):
                fields[f] = dumps(fields[f])
        if "preview_ready" in fields:
            fields["preview_ready"] = 1 if fields["preview_ready"] else 0
        if "phone" in fields:
            phone = normalize_br_phone(fields["phone"])
            fields["phone"] = phone.display() if phone else None
            fields["phone_e164"] = phone.e164 if phone else None
            fields["phone_kind"] = phone.kind if phone else None
        if "website" in fields:
            fields.update({"site_analysis": None, "site_analyzed_at": None,
                           "presence_kind": "sem_site" if not fields["website"] else None})
        fields["updated_at"] = utcnow()
        cols = ", ".join(f"{k} = ?" for k in fields)
        with self.db.tx() as conn:
            cur = conn.execute(f"UPDATE leads SET {cols} WHERE id = ?", (*fields.values(), lead_id))
            if cur.rowcount == 0:
                raise NotFound(f"Lead {lead_id} não encontrado")

    def delete_lead(self, lead_id: int) -> dict:
        lead = self.get_lead(lead_id)
        with self.db.tx() as conn:
            conn.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
        return lead

    def list_leads(self, f: dict) -> tuple[list[dict], int]:
        where, args = ["1=1"], []
        if f.get("q"):
            where.append("(name LIKE ? OR category LIKE ? OR city LIKE ? OR neighborhood LIKE ? OR phone LIKE ? OR notes LIKE ?)")
            args += [f"%{f['q']}%"] * 6
        for key, col in (("status", "status"), ("priority", "priority"), ("segment", "segment"), ("source", "source"), ("presence", "presence_kind")):
            if f.get(key):
                values = [v for v in str(f[key]).split(",") if v]
                if key == "presence" and "com_site" in values:
                    values = [v for v in values if v != "com_site"] + ["proprio"]
                if key == "presence" and "limitada" in values:
                    values = [v for v in values if v != "limitada"] + ["rede_social", "whatsapp", "agregador_links", "plataforma_terceiros", "google_descontinuado"]
                where.append(f"{col} IN ({', '.join('?' * len(values))})")
                args += values
        if f.get("city"):
            where.append("lower(city) = lower(?)")
            args.append(f["city"])
        if f.get("min_score") not in (None, ""):
            where.append("coalesce(score, 0) >= ?")
            args.append(int(f["min_score"]))
        if f.get("has_phone"):
            where.append("phone_e164 IS NOT NULL")
        if f.get("search_id"):
            where.append("id IN (SELECT lead_id FROM search_results WHERE search_id = ?)")
            args.append(int(f["search_id"]))
        order = {
            "score": "score IS NULL, score DESC, reviews_count DESC",
            "recent": "created_at DESC",
            "name": "name COLLATE NOCASE",
            "updated": "updated_at DESC",
            "reviews": "reviews_count IS NULL, reviews_count DESC",
        }.get(f.get("sort") or "score", "score IS NULL, score DESC")
        page = max(1, int(f.get("page") or 1))
        size = max(1, min(500, int(f.get("page_size") or 50)))
        sql_where = " AND ".join(where)
        cols = ("id, place_id, source, name, category, segment, neighborhood, city, state, phone, phone_kind, phone_e164, website, "
                "maps_url, rating, reviews_count, presence_kind, score, priority, status, consent_status, last_contact_at, "
                "contact_count, suggested_message IS NOT NULL AS has_message, google_content_purged, created_at, updated_at")
        with self.db.read() as conn:
            total = conn.execute(f"SELECT count(*) FROM leads WHERE {sql_where}", args).fetchone()[0]
            rows = conn.execute(f"SELECT {cols} FROM leads WHERE {sql_where} ORDER BY {order} LIMIT ? OFFSET ?",
                                (*args, size, (page - 1) * size)).fetchall()
        return [dict(r) for r in rows], total

    def iter_leads_for_export(self, f: dict) -> list[dict]:
        f = dict(f, page=1, page_size=500)
        out, page = [], 1
        while True:
            items, total = self.list_leads(dict(f, page=page))
            ids = [i["id"] for i in items]
            if ids:
                with self.db.read() as conn:
                    rows = conn.execute(f"SELECT * FROM leads WHERE id IN ({', '.join('?' * len(ids))})", ids).fetchall()
                by_id = {r["id"]: lead_from_row(r) for r in rows}
                out += [by_id[i] for i in ids]
            if page * 500 >= total:
                return out
            page += 1

    def stats(self) -> dict:
        with self.db.read() as conn:
            by_status = {r[0]: r[1] for r in conn.execute("SELECT status, count(*) FROM leads GROUP BY status")}
            by_priority = {r[0] or "sem_pontuacao": r[1] for r in conn.execute("SELECT priority, count(*) FROM leads GROUP BY priority")}
            total = conn.execute("SELECT count(*) FROM leads").fetchone()[0]
            no_site = conn.execute("SELECT count(*) FROM leads WHERE presence_kind = 'sem_site'").fetchone()[0]
        return {"total": total, "by_status": by_status, "by_priority": by_priority, "sem_site": no_site}

    # ------------------------------------------------------------------ eventos
    def _event(self, conn, lead_id: int, actor: str, type_: str, summary: str, channel: str | None = None, details: Any = None) -> int:
        cur = conn.execute(
            "INSERT INTO lead_events (lead_id, created_at, actor, type, channel, summary, details) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (lead_id, utcnow(), actor, type_, channel, summary, dumps(details)),
        )
        return cur.lastrowid

    def add_event(self, lead_id: int, actor: str, type_: str, summary: str, channel: str | None = None,
                  details: Any = None, lead_updates: dict | None = None) -> int:
        with self.db.tx() as conn:
            if not conn.execute("SELECT 1 FROM leads WHERE id = ?", (lead_id,)).fetchone():
                raise NotFound(f"Lead {lead_id} não encontrado")
            event_id = self._event(conn, lead_id, actor, type_, summary, channel, details)
            if lead_updates:
                lead_updates = dict(lead_updates, updated_at=utcnow())
                cols = ", ".join(f"{k} = ?" for k in lead_updates)
                conn.execute(f"UPDATE leads SET {cols} WHERE id = ?", (*lead_updates.values(), lead_id))
            if type_ == "mensagem_enviada":
                conn.execute("UPDATE leads SET contact_count = contact_count + 1, last_contact_at = ? WHERE id = ?", (utcnow(), lead_id))
            return event_id

    def events(self, lead_id: int) -> list[dict]:
        with self.db.read() as conn:
            rows = conn.execute("SELECT * FROM lead_events WHERE lead_id = ? ORDER BY created_at DESC, id DESC", (lead_id,)).fetchall()
        return [dict(r, details=loads(r["details"])) for r in rows]

    def sent_today(self, tz: str) -> int:
        local_midnight = datetime.now(ZoneInfo(tz)).replace(hour=0, minute=0, second=0, microsecond=0)
        since = local_midnight.astimezone(timezone.utc).replace(microsecond=0).isoformat()
        with self.db.read() as conn:
            return conn.execute("SELECT count(*) FROM lead_events WHERE type = 'mensagem_enviada' AND created_at >= ?", (since,)).fetchone()[0]

    def phone_contacted_elsewhere(self, phone_e164: str | None, lead_id: int, days: int) -> int:
        if not phone_e164:
            return 0
        since = (datetime.now(timezone.utc) - timedelta(days=days)).replace(microsecond=0).isoformat()
        with self.db.read() as conn:
            return conn.execute(
                "SELECT count(*) FROM lead_events e JOIN leads l ON l.id = e.lead_id "
                "WHERE e.type = 'mensagem_enviada' AND l.phone_e164 = ? AND l.id != ? AND e.created_at >= ?",
                (phone_e164, lead_id, since),
            ).fetchone()[0]

    # ------------------------------------------------------------------ tarefas
    def create_task(self, lead_id: int, title: str, due_date: str, actor: str) -> int:
        with self.db.tx() as conn:
            if not conn.execute("SELECT 1 FROM leads WHERE id = ?", (lead_id,)).fetchone():
                raise NotFound(f"Lead {lead_id} não encontrado")
            cur = conn.execute("INSERT INTO tasks (lead_id, title, due_date, actor, created_at) VALUES (?, ?, ?, ?, ?)",
                               (lead_id, title, due_date, actor, utcnow()))
            self._event(conn, lead_id, actor, "nota", f"Tarefa criada: {title} (até {due_date})")
            return cur.lastrowid

    def list_tasks(self, lead_id: int | None = None, scope: str = "open", today: str | None = None) -> list[dict]:
        where, args = [], []
        if lead_id:
            where.append("t.lead_id = ?")
            args.append(lead_id)
        if scope == "open":
            where.append("t.done = 0")
        elif scope in ("today", "overdue"):
            where.append("t.done = 0 AND t.due_date <= ?" if scope == "today" else "t.done = 0 AND t.due_date < ?")
            args.append(today)
        sql = ("SELECT t.*, l.name AS lead_name, l.status AS lead_status FROM tasks t JOIN leads l ON l.id = t.lead_id"
               + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY t.done, t.due_date, t.id")
        with self.db.read() as conn:
            return [dict(r) for r in conn.execute(sql, args).fetchall()]

    def set_task_done(self, task_id: int, done: bool, actor: str) -> dict:
        with self.db.tx() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if not row:
                raise NotFound(f"Tarefa {task_id} não encontrada")
            conn.execute("UPDATE tasks SET done = ?, done_at = ? WHERE id = ?", (1 if done else 0, utcnow() if done else None, task_id))
            if done:
                self._event(conn, row["lead_id"], actor, "nota", f"Tarefa concluída: {row['title']}")
            return dict(row, done=1 if done else 0)

    # ------------------------------------------------------------------ supressão
    def add_suppression(self, kind: str, value: str, reason: str, actor: str) -> None:
        if kind not in ("phone", "place_id", "domain"):
            raise ValueError("Tipo de supressão inválido")
        if kind == "phone":
            p = normalize_br_phone(value)
            value = p.e164 if p and p.e164 else value
        if kind == "domain":
            value = value.lower().removeprefix("http://").removeprefix("https://").removeprefix("www.").split("/")[0]
        with self.db.tx() as conn:
            conn.execute("INSERT OR IGNORE INTO suppression (kind, value, reason, actor, created_at) VALUES (?, ?, ?, ?, ?)",
                         (kind, value, reason, actor, utcnow()))

    def suppress_lead(self, lead: dict, reason: str, actor: str) -> None:
        if lead.get("phone_e164"):
            self.add_suppression("phone", lead["phone_e164"], reason, actor)
        if lead.get("place_id"):
            self.add_suppression("place_id", lead["place_id"], reason, actor)

    def list_suppression(self) -> list[dict]:
        with self.db.read() as conn:
            return [dict(r) for r in conn.execute("SELECT * FROM suppression ORDER BY created_at DESC").fetchall()]

    def remove_suppression(self, sup_id: int) -> None:
        with self.db.tx() as conn:
            if conn.execute("DELETE FROM suppression WHERE id = ?", (sup_id,)).rowcount == 0:
                raise NotFound("Registro de supressão não encontrado")

    def suppression_matches(self, lead: dict) -> list[dict]:
        checks = []
        if lead.get("phone_e164"):
            checks.append(("phone", lead["phone_e164"]))
        if lead.get("place_id"):
            checks.append(("place_id", lead["place_id"]))
        if lead.get("website"):
            host = lead["website"].lower().removeprefix("http://").removeprefix("https://").removeprefix("www.").split("/")[0]
            checks.append(("domain", host))
        if not checks:
            return []
        clause = " OR ".join("(kind = ? AND value = ?)" for _ in checks)
        with self.db.read() as conn:
            return [dict(r) for r in conn.execute(f"SELECT * FROM suppression WHERE {clause}", [x for c in checks for x in c]).fetchall()]

    # ------------------------------------------------------------------ pesquisas
    def create_job(self, params: dict, actor: str) -> int:
        with self.db.tx() as conn:
            return conn.execute("INSERT INTO search_jobs (status, params, actor, created_at, stage) VALUES ('na_fila', ?, ?, ?, 'Na fila')",
                                (dumps(params), actor, utcnow())).lastrowid

    def link_search_result(self, search_id: int, lead_id: int, is_new: bool) -> None:
        with self.db.tx() as conn:
            conn.execute("INSERT OR IGNORE INTO search_results (search_id, lead_id, is_new) VALUES (?, ?, ?)",
                         (search_id, lead_id, 1 if is_new else 0))

    def claim_next_job(self) -> dict | None:
        with self.db.tx() as conn:
            row = conn.execute("SELECT * FROM search_jobs WHERE status = 'na_fila' ORDER BY id LIMIT 1").fetchone()
            if not row:
                return None
            conn.execute("UPDATE search_jobs SET status = 'executando', started_at = ?, stage = 'Iniciando' WHERE id = ?", (utcnow(), row["id"]))
        return self.get_job(row["id"])

    def get_job(self, job_id: int) -> dict:
        with self.db.read() as conn:
            row = conn.execute("SELECT * FROM search_jobs WHERE id = ?", (job_id,)).fetchone()
        if not row:
            raise NotFound(f"Pesquisa {job_id} não encontrada")
        return dict(row, params=loads(row["params"], {}), discard_reasons=loads(row["discard_reasons"], {}))

    def list_jobs(self, limit: int = 20) -> list[dict]:
        with self.db.read() as conn:
            rows = conn.execute("SELECT * FROM search_jobs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r, params=loads(r["params"], {}), discard_reasons=loads(r["discard_reasons"], {})) for r in rows]

    def update_job(self, job_id: int, **fields) -> None:
        if "discard_reasons" in fields:
            fields["discard_reasons"] = dumps(fields["discard_reasons"])
        cols = ", ".join(f"{k} = ?" for k in fields)
        with self.db.tx() as conn:
            conn.execute(f"UPDATE search_jobs SET {cols} WHERE id = ?", (*fields.values(), job_id))

    def job_cancel_requested(self, job_id: int) -> bool:
        with self.db.read() as conn:
            return bool(conn.execute("SELECT cancel_requested FROM search_jobs WHERE id = ?", (job_id,)).fetchone()[0])

    def mark_interrupted_jobs(self) -> int:
        with self.db.tx() as conn:
            return conn.execute(
                "UPDATE search_jobs SET status = 'interrompida', finished_at = ?, error = 'Servidor reiniciado durante a execução' WHERE status = 'executando'",
                (utcnow(),),
            ).rowcount

    # ------------------------------------------------------------------ uso da API do Google
    def consume_quota(self, sku: str, limit: int) -> int:
        """Registra uma chamada se ainda houver cota no mês. Retorna o total do mês ou -1 se esgotado."""
        month = _month()
        with self.db.tx() as conn:
            row = conn.execute("SELECT calls FROM api_usage WHERE month = ? AND sku = ?", (month, sku)).fetchone()
            calls = row["calls"] if row else 0
            if calls >= limit:
                return -1
            conn.execute("INSERT INTO api_usage (month, sku, calls) VALUES (?, ?, 1) ON CONFLICT(month, sku) DO UPDATE SET calls = calls + 1",
                         (month, sku))
            return calls + 1

    def usage(self, month: str | None = None) -> dict:
        with self.db.read() as conn:
            rows = conn.execute("SELECT sku, calls FROM api_usage WHERE month = ?", (month or _month(),)).fetchall()
        return {r["sku"]: r["calls"] for r in rows}

    # ------------------------------------------------------------------ cache de conteúdo do Google
    def stale_google_leads(self, days: int) -> list[dict]:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).replace(microsecond=0).isoformat()
        with self.db.read() as conn:
            rows = conn.execute(
                "SELECT id, place_id, name, status, google_fetched_at FROM leads WHERE source = 'google_places' "
                "AND google_content_purged = 0 AND google_fetched_at < ? ORDER BY google_fetched_at", (cutoff,),
            ).fetchall()
        return [dict(r) for r in rows]

    def purge_google_content(self, lead_id: int, actor: str) -> None:
        """Remove o conteúdo vindo do Google e mantém place_id, histórico e anotações do usuário."""
        fields = {k: None for k in GOOGLE_FIELDS if k != "name"}
        fields.update({"name": "(dados do Google expirados — atualize)", "google_content_purged": 1, "updated_at": utcnow()})
        cols = ", ".join(f"{k} = ?" for k in fields)
        with self.db.tx() as conn:
            conn.execute(f"UPDATE leads SET {cols} WHERE id = ?", (*fields.values(), lead_id))
            self._event(conn, lead_id, actor, "atualizacao_dados", "Conteúdo do Google removido após o prazo de cache (place_id mantido)")

    # ------------------------------------------------------------------ tokens, auditoria e configurações
    def create_token(self, name: str, scopes: list[str]) -> str:
        bad = [s for s in scopes if s not in ALL_SCOPES]
        if bad:
            raise ValueError(f"Escopos inválidos: {', '.join(bad)}. Válidos: {', '.join(ALL_SCOPES)}")
        token = "pk_" + secrets.token_urlsafe(32)
        with self.db.tx() as conn:
            conn.execute("INSERT INTO api_tokens (name, token_hash, scopes, created_at) VALUES (?, ?, ?, ?)",
                         (name, hash_token(token), ",".join(scopes), utcnow()))
        return token

    def verify_token(self, token: str) -> dict | None:
        h = hash_token(token)
        with self.db.read() as conn:
            row = conn.execute("SELECT * FROM api_tokens WHERE token_hash = ? AND revoked = 0", (h,)).fetchone()
        if not row or not hmac.compare_digest(row["token_hash"], h):
            return None
        with self.db.tx() as conn:
            conn.execute("UPDATE api_tokens SET last_used_at = ? WHERE id = ?", (utcnow(), row["id"]))
        return {"name": row["name"], "scopes": set(row["scopes"].split(","))}

    def list_tokens(self) -> list[dict]:
        with self.db.read() as conn:
            return [dict(r) for r in conn.execute("SELECT id, name, scopes, revoked, created_at, last_used_at FROM api_tokens ORDER BY id").fetchall()]

    def revoke_token(self, name: str) -> bool:
        with self.db.tx() as conn:
            return conn.execute("UPDATE api_tokens SET revoked = 1 WHERE name = ?", (name,)).rowcount > 0

    def audit(self, actor: str, method: str, path: str, status: int, detail: str | None = None) -> None:
        with self.db.tx() as conn:
            conn.execute("INSERT INTO audit_log (at, actor, method, path, status, detail) VALUES (?, ?, ?, ?, ?, ?)",
                         (utcnow(), actor, method, path, status, detail))

    def audit_entries(self, limit: int = 200) -> list[dict]:
        with self.db.read() as conn:
            return [dict(r) for r in conn.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()]

    def prune_audit(self, days: int = 180) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self.db.tx() as conn:
            return conn.execute("DELETE FROM audit_log WHERE at < ?", (cutoff,)).rowcount

    def settings(self) -> dict:
        out = copy.deepcopy(DEFAULT_SETTINGS)
        with self.db.read() as conn:
            for r in conn.execute("SELECT key, value FROM settings").fetchall():
                value = loads(r["value"])
                if isinstance(out.get(r["key"]), dict) and isinstance(value, dict):
                    out[r["key"]] = {**out[r["key"]], **value} if r["key"] != "scoring" else value
                else:
                    out[r["key"]] = value
        return out

    def save_setting(self, key: str, value: Any) -> None:
        if key not in DEFAULT_SETTINGS:
            raise ValueError(f"Configuração desconhecida: {key}")
        with self.db.tx() as conn:
            conn.execute("INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
                         (key, dumps(value), utcnow()))


def presence_from_website(website: str | None) -> str:
    return classify_url(website)[0]
