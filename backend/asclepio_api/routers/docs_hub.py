"""Central de documentação — serve os artefatos acadêmicos do repositório dentro da plataforma.

Evidências para avaliação (Tech Challenge): relatório técnico, processo de desenvolvimento,
arquitetura/ADRs, dataset card, avaliação do modelo, políticas, guias e diagramas.
Lista **curada e imutável** (nenhum acesso por caminho livre — sem path traversal).
"""

from __future__ import annotations

import base64
import mimetypes
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..core.config import REPO_ROOT
from ..core.deps import require_permission

router = APIRouter(
    prefix="/docs-hub", tags=["documentação"], dependencies=[require_permission("docs:read")]
)

DOCS = REPO_ROOT / "docs"
MAX_INLINE_IMAGE = 800_000  # imagens relativas até ~800 KB viram data URI no conteúdo


@dataclass(frozen=True)
class Doc:
    id: str
    title: str
    description: str
    path: Path


@dataclass(frozen=True)
class Category:
    id: str
    title: str
    description: str
    docs: tuple[Doc, ...]


CATALOG: tuple[Category, ...] = (
    Category(
        "relatorios",
        "Relatórios da entrega",
        "Documentos principais exigidos pelo edital da Fase 3.",
        (
            Doc(
                "relatorio-tecnico",
                "Relatório Técnico",
                "Documento central: dados, anonimização, fine-tuning, assistente, fluxos, segurança, avaliação e conclusões — abre com o checklist de conformidade com o edital.",
                DOCS / "RELATORIO_TECNICO.md",
            ),
            Doc(
                "relatorio-tecnico-pdf",
                "Relatório Técnico (PDF)",
                "Versão em PDF com capa e anexos (fine-tuning, arquitetura, políticas, evidências) para impressão/entrega.",
                DOCS / "RELATORIO_TECNICO.pdf",
            ),
            Doc(
                "evidencias",
                "Mapa de evidências",
                "Onde cada exigência do edital aparece no sistema: tela, arquivo e comando — inclui roteiro de demonstração de 10 minutos.",
                DOCS / "EVIDENCIAS.md",
            ),
            Doc(
                "roteiro-video",
                "Roteiro do vídeo (≤ 15 min)",
                "Cena a cena do vídeo de demonstração exigido pela entrega.",
                DOCS / "ROTEIRO_VIDEO.md",
            ),
        ),
    ),
    Category(
        "processo",
        "Processo de desenvolvimento",
        "Como o projeto foi construído, etapa por etapa, com visão acadêmica (método, ferramentas, artefatos e resultados de cada fase).",
        (
            Doc(
                "processo-desenvolvimento",
                "Processo de desenvolvimento (passo a passo)",
                "Metodologia completa: da leitura do edital à publicação — requisitos, concepção, arquitetura, dados, fine-tuning, avaliação, segurança, frontend, DevEx e lições aprendidas.",
                DOCS / "PROCESSO_DESENVOLVIMENTO.md",
            ),
            Doc(
                "changelog",
                "Histórico de versões (Changelog)",
                "Evolução do produto por versão (1.0 → 1.2), no padrão Keep a Changelog.",
                REPO_ROOT / "CHANGELOG.md",
            ),
        ),
    ),
    Category(
        "arquitetura",
        "Arquitetura e decisões",
        "Desenho da solução e registro das decisões de engenharia (ADRs).",
        (
            Doc(
                "arquitetura",
                "Arquitetura da solução",
                "Componentes, fluxos de dados, diagramas de sequência, RAG, observabilidade e deploy.",
                DOCS / "ARQUITETURA.md",
            ),
            Doc(
                "contrato-api",
                "Contrato da API",
                "Todos os endpoints, tipos e regras (v1 → v1.3), incluindo autenticação real e catálogos.",
                DOCS / "CONTRATO_API.md",
            ),
            Doc(
                "adr-0001",
                "ADR-0001 · Monorepo com uv workspace",
                "Por que um monorepo Python (core/backend/ml) + frontend.",
                DOCS / "adr" / "0001-monorepo-uv-workspace.md",
            ),
            Doc(
                "adr-0002",
                "ADR-0002 · LangGraph com validação humana",
                "Por que grafos determinísticos com interrupt em vez de agente livre.",
                DOCS / "adr" / "0002-langgraph-com-validacao-humana.md",
            ),
            Doc(
                "adr-0003",
                "ADR-0003 · LoRA em modelo pequeno + Ollama",
                "Escolha do modelo base, LoRA e serving local.",
                DOCS / "adr" / "0003-lora-modelo-pequeno-ollama.md",
            ),
            Doc(
                "adr-0004",
                "ADR-0004 · Auditoria com cadeia de hashes",
                "Trilha imutável (tamper-evident) para rastreabilidade.",
                DOCS / "adr" / "0004-auditoria-hash-chain.md",
            ),
            Doc(
                "adr-0005",
                "ADR-0005 · LiteLLM e Langfuse",
                "Gateway de modelos e observabilidade de LLM.",
                DOCS / "adr" / "0005-litellm-langfuse-observabilidade.md",
            ),
        ),
    ),
    Category(
        "dados-ml",
        "Dados e fine-tuning",
        "Preparo dos dados (anonimização/curadoria), treino LoRA e avaliação do modelo.",
        (
            Doc(
                "fine-tuning",
                "Fine-tuning em detalhe",
                "Dados, anonimização, curadoria, LoRA e hiperparâmetros, hardware, resultados reais e análise crítica.",
                DOCS / "FINE_TUNING.md",
            ),
            Doc(
                "dataset-card",
                "Dataset card (dados de treino)",
                "Composição do dataset SFT: origens, categorias, contagens, PII removida, splits e avisos.",
                REPO_ROOT / "data" / "processed" / "DATASET_CARD.md",
            ),
            Doc(
                "eval-report",
                "Relatório de avaliação (última execução)",
                "Métricas base × fine-tuned × referência e RAG, geradas pelo pipeline de avaliação.",
                REPO_ROOT / "ml" / "reports" / "eval_latest.md",
            ),
            Doc(
                "kb-readme",
                "Base de conhecimento (formato e conteúdo)",
                "Esquema dos 16 protocolos, 10 modelos de documento e 167 FAQs fictícios usados no RAG e no treino.",
                REPO_ROOT / "data" / "knowledge_base" / "README.md",
            ),
        ),
    ),
    Category(
        "seguranca-operacao",
        "Segurança e operação",
        "Políticas de segurança/acesso e guias de instalação e uso.",
        (
            Doc(
                "politicas",
                "Políticas de segurança, acesso e uso",
                "Autenticação forte (MFA), RBAC por perfil, LGPD/anonimização, guardrails, auditoria e infraestrutura.",
                DOCS / "POLITICAS.md",
            ),
            Doc(
                "guia-instalacao",
                "Guia de instalação",
                "Passo a passo para instalar em qualquer máquina (1 comando ou manual), credenciais e troubleshooting.",
                DOCS / "GUIA_INSTALACAO.md",
            ),
            Doc(
                "guia-instalacao-pdf",
                "Guia de instalação (PDF)",
                "Versão em PDF do guia, com anexo de evidências.",
                DOCS / "GUIA_INSTALACAO.pdf",
            ),
            Doc(
                "identidade-visual",
                "Identidade visual",
                "Nome, logo, paleta, tipografia e padrões de interface.",
                DOCS / "IDENTIDADE_VISUAL.md",
            ),
        ),
    ),
    Category(
        "diagramas",
        "Diagramas",
        "Grafos gerados pelo próprio LangGraph e diagrama de arquitetura (Mermaid).",
        (
            Doc(
                "diagrama-arquitetura",
                "Arquitetura (Mermaid)",
                "Componentes e integrações da plataforma.",
                DOCS / "diagramas" / "arquitetura.mmd",
            ),
            Doc(
                "diagrama-chat",
                "Grafo do assistente (LangGraph)",
                "guard_input → classify → retrieve → generate → guard_output — gerado pelo código.",
                DOCS / "diagramas" / "grafo_chat_langgraph.mmd",
            ),
            Doc(
                "diagrama-fluxo",
                "Grafo da revisão clínica (LangGraph)",
                "10 nós com ramificações, regeneração e validação humana — gerado pelo código.",
                DOCS / "diagramas" / "grafo_revisao_clinica_langgraph.mmd",
            ),
        ),
    ),
)

