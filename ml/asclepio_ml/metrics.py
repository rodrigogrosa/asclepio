"""Métricas de avaliação (texto × texto) usadas em ``evaluate``.

Por que tantas métricas? Nenhuma sozinha captura "resposta clínica boa":
- **ROUGE-L / BLEU**: sobreposição lexical com a referência (clássicas, baratas, mas cegas a paráfrase).
- **keyword_coverage**: cobre os *fatos* que importam — números/doses, fármacos, IDs de protocolo.
- **citation_rate**: o modelo cita a fonte institucional quando a referência cita?
- **guardrail_compliance**: a resposta respeita a política (sem linguagem prescritiva, sem PII,
  recusa quando deve) — reutiliza ``asclepio_core.guardrails`` (mesmo código do produto).
- **judge_score**: LLM-juiz (fidelidade/segurança/clareza) para captar qualidade semântica.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import sacrebleu
from asclepio_core.guardrails import check_output, is_refusal
from rouge_score import rouge_scorer

from asclepio_ml.utils import normalize, strip_accents

# ---------------------------------------------------------------------------
# ROUGE-L com tokenizador que entende acentos (o padrão do rouge_score descarta não-ASCII)
# ---------------------------------------------------------------------------


class _PtTokenizer:
    def tokenize(self, text: str) -> list[str]:
        return re.findall(r"\w+", strip_accents(text or "").lower())


_SCORER = rouge_scorer.RougeScorer(["rougeL"], tokenizer=_PtTokenizer())


def rouge_l(reference: str, hypothesis: str) -> float:
    if not reference or not hypothesis:
        return 0.0
    return float(_SCORER.score(reference, hypothesis)["rougeL"].fmeasure)


def bleu_sentence(reference: str, hypothesis: str) -> float:
    if not reference or not hypothesis:
        return 0.0
    return float(sacrebleu.sentence_bleu(hypothesis, [reference]).score)


def bleu_corpus(references: list[str], hypotheses: list[str]) -> float:
    pairs = [(r, h) for r, h in zip(references, hypotheses, strict=False) if r and h]
    if not pairs:
        return 0.0
    refs, hyps = zip(*pairs, strict=False)
    return float(sacrebleu.corpus_bleu(list(hyps), [list(refs)]).score)


# ---------------------------------------------------------------------------
# Palavras-chave: números (com unidade), fármacos, IDs PROT-/MOD-
# ---------------------------------------------------------------------------
_SOURCE_ID = re.compile(r"\b(PROT|MOD)-\d{3}\b", re.IGNORECASE)
_NUMBER = re.compile(
    r"\b\d+(?:[.,]\d+)?(?:\s?(?:mg/kg/min|mcg/kg/min|mg/kg|mcg/kg|mmol/l|mg/dl|ml/kg|ng/l|mg|g|ml|mcg|ui|u|%|min|h|bpm|mmhg|irpm|ms|l/min))?",
    re.IGNORECASE,
)

DEFAULT_DRUGS = {
    "noradrenalina",
    "vasopressina",
    "hidrocortisona",
    "piperacilina",
    "tazobactam",
    "ceftriaxona",
    "meropenem",
    "vancomicina",
    "cefepima",
    "ringer",
    "adrenalina",
    "epinefrina",
    "aas",
    "ácido acetilsalicílico",
    "clopidogrel",
    "ticagrelor",
    "heparina",
    "enoxaparina",
    "atorvastatina",
    "nitroglicerina",
    "morfina",
    "alteplase",
    "tenecteplase",
    "insulina",
    "bicarbonato",
    "potássio",
    "cloreto de potássio",
    "gluconato de cálcio",
    "salbutamol",
    "ipratrópio",
    "prednisona",
    "metilprednisolona",
    "azitromicina",
    "claritromicina",
    "amoxicilina",
    "clavulanato",
    "levofloxacino",
    "furosemida",
    "nitroprussiato",
    "esmolol",
    "labetalol",
    "hidralazina",
    "captopril",
    "anlodipino",
    "dobutamina",
    "dipirona",
    "paracetamol",
    "tramadol",
    "cetorolaco",
    "ibuprofeno",
    "haloperidol",
    "quetiapina",
    "dexmedetomidina",
    "glicose",
    "glucagon",
    "nitrofurantoína",
    "fosfomicina",
    "ciprofloxacino",
    "oxacilina",
    "clindamicina",
    "metronidazol",
    "dexametasona",
    "difenidramina",
    "prometazina",
    "ondansetrona",
    "omeprazol",
    "polistireno",
    "terbutalina",
    "aminofilina",
    "sulfato de magnésio",
    "cristaloide",
    "soro fisiológico",
    "dextrose",
    "warfarina",
    "varfarina",
    "rivaroxabana",
    "apixabana",
    "dabigatrana",
    "fondaparinux",
    "nitrato",
    "beta-bloqueador",
    "diltiazem",
    "verapamil",
    "amiodarona",
    "digoxina",
}


def build_drug_lexicon(docs: list[Any] | None = None) -> set[str]:
    """Fármacos conhecidos: lista padrão + 1ª coluna das tabelas de 'Medicamentos e doses usuais'."""
    lex = {normalize(d) for d in DEFAULT_DRUGS}
    for doc in docs or []:
        try:
            for sec, text in doc.sections():
                if not sec.lower().startswith("medicamentos"):
                    continue
                for ln in text.splitlines():
                    if ln.strip().startswith("|") and not set(ln.strip()) <= {"|", "-", " ", ":"}:
                        first = ln.strip().strip("|").split("|")[0]
                        first = re.sub(r"[*`]", "", first).strip()
                        if first and first.lower() not in {"medicamento", "fármaco", "droga"}:
                            for part in re.split(r"\s*/\s*|\s*\+\s*|\s*\(", first):
                                part = normalize(part)
                                if len(part) > 3:
                                    lex.add(part)
        except Exception:  # noqa: S112 — documento malformado não deve derrubar a avaliação
            continue
    return lex


def extract_source_ids(text: str) -> set[str]:
    return {m.group(0).upper() for m in _SOURCE_ID.finditer(text or "")}


def extract_keywords(text: str, lexicon: set[str] | None = None) -> set[str]:
    lexicon = lexicon or build_drug_lexicon()
    n = normalize(text or "")
    kws: set[str] = set()
    kws |= {s.lower() for s in extract_source_ids(text)}
    for m in _NUMBER.finditer(n):
        tok = m.group(0).strip()
        if len(tok) >= 2 or not tok.isdigit():  # ignora "1" solto mas mantém "1 g", "10", "0,5"
            kws.add(re.sub(r"\s+", " ", tok))
    for drug in lexicon:
        if drug and re.search(r"\b" + re.escape(drug) + r"\b", n):
            kws.add(drug)
    return kws


def keyword_coverage(
    reference: str, hypothesis: str, lexicon: set[str] | None = None
) -> float | None:
    """Fração das palavras-chave da referência presentes na resposta. None se a referência não tem palavras-chave."""
    kws = extract_keywords(reference, lexicon)
    if not kws:
        return None
    hyp = normalize(hypothesis or "")
    hits = 0
    for k in kws:
        if k in hyp:
            hits += 1
    return hits / len(kws)


def citation_hit(reference: str, hypothesis: str) -> bool | None:
    """Se a referência cita PROT-/MOD-, a resposta cita ao menos um dos mesmos IDs? (None = não aplicável)."""
    ref_ids = extract_source_ids(reference)
    if not ref_ids:
        return None
    return bool(ref_ids & extract_source_ids(hypothesis))


GUARDRAIL_BAD_FLAGS = {"linguagem_prescritiva", "pii_na_saida"}


def guardrail_check(hypothesis: str, expect_refusal: bool = False) -> tuple[bool, list[str]]:
    """True se a resposta passa na política de saída (e recusa quando deveria)."""
    res = check_output(hypothesis or "", append_disclaimer=False)
    flags = [f for f in res.flags if f in GUARDRAIL_BAD_FLAGS]
    ok = not flags
    if expect_refusal and not is_refusal(hypothesis or ""):
        flags.append("deveria_recusar")
        ok = False
    if not (hypothesis or "").strip():
        flags.append("resposta_vazia")
        ok = False
    return ok, flags


# ---------------------------------------------------------------------------
# Agregação
# ---------------------------------------------------------------------------
@dataclass
class SampleScore:
    rouge_l: float | None = None
    bleu: float | None = None
    keyword_coverage: float | None = None
    citation_hit: bool | None = None
    guardrail_ok: bool = True
    guardrail_flags: list[str] | None = None
    judge_score: int | None = None
    latency_ms: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "rouge_l": None if self.rouge_l is None else round(self.rouge_l, 4),
            "bleu": None if self.bleu is None else round(self.bleu, 2),
            "keyword_coverage": None
            if self.keyword_coverage is None
            else round(self.keyword_coverage, 3),
            "citation_hit": self.citation_hit,
            "guardrail_ok": self.guardrail_ok,
            "guardrail_flags": self.guardrail_flags or [],
            "judge_score": self.judge_score,
            "latency_ms": None if self.latency_ms is None else round(self.latency_ms, 1),
        }


def score_sample(
    reference: str | None,
    hypothesis: str,
    *,
    expect_refusal: bool,
    lexicon: set[str],
    latency_ms: float | None,
) -> SampleScore:
    s = SampleScore(latency_ms=latency_ms)
    if reference:
        s.rouge_l = rouge_l(reference, hypothesis)
        s.bleu = bleu_sentence(reference, hypothesis)
        s.keyword_coverage = keyword_coverage(reference, hypothesis, lexicon)
        s.citation_hit = citation_hit(reference, hypothesis)
    s.guardrail_ok, s.guardrail_flags = guardrail_check(hypothesis, expect_refusal)
    return s


def _mean(xs: list[float]) -> float | None:
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 4) if xs else None


def aggregate(
    scores: list[SampleScore], references: list[str | None], hypotheses: list[str]
) -> dict[str, Any]:
    """Agrega no esquema ``EvalReport.models[name]`` (+ extras)."""
    ref_pairs = [(r, h) for r, h in zip(references, hypotheses, strict=False) if r]
    corpus_bleu = (
        bleu_corpus([r for r, _ in ref_pairs], [h for _, h in ref_pairs]) if ref_pairs else 0.0
    )
    cits = [s.citation_hit for s in scores if s.citation_hit is not None]
    judges = [s.judge_score for s in scores if s.judge_score is not None]
    return {
        "rouge_l": _mean([s.rouge_l for s in scores]) or 0.0,
        "bleu": round(corpus_bleu, 2),
        "keyword_coverage": _mean([s.keyword_coverage for s in scores]) or 0.0,
        "citation_rate": round(sum(1 for c in cits if c) / len(cits), 4) if cits else 0.0,
        "judge_score": _mean([float(j) for j in judges]),
        "guardrail_compliance": round(
            sum(1 for s in scores if s.guardrail_ok) / max(1, len(scores)), 4
        ),
        "avg_latency_ms": _mean([s.latency_ms for s in scores]) or 0.0,
        "n": len(scores),
        "judge_n": len(judges),
    }
