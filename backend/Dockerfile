# syntax=docker/dockerfile:1.7
# ---------- build: instala dependências com uv (workspace: core + api) ----------
FROM python:3.12-slim-bookworm AS builder
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
COPY packages/asclepio_core/pyproject.toml packages/asclepio_core/pyproject.toml
COPY backend/pyproject.toml backend/pyproject.toml
COPY ml/pyproject.toml ml/pyproject.toml
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-workspace --package asclepio-api
COPY packages/asclepio_core packages/asclepio_core
COPY backend backend
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package asclepio-api

# ---------- runtime ----------
FROM python:3.12-slim-bookworm AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 10001 asclepio
WORKDIR /app
COPY --from=builder --chown=asclepio:asclepio /app/.venv /app/.venv
COPY --from=builder --chown=asclepio:asclepio /app/packages /app/packages
COPY --from=builder --chown=asclepio:asclepio /app/backend /app/backend
# dados (base de conhecimento) são montados como volume em /app/data
RUN mkdir -p /app/data /app/ml && chown -R asclepio:asclepio /app
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 APP_ENV=production LOG_FORMAT=json \
    KNOWLEDGE_BASE_DIR=/app/data/knowledge_base VECTORSTORE_DIR=/app/data/vectorstore \
    CHECKPOINTS_DIR=/app/data/checkpoints SYNTHETIC_PATIENTS_FILE=/app/data/synthetic/patients.json \
    ML_REGISTRY_FILE=/app/ml/registry.json ML_EVAL_REPORT_FILE=/app/ml/reports/eval_latest.json
USER asclepio
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=60s --retries=10 CMD curl -fsS http://localhost:8000/health || exit 1
CMD ["uvicorn", "asclepio_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "backend", "--proxy-headers", "--forwarded-allow-ips", "*"]
