"""Comandos de administração.

  python -m app.cli init                         cria .env com ADMIN_TOKEN e o banco
  python -m app.cli create-token --name claude --scopes leads:read,leads:write,search:run,export
  python -m app.cli list-tokens | revoke-token --name claude
  python -m app.cli import-csv planilha.csv      importa leads e analisa
  python -m app.cli seed-demo                    insere empresas FICTÍCIAS para conhecer o painel
  python -m app.cli google-cache report|purge|refresh
  python -m app.cli run-jobs                     processa a fila sem subir o servidor web
"""
from __future__ import annotations

import argparse
import re
import secrets
import sys

from .config import PROJECT_ROOT, load_config
from .db import utcnow
from .jobs import Worker
from .main import build_services


def cmd_init(args) -> None:
    env = PROJECT_ROOT / ".env"
    example = PROJECT_ROOT / ".env.example"
    text = env.read_text(encoding="utf-8") if env.exists() else example.read_text(encoding="utf-8")
    token = None
    m = re.search(r"^ADMIN_TOKEN=(.*)$", text, re.M)
    if not m or not m.group(1).strip():
        token = "adm_" + secrets.token_urlsafe(32)
        text = re.sub(r"^ADMIN_TOKEN=.*$", f"ADMIN_TOKEN={token}", text, flags=re.M) if m else text + f"\nADMIN_TOKEN={token}\n"
        env.write_text(text, encoding="utf-8")
    import os

    if token:
        os.environ["ADMIN_TOKEN"] = token
    build_services(load_config())
    print(f"Banco pronto em {load_config().database_path}")
    if token:
        print("\nToken de administrador gerado e salvo no .env:\n")
        print(f"  {token}\n")
        print("Use esse token para entrar no painel. Não compartilhe.")
    else:
        print("ADMIN_TOKEN já existia no .env (não foi alterado).")


def cmd_create_token(args) -> None:
    svc = build_services(load_config())
    scopes = [s.strip() for s in args.scopes.split(",") if s.strip()]
    token = svc.repo.create_token(args.name, scopes)
    print(f"Token '{args.name}' criado com escopos {', '.join(scopes)}:\n\n  {token}\n\nGuarde agora: ele não será exibido novamente.")


def cmd_list_tokens(args) -> None:
    svc = build_services(load_config())
    for t in svc.repo.list_tokens():
        state = "revogado" if t["revoked"] else "ativo"
        print(f"{t['name']:<20} {state:<9} {t['scopes']:<60} último uso: {t['last_used_at'] or '-'}")


def cmd_revoke_token(args) -> None:
    svc = build_services(load_config())
    print("Revogado." if svc.repo.revoke_token(args.name) else "Token não encontrado.")


def cmd_import_csv(args) -> None:
    svc = build_services(load_config())
    with open(args.path, "rb") as f:
        result = svc.import_csv(f.read(), "cli")
    print(result)
    if result.get("analysis_job_id"):
        print("Analisando leads importados...")
        Worker(svc).process_next()
        print("Pronto.")


def cmd_run_jobs(args) -> None:
    svc = build_services(load_config())
    w = Worker(svc)
    n = 0
    while w.process_next():
        n += 1
    print(f"{n} trabalho(s) processado(s).")


def cmd_google_cache(args) -> None:
    svc = build_services(load_config())
    print(svc.google_cache_maintenance(args.mode, "cli"))


