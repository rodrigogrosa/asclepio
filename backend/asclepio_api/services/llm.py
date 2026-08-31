"""Fábrica de modelos (LLM e embeddings) + observabilidade (Langfuse).

Provedores suportados (``LLM_PROVIDER``):
- ``ollama``  → 100% local; usa o modelo fine-tunado ``asclepio-med`` (criado pelo pipeline
  de ML) com *fallback* automático para ``LLM_FALLBACK_MODEL`` se ele ainda não existir.
- ``litellm`` → gateway LiteLLM (OpenAI-compatible) — roteia para Ollama/OpenAI/Azure/etc.,
  centraliza chaves, limites, custo e envia traces ao Langfuse (ver infra/litellm/config.yaml).
- ``openai``  → qualquer endpoint OpenAI-compatible.
- ``fake``    → modelo determinístico para testes/CI (sem rede), que "responde" com base no contexto.

A troca de modelo em tempo de execução (``POST /model/switch``) é persistida em ``app_settings``.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from typing import Any

import httpx
from langchain_core.callbacks import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.embeddings import DeterministicFakeEmbedding, Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult

from ..core.config import Settings, get_settings
from ..core.logging import get_logger

log = get_logger("llm")


class LLMUnavailableError(RuntimeError):
    """O provedor de LLM (ex.: Ollama) está fora do ar / inalcançável."""


_CONN_HINTS = (
    "name or service not known",
    "connection refused",
    "connect call failed",
    "failed to connect",
    "nodename nor servname",
    "temporary failure in name resolution",
    "connecterror",
    "connection error",
    "timed out",
    "timeout",
    "no route to host",
)


def map_llm_error(exc: Exception) -> str | None:
    """Se o erro for de conectividade com o provedor, devolve uma mensagem amigável em pt-BR."""
    text = f"{type(exc).__name__}: {exc}".lower()
    if isinstance(exc, ConnectionError | OSError) or any(h in text for h in _CONN_HINTS):
        s = get_settings()
        alvo = (
            s.ollama_base_url
            if s.llm_provider == "ollama"
            else (
                s.litellm_base_url
                if s.llm_provider == "litellm"
                else s.openai_base_url or "provedor"
            )
        )
        return (
            f"O serviço de modelos de IA está indisponível no momento (não foi possível conectar a {alvo}). "
            "Verifique se o Ollama está em execução — `make logs` mostra os detalhes e `make up` (ou `./scripts/bootstrap.sh`) "
            "sobe/repara os serviços — e tente novamente em instantes."
        )
    return None


def raise_if_llm_unavailable(exc: Exception) -> None:
    """Converte erros de conexão em LLMUnavailableError (mensagem amigável); re-levanta os demais."""
    msg = map_llm_error(exc)
    if msg:
        raise LLMUnavailableError(msg) from exc
    raise exc


@dataclass
class ModelInfo:
    provider: str
    name: str
    fine_tuned: bool
    base_model: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "name": self.name,
            "fine_tuned": self.fine_tuned,
            "base_model": self.base_model,
        }


# ---------------------------------------------------------------------------
# Modelo fake (testes / CI / demonstração offline)
# ---------------------------------------------------------------------------
class FakeClinicalChatModel(BaseChatModel):
    """Modelo determinístico: extrai o primeiro trecho de contexto do prompt e o devolve
    como resposta estruturada, citando [1]. Suporta streaming. Sem rede."""

    model_name: str = "fake-clinical"

    @property
    def _llm_type(self) -> str:
        return "fake-clinical"

    def _compose(self, messages: list[BaseMessage]) -> str:
        text = "\n".join(str(m.content) for m in messages)
        user = str(messages[-1].content) if messages else ""
        if "FORA do escopo" in text:
            return "Desculpe, o Asclépio apoia apenas questões clínicas e institucionais do hospital. Posso ajudar com protocolos, exames ou documentos clínicos? ⚠️ Esta orientação é apoio à decisão e requer validação do médico assistente."
        if "pediu para você PRESCREVER" in text:
            return "Não posso prescrever nem decidir a conduta — isso cabe ao médico assistente. Segundo o protocolo institucional [1], a dose usual e os critérios estão descritos no trecho citado; considere alergias e função renal. ⚠️ Esta orientação é apoio à decisão e requer validação do médico assistente."
        if "perguntou sobre você" in text:
            return "Sou o Asclépio, assistente clínico do HU-FIAP. Fui ajustado (fine-tuning) com protocolos, FAQs e modelos do hospital, busco trechos dos protocolos (RAG) e cito as fontes. Não prescrevo sem validação humana; dados de pacientes são anonimizados e tudo é auditado. ⚠️ Esta orientação é apoio à decisão e requer validação do médico assistente."
        m = re.search(
            r"\[1\] \((.+?)\)\n(.+?)(?:\n\n\[2\] \(|\n\n[A-ZÀ-Ü]{3,}|\Z)", text, re.DOTALL
        )
        if m:
            src, chunk = m.group(1), m.group(2).strip()
            snippet = re.sub(r"\s+", " ", chunk)[:420]
            if "SUGESTÃO DE CONDUTA" in text:
                return (
                    "**Síntese clínica**: paciente com achados de atenção descritos na avaliação de risco determinística [1].\n\n"
                    "**Critérios de protocolo aplicáveis**: ver trecho [1].\n\n"
                    "**Sugestões para validação médica**:\n"
                    "- [alta] [exame] Coletar/repetir exames pendentes — o protocolo orienta reavaliação precoce [1].\n"
                    "- [alta] [monitorizacao] Monitorização contínua de sinais vitais — critérios de gravidade do protocolo [1].\n"
                    "- [media] [conduta] Revisar conduta conforme seção de conduta do protocolo [1].\n"
                    "- [media] [encaminhamento] Avaliar necessidade de leito de maior complexidade [1].\n\n"
                    f"Fontes: {src}\n\n⚠️ Esta orientação é apoio à decisão e requer validação do médico assistente."
                )
            return f"Segundo o protocolo institucional [1]: {snippet}\n\nFontes: {src}\n\n⚠️ Esta orientação é apoio à decisão e requer validação do médico assistente."
        return f'Não encontrei protocolo institucional específico para: "{user[:120]}". Posso ajudar com base nos protocolos disponíveis. ⚠️ Esta orientação é apoio à decisão e requer validação do médico assistente.'

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content=self._compose(messages)))]
        )

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        for tok in re.findall(r"\S+\s*|\n", self._compose(messages)):
            chunk = ChatGenerationChunk(message=AIMessageChunk(content=tok))
            if run_manager:
                run_manager.on_llm_new_token(tok, chunk=chunk)
            yield chunk

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        for tok in re.findall(r"\S+\s*|\n", self._compose(messages)):
            chunk = ChatGenerationChunk(message=AIMessageChunk(content=tok))
            if run_manager:
                await run_manager.on_llm_new_token(tok, chunk=chunk)
            yield chunk


# ---------------------------------------------------------------------------
# Fábrica
# ---------------------------------------------------------------------------
class LLMFactory:
    def __init__(self, settings: Settings | None = None) -> None:
        self.s = settings or get_settings()
        self._override_model: str | None = None
        self._available_cache: list[dict[str, Any]] | None = None
        self._available_cache_at: float = 0.0
        self._warned_fallback: str | None = None

    # ---- Ollama helpers ----
    def ollama_models(self, refresh: bool = False) -> list[dict[str, Any]]:
        """Lista modelos do Ollama (cache de 60 s — assim um `ollama create asclepio-med` é detectado sem reiniciar)."""
        import time as _time

        if (
            self._available_cache is not None
            and not refresh
            and _time.monotonic() - self._available_cache_at < 60
        ):
            return self._available_cache
        try:
            r = httpx.get(f"{self.s.ollama_base_url}/api/tags", timeout=3)
            r.raise_for_status()
            models = [
                {"name": m["name"], "size": m.get("size", 0)} for m in r.json().get("models", [])
            ]
        except Exception as exc:
            log.warning("ollama indisponível", error=str(exc))
            models = []
        self._available_cache = models
        self._available_cache_at = _time.monotonic()
        return models

    def ollama_reachable(self) -> bool:
        try:
            return httpx.get(f"{self.s.ollama_base_url}/api/tags", timeout=2).status_code == 200
        except Exception:
            return False

    def set_model(self, name: str | None) -> None:
        self._override_model = name
        self._available_cache = None

    @property
    def requested_model(self) -> str:
        return self._override_model or self.s.llm_model

    def resolve_model(self) -> ModelInfo:
        """Decide qual modelo será usado de fato (com fallback) e se é o fine-tunado."""
        p = self.s.llm_provider
        name = self.requested_model
        if p == "fake":
            return ModelInfo("fake", "fake-clinical", fine_tuned=False)
        if p == "ollama":
            available = {m["name"].split(":")[0]: m["name"] for m in self.ollama_models()}
            full = {m["name"] for m in self.ollama_models()}
            if name in full or name.split(":")[0] in available:
                resolved = name if name in full else available[name.split(":")[0]]
            elif available:
                resolved = (
                    self.s.llm_fallback_model
                    if (
                        self.s.llm_fallback_model in full
                        or self.s.llm_fallback_model.split(":")[0] in available
                    )
                    else next(iter(full))
                )
                log.warning(
                    "modelo não encontrado no Ollama; usando fallback",
                    requested=name,
                    fallback=resolved,
                )
            else:
                resolved = name
            return ModelInfo(
                "ollama",
                resolved,
                fine_tuned=resolved.startswith("asclepio-med"),
                base_model=self._registry_base(),
            )
        return ModelInfo(
            p, name, fine_tuned=name.startswith("asclepio-med"), base_model=self._registry_base()
        )

    def _registry_base(self) -> str | None:
        try:
            import json
            from pathlib import Path

            reg = json.loads(Path(self.s.ml_registry_file).read_text(encoding="utf-8"))
            return reg.get("base_model")
        except Exception:
            return None

    def chat_model(
        self,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        streaming: bool = True,
    ) -> tuple[BaseChatModel, ModelInfo]:
        info = self.resolve_model()
        temp = self.s.llm_temperature if temperature is None else temperature
        max_tok = max_tokens or self.s.llm_max_tokens
        if info.provider == "fake":
            return FakeClinicalChatModel(), info
        if info.provider == "ollama":
            from langchain_ollama import ChatOllama

            return ChatOllama(
                model=info.name,
                base_url=self.s.ollama_base_url,
                temperature=temp,
                num_predict=max_tok,
                num_ctx=8192,
                keep_alive="10m",
            ), info
        from langchain_openai import ChatOpenAI

        if info.provider == "litellm":
            return ChatOpenAI(
                model=info.name,
                base_url=self.s.litellm_base_url,
                api_key=self.s.litellm_api_key,
                temperature=temp,
                max_tokens=max_tok,
                streaming=streaming,
                timeout=self.s.llm_timeout_seconds,
            ), info
        return ChatOpenAI(
            model=info.name,
            base_url=self.s.openai_base_url,
            api_key=self.s.openai_api_key or "sk-none",
            temperature=temp,
            max_tokens=max_tok,
            streaming=streaming,
            timeout=self.s.llm_timeout_seconds,
        ), info

    def embeddings(self) -> tuple[Embeddings, dict[str, str]]:
        p = self.s.embeddings_provider
        if p == "fake":
            return DeterministicFakeEmbedding(size=384), {
                "provider": "fake",
                "model": "deterministic-384",
            }
        if p == "ollama":
            from langchain_ollama import OllamaEmbeddings

            return OllamaEmbeddings(
                model=self.s.embeddings_model, base_url=self.s.ollama_base_url
            ), {"provider": "ollama", "model": self.s.embeddings_model}
        from langchain_openai import OpenAIEmbeddings

        if p == "litellm":
            return OpenAIEmbeddings(
                model=self.s.embeddings_model,
                base_url=self.s.litellm_base_url,
                api_key=self.s.litellm_api_key,
                check_embedding_ctx_length=False,
            ), {"provider": "litellm", "model": self.s.embeddings_model}
        return OpenAIEmbeddings(
            model=self.s.embeddings_model,
            base_url=self.s.openai_base_url,
            api_key=self.s.openai_api_key or "sk-none",
        ), {"provider": "openai", "model": self.s.embeddings_model}

    # ---- Observabilidade ----
    def langfuse_handler(self):  # type: ignore[no-untyped-def]
        """Callback do Langfuse (tracing de prompts, tokens, latência) quando configurado."""
        if not self.s.langfuse_active:
            return None
        try:
            import os

            os.environ.setdefault("LANGFUSE_PUBLIC_KEY", self.s.langfuse_public_key or "")
            os.environ.setdefault("LANGFUSE_SECRET_KEY", self.s.langfuse_secret_key or "")
            if self.s.langfuse_host:
                os.environ.setdefault("LANGFUSE_HOST", self.s.langfuse_host)
            from langfuse.langchain import CallbackHandler

            return CallbackHandler()
        except Exception as exc:
            log.warning("langfuse indisponível", error=str(exc))
            return None

    def run_config(
        self,
        *,
        trace_id: str,
        user_id: str | None = None,
        session_id: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Config padrão para invocar chains/grafos: callbacks + metadados (aparecem no Langfuse/LangSmith)."""
        cfg: dict[str, Any] = {
            "run_name": "asclepio",
            "tags": ["asclepio", *(tags or [])],
            "metadata": {
                "trace_id": trace_id,
                "langfuse_session_id": session_id or trace_id,
                "langfuse_user_id": user_id or "anon",
                "langfuse_tags": ["asclepio", *(tags or [])],
            },
        }
        h = self.langfuse_handler()
        if h is not None:
            cfg["callbacks"] = [h]
        return cfg


_factory: LLMFactory | None = None


def get_llm_factory() -> LLMFactory:
    global _factory
    if _factory is None:
        _factory = LLMFactory()
    return _factory


def reset_llm_factory() -> None:
    global _factory
    _factory = None
