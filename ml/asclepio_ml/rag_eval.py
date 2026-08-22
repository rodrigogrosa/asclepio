"""Métricas de recuperação (RAG): hit_rate@5 e MRR.

Pergunta que respondemos: "se o usuário fizer uma das perguntas do FAQ, o recuperador
traz um trecho do protocolo correto entre os 5 primeiros?" Gabarito = ``protocolo_id`` do FAQ.
Embeddings: ``nomic-embed-text`` via Ollama (o mesmo usado pelo backend); *fallback* TF-IDF
(scikit-learn) quando o Ollama não está disponível — assim os testes rodam sem rede.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from asclepio_core.knowledge import chunk_documents, load_faq, load_knowledge_base

from asclepio_ml.utils import log


def build_corpus(kb_dir: Path) -> tuple[list[str], list[str]]:
    """Retorna (textos dos chunks, doc_id de cada chunk) — sem FAQ (senão a busca seria trivial)."""
    docs = [d for d in load_knowledge_base(kb_dir) if d.doc_type != "faq"]
    chunks = chunk_documents(docs)
    return [c.text for c in chunks], [c.doc_id for c in chunks]


def load_queries(kb_dir: Path) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    faq_dir = kb_dir / "faq"
    if faq_dir.exists():
        for p in sorted(faq_dir.glob("*.jsonl")):
            for row in load_faq(p):
                if row.get("pergunta") and row.get("protocolo_id"):
                    out.append((row["pergunta"], str(row["protocolo_id"])))
    return out


def _tfidf_scores(corpus: list[str], queries: list[str]) -> np.ndarray:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    vec = TfidfVectorizer(
        ngram_range=(1, 2), sublinear_tf=True, strip_accents="unicode", lowercase=True, min_df=1
    )
    doc_matrix = vec.fit_transform(corpus)
    query_matrix = vec.transform(queries)
    return cosine_similarity(query_matrix, doc_matrix)


def _ollama_scores(corpus: list[str], queries: list[str], model: str, base_url: str) -> np.ndarray:
    from langchain_ollama import OllamaEmbeddings

    emb = OllamaEmbeddings(model=model, base_url=base_url)
    # prefixos recomendados pelo nomic-embed-text (melhoram a busca assimétrica)
    docs_v = np.array(
        emb.embed_documents([f"search_document: {t}" for t in corpus]), dtype=np.float32
    )
    q_v = np.array([emb.embed_query(f"search_query: {q}") for q in queries], dtype=np.float32)
    docs_v /= np.linalg.norm(docs_v, axis=1, keepdims=True) + 1e-9
    q_v /= np.linalg.norm(q_v, axis=1, keepdims=True) + 1e-9
    return q_v @ docs_v.T


def ranking_metrics(
    scores: np.ndarray, doc_ids: list[str], gold: list[str], k: int = 5
) -> dict[str, Any]:
    hits, rr = 0, 0.0
    for i, g in enumerate(gold):
        order = np.argsort(-scores[i])
        seen: list[str] = []
        for idx in order:  # ranking por DOCUMENTO (primeiro chunk de cada doc)
            d = doc_ids[idx]
            if d not in seen:
                seen.append(d)
            if len(seen) >= max(k, 20):
                break
        if g in seen[:k]:
            hits += 1
        if g in seen:
            rr += 1.0 / (seen.index(g) + 1)
    n = max(1, len(gold))
    return {"hit_rate_at_5": round(hits / n, 4), "mrr": round(rr / n, 4), "n_queries": len(gold)}


def evaluate_rag(
    kb_dir: Path,
    embed_model: str = "nomic-embed-text",
    base_url: str = "http://localhost:11434",
    k: int = 5,
    force_tfidf: bool = False,
) -> dict[str, Any]:
    corpus, doc_ids = build_corpus(kb_dir)
    pairs = load_queries(kb_dir)
    if not corpus or not pairs:
        return {
            "hit_rate_at_5": 0.0,
            "mrr": 0.0,
            "n_queries": 0,
            "method": "none",
            "n_chunks": len(corpus),
        }
    queries, gold = [q for q, _ in pairs], [g for _, g in pairs]
    method = "tfidf"
    scores: np.ndarray | None = None
    if not force_tfidf:
        try:
            scores = _ollama_scores(corpus, queries, embed_model, base_url)
            method = f"ollama:{embed_model}"
        except Exception as exc:
            log(
                f"[yellow]Embeddings via Ollama indisponíveis ({type(exc).__name__}); usando TF-IDF.[/]"
            )
    if scores is None:
        scores = _tfidf_scores(corpus, queries)
    out = ranking_metrics(scores, doc_ids, gold, k)
    out.update({"method": method, "n_chunks": len(corpus)})
    # bônus didático: também reportamos o TF-IDF como linha de base quando usamos embeddings
    if method != "tfidf":
        base = ranking_metrics(_tfidf_scores(corpus, queries), doc_ids, gold, k)
        out["tfidf_baseline"] = {"hit_rate_at_5": base["hit_rate_at_5"], "mrr": base["mrr"]}
    return out
