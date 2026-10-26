# Imagem de referência para implantação (não testada no ambiente em que o projeto foi escrito).
# Build:  docker build -t prospecta .
# Rodar:  docker run -d --name prospecta --env-file .env -e HOST=0.0.0.0 \
#           -p 127.0.0.1:8000:8000 -v "$(pwd)/data:/app/data" prospecta
# A porta fica publicada só em 127.0.0.1 do host. Para acesso externo, use um proxy com HTTPS.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY static ./static
COPY mcp_server ./mcp_server
COPY .env.example ./
RUN useradd --create-home prospecta && mkdir -p data exports && chown -R prospecta /app
USER prospecta
EXPOSE 8000
CMD ["python", "-m", "app"]
