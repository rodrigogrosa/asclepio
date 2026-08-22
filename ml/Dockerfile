# Imagem para rodar o pipeline de ML em container (CPU). Em Macs com Apple Silicon é MUITO mais
# rápido rodar no host com MPS: `make finetune`. Use esta imagem em CI/Linux/GPU (ajuste a base para CUDA).
FROM python:3.12-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends git curl build-essential && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
COPY packages/asclepio_core packages/asclepio_core
COPY backend/pyproject.toml backend/pyproject.toml
COPY ml ml
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --package asclepio-ml
ENV PATH="/app/.venv/bin:$PATH" HF_HOME=/app/ml/.cache/huggingface
ENTRYPOINT ["python", "-m", "asclepio_ml"]
CMD ["--help"]