_BY_ID: dict[str, tuple[Category, Doc]] = {d.id: (c, d) for c in CATALOG for d in c.docs}


def _fmt(path: Path) -> str:
    return {".md": "md", ".pdf": "pdf", ".mmd": "mmd"}.get(path.suffix.lower(), "md")


def _doc_out(d: Doc) -> dict[str, Any]:
    exists = d.path.exists()
    stat = d.path.stat() if exists else None
    fmt = _fmt(d.path)
    return {
        "id": d.id,
        "title": d.title,
        "description": d.description,
        "format": fmt,
        "filename": d.path.name,
        "size_bytes": stat.st_size if stat else 0,
        "updated_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds")
        if stat
        else None,
        "readable": exists and fmt in ("md", "mmd"),
        "downloadable": exists,
    }


def _inline_images(content: str, base: Path) -> str:
    """Converte imagens relativas do markdown em data URIs (o frontend renderiza sem endpoint extra)."""

    def sub(m: re.Match[str]) -> str:
        src = m.group(2)
        if src.startswith(("http://", "https://", "data:")):
            return m.group(0)
        p = (base / src).resolve()
        try:
            p.relative_to(REPO_ROOT)
        except ValueError:
            return m.group(0)
        if not p.exists() or p.stat().st_size > MAX_INLINE_IMAGE:
            return m.group(0)
        mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        data = base64.b64encode(p.read_bytes()).decode()
        return f"{m.group(1)}(data:{mime};base64,{data})"

    return re.sub(r"(!\[[^\]]*\])\(([^)\s]+)\)", sub, content)


@router.get("")
async def list_documents() -> dict[str, Any]:
    cats = [
        {
            "id": c.id,
            "title": c.title,
            "description": c.description,
            "documents": [_doc_out(d) for d in c.docs],
        }
        for c in CATALOG
    ]
    return {"categories": cats, "total": sum(len(c["documents"]) for c in cats)}


@router.get("/{doc_id}")
async def read_document(doc_id: str) -> dict[str, Any]:
    entry = _BY_ID.get(doc_id)
    if not entry:
        raise HTTPException(404, "Documento não encontrado")
    _, d = entry
    out = _doc_out(d)
    if not out["readable"]:
        raise HTTPException(409, "Este documento não tem leitura embutida — use o download")
    content = d.path.read_text(encoding="utf-8")
    if out["format"] == "md":
        content = _inline_images(content, d.path.parent)
    return {**out, "content": content}


@router.get("/{doc_id}/download")
async def download_document(doc_id: str):  # type: ignore[no-untyped-def]
    entry = _BY_ID.get(doc_id)
    if not entry or not entry[1].path.exists():
        raise HTTPException(404, "Documento não encontrado")
    d = entry[1]
    media = mimetypes.guess_type(d.path.name)[0] or "application/octet-stream"
    return FileResponse(
        d.path, media_type=media, filename=d.path.name, content_disposition_type="attachment"
    )
