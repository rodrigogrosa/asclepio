"""RAG: indexação da base de conhecimento no Chroma e busca com citações.

Explainability: cada resultado devolve documento, seção, score e o trecho usado —
o frontend mostra isso ao lado da resposta e a auditoria guarda os IDs das fontes.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from asclepio_core.knowledge import Chunk, KnowledgeDocument, chunk_documents, load_knowledge_base
from langchain_core.documents import Document

from ..core.config import Settings, get_settings
from ..core.logging import get_logger
from .llm import get_llm_factory

log = get_logger("rag")

COLLECTION = "asclepio_kb"


class KnowledgeService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.s = settings or get_settings()
        self.base_dir = Path(self.s.knowledge_base_dir)
        self.store_dir = Path(self.s.vectorstore_dir)
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self._docs: list[KnowledgeDocument] = []
        self._chunks: list[Chunk] = []
        self._vs = None
        self._emb_info: dict[str, str] = {}

    # ---- carga --------------------------------------------------------------
    def load(self) -> None:
        self._docs = load_knowledge_base(self.base_dir)
        self._chunks = chunk_documents(self._docs)

    @property
    def documents(self) -> list[KnowledgeDocument]:
        if not self._docs:
            self.load()
        return self._docs

    @property
    def chunks(self) -> list[Chunk]:
        if not self._chunks:
            self.load()
        return self._chunks

    def document(self, doc_id: str) -> KnowledgeDocument | None:
        return next((d for d in self.documents if d.id == doc_id), None)

    def chunk_count(self, doc_id: str) -> int:
        return sum(1 for c in self.chunks if c.doc_id == doc_id)

    def _manifest_hash(self) -> str:
        h = hashlib.sha256()
        for p in sorted(self.base_dir.rglob("*")):
            if p.is_file() and p.suffix in {".md", ".jsonl"}:
                h.update(p.name.encode())
                h.update(str(p.stat().st_mtime_ns).encode())
                h.update(str(p.stat().st_size).encode())
        h.update(json.dumps(self._emb_info, sort_keys=True).encode())
        return h.hexdigest()

    # ---- vetor -------------------------------------------------------------
    def _vectorstore(self):  # type: ignore[no-untyped-def]
        if self._vs is None:
            from langchain_chroma import Chroma

            emb, self._emb_info = get_llm_factory().embeddings()
            self._vs = Chroma(
                collection_name=COLLECTION,
                embedding_function=emb,
                persist_directory=str(self.store_dir),
                collection_metadata={"hnsw:space": "cosine"},
            )
        return self._vs

    def index_count(self) -> int:
        try:
            return self._vectorstore()._collection.count()
        except Exception:
            return 0

    def ensure_index(self, force: bool = False) -> dict[str, Any]:
        """(Re)indexa se a base mudou (hash de manifesto) ou se o índice está vazio."""
        vs = self._vectorstore()
        manifest = self.store_dir / "manifest.json"
        current = self._manifest_hash()
        if not force and manifest.exists():
            try:
                if (
                    json.loads(manifest.read_text()).get("hash") == current
                    and self.index_count() > 0
                ):
                    return {
                        "documents": len(self.documents),
                        "chunks": self.index_count(),
                        "duration_ms": 0,
                        "reindexed": False,
                    }
            except Exception:
                pass
        t0 = time.perf_counter()
        self.load()
        try:
            vs.reset_collection()
        except Exception:
            pass
        docs = [Document(page_content=c.text, metadata=self._meta(c)) for c in self.chunks]
        ids = [c.id for c in self.chunks]
        if docs:
            for i in range(0, len(docs), 64):
                vs.add_documents(docs[i : i + 64], ids=ids[i : i + 64])
        dur = int((time.perf_counter() - t0) * 1000)
        manifest.write_text(
            json.dumps(
                {
                    "hash": current,
                    "chunks": len(docs),
                    "documents": len(self.documents),
                    "embeddings": self._emb_info,
                },
                indent=2,
            )
        )
        log.info(
            "base de conhecimento indexada",
            documents=len(self.documents),
            chunks=len(docs),
            duration_ms=dur,
            embeddings=self._emb_info,
        )
        return {
            "documents": len(self.documents),
            "chunks": len(docs),
            "duration_ms": dur,
            "reindexed": True,
        }

    @staticmethod
    def _meta(c: Chunk) -> dict[str, Any]:
        m = {
            "doc_id": c.doc_id,
            "title": c.title,
            "section": c.section or "",
            "doc_type": c.doc_type,
            "path": c.path or "",
        }
        for k, v in c.metadata.items():
            if v is not None and isinstance(v, str | int | float | bool):
                m[k] = v
        return m

    # ---- busca -------------------------------------------------------------
    def search(
        self,
        query: str,
        k: int | None = None,
        doc_type: str | None = None,
        boost_doc_ids: list[str] | None = None,
        min_score: float | None = None,
    ) -> list[dict[str, Any]]:
        """Busca semântica com score de relevância (0-1) e, opcionalmente, *boost* para
        protocolos sugeridos pelas regras clínicas (ex.: paciente com gatilho de sepse → PROT-001)."""
        k = k or self.s.rag_top_k
        min_score = self.s.rag_min_score if min_score is None else min_score
        vs = self._vectorstore()
        flt = {"doc_type": doc_type} if doc_type else None
        try:
            results = vs.similarity_search_with_relevance_scores(query, k=k * 2, filter=flt)
        except Exception as exc:
            log.warning("busca vetorial falhou", error=str(exc))
            results = []
        hits: dict[str, tuple[Document, float]] = {}
        for doc, score in results:
            cid = doc.metadata.get("doc_id", "") + "|" + str(doc.metadata.get("section", ""))
            s = max(0.0, min(1.0, float(score)))
            if boost_doc_ids and doc.metadata.get("doc_id") in boost_doc_ids:
                s = min(1.0, s + 0.15)
            if cid not in hits or hits[cid][1] < s:
                hits[cid] = (doc, s)
        if boost_doc_ids:
            for pid in boost_doc_ids[:3]:
                try:
                    extra = vs.similarity_search_with_relevance_scores(
                        query, k=2, filter={"doc_id": pid}
                    )
                except Exception:
                    extra = []
                for doc, score in extra:
                    cid = (
                        doc.metadata.get("doc_id", "") + "|" + str(doc.metadata.get("section", ""))
                    )
                    s = min(1.0, max(0.0, float(score)) + 0.15)
                    if cid not in hits or hits[cid][1] < s:
                        hits[cid] = (doc, s)
        ranked = sorted(hits.values(), key=lambda x: x[1], reverse=True)
        ranked = [r for r in ranked if r[1] >= min_score][:k] or ranked[: min(2, len(ranked))]
        out: list[dict[str, Any]] = []
        for i, (doc, score) in enumerate(ranked, start=1):
            out.append(
                {
                    "id": i,
                    "source_id": doc.metadata.get("doc_id", ""),
                    "title": doc.metadata.get("title", ""),
                    "section": doc.metadata.get("section") or None,
                    "doc_type": doc.metadata.get("doc_type", "protocolo"),
                    "chunk": doc.page_content,
                    "score": round(score, 4),
                    "path": doc.metadata.get("path") or None,
                }
            )
        return out

    @staticmethod
    def format_context(citations: list[dict[str, Any]], max_chars: int = 6000) -> str:
        parts: list[str] = []
        used = 0
        for c in citations:
            head = (
                f"[{c['id']}] ({c['source_id']} — {c['title']}"
                + (f" › {c['section']}" if c.get("section") else "")
                + ")"
            )
            body = c["chunk"]
            if used + len(body) > max_chars:
                body = body[: max(0, max_chars - used)]
            parts.append(f"{head}\n{body}")
            used += len(body)
            if used >= max_chars:
                break
        return "\n\n".join(parts)


_service: KnowledgeService | None = None


def get_knowledge_service() -> KnowledgeService:
    global _service
    if _service is None:
        _service = KnowledgeService()
    return _service


def reset_knowledge_service() -> None:
    global _service
    _service = None
