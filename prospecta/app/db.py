"""Banco de dados SQLite (modo WAL).

Cada operação abre a própria conexão, o que torna o acesso seguro entre a API e o worker
de pesquisas, que rodam em threads diferentes. Para um usuário com dezenas de milhares de
leads, SQLite é suficiente. Se um dia precisar de vários usuários simultâneos, o acesso ao
banco está concentrado em app/repository.py, o que facilita trocar por PostgreSQL.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);

CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY,
    place_id TEXT UNIQUE,
    source TEXT NOT NULL,
    name TEXT NOT NULL,
    category TEXT,
    primary_type TEXT,
    segment TEXT,
    address TEXT,
    neighborhood TEXT,
    city TEXT,
    state TEXT,
    phone TEXT,
    phone_e164 TEXT,
    phone_kind TEXT,
    website TEXT,
    maps_url TEXT,
    rating REAL,
    reviews_count INTEGER,
    opening_hours TEXT,
    business_status TEXT,
    social_links TEXT,
    presence_kind TEXT,
    google_fetched_at TEXT,
    google_content_purged INTEGER NOT NULL DEFAULT 0,
    site_analysis TEXT,
    site_analyzed_at TEXT,
    score INTEGER,
    priority TEXT,
    score_breakdown TEXT,
    scored_at TEXT,
    analysis TEXT,
    analysis_generated_by TEXT,
    analyzed_at TEXT,
    suggested_message TEXT,
    message_variant TEXT,
    message_generated_by TEXT,
    message_generated_at TEXT,
    message_warnings TEXT,
    preview_ready INTEGER NOT NULL DEFAULT 0,
    preview_url TEXT,
    responsible_name TEXT,
    status TEXT NOT NULL DEFAULT 'identificado',
    consent_status TEXT NOT NULL DEFAULT 'nao_registrado',
    consent_note TEXT,
    consent_at TEXT,
    notes TEXT,
    last_contact_at TEXT,
    contact_count INTEGER NOT NULL DEFAULT 0,
    first_search_id INTEGER,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_leads_phone ON leads(phone_e164);
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
CREATE INDEX IF NOT EXISTS idx_leads_priority ON leads(priority, score);
CREATE INDEX IF NOT EXISTS idx_leads_city ON leads(city);

CREATE TABLE IF NOT EXISTS lead_events (
    id INTEGER PRIMARY KEY,
    lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    actor TEXT NOT NULL,
    type TEXT NOT NULL,
    channel TEXT,
    summary TEXT,
    details TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_lead ON lead_events(lead_id, created_at);
CREATE INDEX IF NOT EXISTS idx_events_type ON lead_events(type, created_at);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY,
    lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    due_date TEXT NOT NULL,
    done INTEGER NOT NULL DEFAULT 0,
    actor TEXT NOT NULL,
    created_at TEXT NOT NULL,
    done_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_tasks_due ON tasks(done, due_date);

CREATE TABLE IF NOT EXISTS suppression (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,
    value TEXT NOT NULL,
    reason TEXT,
    actor TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(kind, value)
);

CREATE TABLE IF NOT EXISTS search_jobs (
    id INTEGER PRIMARY KEY,
    status TEXT NOT NULL,
    params TEXT NOT NULL,
    stage TEXT,
    progress INTEGER NOT NULL DEFAULT 0,
    total INTEGER NOT NULL DEFAULT 0,
    found INTEGER NOT NULL DEFAULT 0,
    saved_new INTEGER NOT NULL DEFAULT 0,
    updated INTEGER NOT NULL DEFAULT 0,
    discarded INTEGER NOT NULL DEFAULT 0,
    high_priority INTEGER NOT NULL DEFAULT 0,
    api_calls INTEGER NOT NULL DEFAULT 0,
    discard_reasons TEXT,
    error TEXT,
    actor TEXT NOT NULL,
    cancel_requested INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS search_results (
    search_id INTEGER NOT NULL REFERENCES search_jobs(id) ON DELETE CASCADE,
    lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    is_new INTEGER NOT NULL,
    PRIMARY KEY (search_id, lead_id)
);

CREATE TABLE IF NOT EXISTS api_tokens (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    token_hash TEXT NOT NULL UNIQUE,
    scopes TEXT NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    last_used_at TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY,
    at TEXT NOT NULL,
    actor TEXT NOT NULL,
    method TEXT NOT NULL,
    path TEXT NOT NULL,
    status INTEGER NOT NULL,
    detail TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_at ON audit_log(at);

CREATE TABLE IF NOT EXISTS api_usage (
    month TEXT NOT NULL,
    sku TEXT NOT NULL,
    calls INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (month, sku)
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def dumps(value: Any) -> str | None:
    return None if value is None else json.dumps(value, ensure_ascii=False)


def loads(value: str | None, default: Any = None) -> Any:
    if value in (None, ""):
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 10000")
        return conn

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        """Transação explícita: confirma no final ou desfaz em caso de erro."""
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    @contextmanager
    def read(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            yield conn
        finally:
            conn.close()

    def init(self) -> None:
        conn = self.connect()
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(SCHEMA)
            row = conn.execute("SELECT version FROM schema_version").fetchone()
            if row is None:
                conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
        finally:
            conn.close()
