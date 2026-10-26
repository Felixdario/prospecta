"""python -m app  →  inicia o servidor web."""
import uvicorn

from .config import load_config
from .main import create_app

if __name__ == "__main__":
    cfg = load_config()
    if cfg.host not in ("127.0.0.1", "localhost"):
        print(f"Atenção: servidor acessível em {cfg.host}. Use HTTPS (proxy reverso) e um ADMIN_TOKEN forte.")
    print(f"Prospecta rodando em http://{cfg.host}:{cfg.port}  (Ctrl+C para parar)")
    uvicorn.run(create_app(cfg), host=cfg.host, port=cfg.port, log_level="info")
