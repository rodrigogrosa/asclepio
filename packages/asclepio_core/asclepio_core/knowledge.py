"""Leitura e *chunking* da base de conhecimento (protocolos, modelos de documento, FAQ).

Formato dos arquivos (ver ``data/knowledge_base/README.md``):
- Markdown com front matter YAML (``id``, ``titulo``, ``tipo``, ``categoria``, ``tags``...).
- FAQ em JSONL (``pergunta``, ``resposta``, ``protocolo_id``...).

Chunking por **seção H2** (com subdivisão por tamanho), preservando metadados
(documento, seção, tipo, versão) — é isso que permite citar "PROT-001 › Conduta".
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_FRONT = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_H2 = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)

DOC_TYPE_MAP = {
    "protocolo": "protocolo",
    "modelo": "modelo",
    "faq": "faq",
    "prontuario": "prontuario",
}


@dataclass
class KnowledgeDocument:
    id: str
    title: str
    doc_type: str
    path: str
    content: str
    category: str | None = None
    tags: list[str] = field(default_factory=list)
    version: str | None = None
    updated_at: str | None = None
    sector: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def size_chars(self) -> int:
        return len(self.content)

    def sections(self) -> list[tuple[str, str]]:
        """Divide o corpo em (título da seção, texto). O texto antes do primeiro H2 vira 'Introdução'."""
        body = _FRONT.sub("", self.content, count=1)
        positions = [(m.start(), m.end(), m.group(1)) for m in _H2.finditer(body)]
        if not positions:
            return [("Conteúdo", body.strip())]
        out: list[tuple[str, str]] = []
        head = body[: positions[0][0]].strip()
        if head:
            out.append(("Introdução", head))
        for i, (_, end, title) in enumerate(positions):
            nxt = positions[i + 1][0] if i + 1 < len(positions) else len(body)
            out.append((title.strip(), body[end:nxt].strip()))
        return out


@dataclass
class Chunk:
    id: str
    doc_id: str
    title: str
    section: str | None
    text: str
    doc_type: str
    path: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "doc_id": self.doc_id,
            "title": self.title,
            "section": self.section,
            "text": self.text,
            "doc_type": self.doc_type,
            "path": self.path,
            **self.metadata,
        }


def parse_markdown(path: Path) -> KnowledgeDocument:
    raw = path.read_text(encoding="utf-8")
    meta: dict[str, Any] = {}
    m = _FRONT.match(raw)
    if m:
        try:
            meta = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError:
            meta = {}
    doc_id = str(meta.get("id") or path.stem)
    title = str(meta.get("titulo") or meta.get("title") or path.stem)
    doc_type = DOC_TYPE_MAP.get(
        str(meta.get("tipo", "")).lower(),
        "protocolo" if "protocolo" in str(path).lower() else "modelo",
    )
    tags = meta.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    return KnowledgeDocument(
        id=doc_id,
        title=title,
        doc_type=doc_type,
        path=str(path),
        content=raw,
        category=meta.get("categoria"),
        tags=[str(t) for t in tags],
        version=str(meta.get("versao")) if meta.get("versao") is not None else None,
        updated_at=str(meta.get("atualizado_em")) if meta.get("atualizado_em") else None,
        sector=meta.get("setor"),
        metadata={
            k: v
            for k, v in meta.items()
            if k
            not in {"id", "titulo", "tipo", "categoria", "tags", "versao", "atualizado_em", "setor"}
        },
    )


def load_faq(path: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if not path.exists():
        return items
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return items


def load_knowledge_base(base_dir: str | Path) -> list[KnowledgeDocument]:
    """Carrega todos os documentos markdown (protocolos + modelos) e o FAQ (como 1 doc por item)."""
    base = Path(base_dir)
    docs: list[KnowledgeDocument] = []
    for sub in ("protocolos", "modelos_documentos"):
        d = base / sub
        if d.exists():
            for p in sorted(d.glob("*.md")):
                if p.name.lower() == "readme.md":
                    continue
                docs.append(parse_markdown(p))
    faq_dir = base / "faq"
    if faq_dir.exists():
        for p in sorted(faq_dir.glob("*.jsonl")):
            for item in load_faq(p):
                fid = str(item.get("id") or f"FAQ-{len(docs):04d}")
                q, a = item.get("pergunta", ""), item.get("resposta", "")
                docs.append(
                    KnowledgeDocument(
                        id=fid,
                        title=q[:120],
                        doc_type="faq",
                        path=str(p),
                        content=f"Pergunta: {q}\nResposta: {a}",
                        category=item.get("categoria"),
                        tags=[str(t) for t in item.get("tags", [])],
                        metadata={
                            "protocolo_id": item.get("protocolo_id"),
                            "secao": item.get("secao"),
                        },
                    )
                )
    return docs


def _split_text(text: str, max_chars: int, overlap: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    parts: list[str] = []
    paragraphs = re.split(r"\n{2,}", text)
    cur = ""
    for p in paragraphs:
        if len(cur) + len(p) + 2 <= max_chars:
            cur = f"{cur}\n\n{p}" if cur else p
        else:
            if cur:
                parts.append(cur)
            if len(p) > max_chars:  # parágrafo gigante: corta por tamanho com sobreposição
                i = 0
                while i < len(p):
                    parts.append(p[i : i + max_chars])
                    i += max_chars - overlap
                cur = ""
            else:
                cur = p
    if cur:
        parts.append(cur)
    return parts


def chunk_documents(
    docs: list[KnowledgeDocument], max_chars: int = 1400, overlap: int = 150
) -> list[Chunk]:
    chunks: list[Chunk] = []
    for doc in docs:
        if doc.doc_type == "faq":
            chunks.append(
                Chunk(
                    f"{doc.id}#0",
                    doc.id,
                    doc.title,
                    doc.metadata.get("secao"),
                    doc.content,
                    "faq",
                    doc.path,
                    {
                        "protocolo_id": doc.metadata.get("protocolo_id"),
                        "category": doc.category,
                        "tags": ",".join(doc.tags),
                    },
                )
            )
            continue
        n = 0
        for section, text in doc.sections():
            if not text:
                continue
            for piece in _split_text(text, max_chars, overlap):
                header = f"{doc.title} › {section}\n\n"
                chunks.append(
                    Chunk(
                        id=f"{doc.id}#{n}",
                        doc_id=doc.id,
                        title=doc.title,
                        section=section,
                        text=header + piece,
                        doc_type=doc.doc_type,
                        path=doc.path,
                        metadata={
                            "category": doc.category,
                            "version": doc.version,
                            "tags": ",".join(doc.tags),
                            "updated_at": doc.updated_at,
                        },
                    )
                )
                n += 1
    return chunks