DEMO = [
    {"name": "Academia Exemplo Fit (DEMO)", "category": "Academia", "segment": "academia", "neighborhood": "Centro", "rating": 4.8, "reviews_count": 212, "phone": "(41) 90000-0001", "website": None},
    {"name": "Clínica Sorriso Fictício (DEMO)", "category": "Dentista", "segment": "saude", "neighborhood": "Batel", "rating": 4.9, "reviews_count": 87, "phone": "(41) 90000-0002", "website": "https://instagram.com/clinica_demo_ficticia"},
    {"name": "Oficina Modelo Demo (DEMO)", "category": "Oficina mecânica", "segment": "automotivo", "neighborhood": "Portão", "rating": 4.6, "reviews_count": 143, "phone": "(41) 3000-0003", "website": "https://oficina-demo.business.site"},
    {"name": "Salão Beleza Ilustrativa (DEMO)", "category": "Salão de beleza", "segment": "beleza", "neighborhood": "Água Verde", "rating": 4.4, "reviews_count": 35, "phone": "(41) 90000-0004", "website": "http://salao-demo.example"},
    {"name": "Restaurante Sabor Teste (DEMO)", "category": "Restaurante", "segment": "alimentacao", "neighborhood": "Mercês", "rating": 4.2, "reviews_count": 640, "phone": "(41) 90000-0005", "website": "https://restaurante-demo.example"},
    {"name": "Escritório Contábil Amostra (DEMO)", "category": "Contabilidade", "segment": "profissionais", "neighborhood": "Centro Cívico", "rating": 5.0, "reviews_count": 3, "phone": None, "website": None},
]
DEMO_SITES = {
    "http://salao-demo.example": {"kind": "proprio", "kind_label": "Site próprio", "platform": None, "fetched": True, "reachable": True,
                                  "final_url": "http://salao-demo.example", "status_code": 200, "response_ms": 900,
                                  "issues": [
                                      {"code": "sem_https", "label": "Site sem HTTPS (navegadores mostram \"Não seguro\")", "evidence": "Exemplo fictício", "basis": "verificado"},
                                      {"code": "sem_meta_viewport", "label": "Página sem a tag de adaptação para celular (meta viewport)", "evidence": "Exemplo fictício", "basis": "verificado"},
                                      {"code": "rodape_desatualizado", "label": "Ano no rodapé: 2019", "evidence": "Exemplo fictício", "basis": "hipotese"}],
                                  "signals": {}, "social_links": {}},
    "https://restaurante-demo.example": {"kind": "proprio", "kind_label": "Site próprio", "platform": None, "fetched": True, "reachable": True,
                                         "final_url": "https://restaurante-demo.example", "status_code": 200, "response_ms": 650,
                                         "issues": [], "signals": {"https": True, "meta_viewport": True}, "social_links": {}},
}


def cmd_seed_demo(args) -> None:
    from .site_analysis import analyze_website

    svc = build_services(load_config())
    for d in DEMO:
        data = dict(d, city="Curitiba", state="PR", address=f"Rua Fictícia, 100 - {d['neighborhood']}, Curitiba - PR")
        lead_id, new = svc.repo.upsert_lead(data, "demo", "cli")
        site = DEMO_SITES.get(d["website"] or "") or analyze_website(d["website"], None)
        site["checked_at"] = utcnow()
        svc.repo.update_lead(lead_id, {"site_analysis": site, "site_analyzed_at": utcnow(), "presence_kind": site["kind"]})
        svc.analyze(lead_id, "cli")
        print(f"{'+' if new else '='} {d['name']}")
    print("\nEmpresas FICTÍCIAS inseridas (origem 'demo'). O envio por WhatsApp fica bloqueado para elas.")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m app.cli", description="Administração do Prospecta")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init").set_defaults(fn=cmd_init)
    p = sub.add_parser("create-token")
    p.add_argument("--name", required=True)
    p.add_argument("--scopes", required=True, help="ex.: leads:read,leads:write,search:run,export")
    p.set_defaults(fn=cmd_create_token)
    sub.add_parser("list-tokens").set_defaults(fn=cmd_list_tokens)
    p = sub.add_parser("revoke-token")
    p.add_argument("--name", required=True)
    p.set_defaults(fn=cmd_revoke_token)
    p = sub.add_parser("import-csv")
    p.add_argument("path")
    p.set_defaults(fn=cmd_import_csv)
    sub.add_parser("seed-demo").set_defaults(fn=cmd_seed_demo)
    sub.add_parser("run-jobs").set_defaults(fn=cmd_run_jobs)
    p = sub.add_parser("google-cache")
    p.add_argument("mode", choices=["report", "purge", "refresh"])
    p.set_defaults(fn=cmd_google_cache)
    args = ap.parse_args(argv)
    try:
        args.fn(args)
    except (ValueError, FileNotFoundError) as e:
        sys.exit(f"Erro: {e}")


if __name__ == "__main__":
    main()
