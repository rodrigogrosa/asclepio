from pathlib import Path

from asclepio_core.knowledge import chunk_documents, load_knowledge_base
from asclepio_core.synthetic import generate_patients

KB = Path(__file__).resolve().parents[3] / "data" / "knowledge_base"


def test_load_knowledge_base_real_files():
    docs = load_knowledge_base(KB)
    ids = {d.id for d in docs}
    assert (
        "PROT-001" in ids
        and any(i.startswith("MOD-") for i in ids)
        and any(i.startswith("FAQ-") for i in ids)
    )
    prot = next(d for d in docs if d.id == "PROT-001")
    secs = [s for s, _ in prot.sections()]
    assert "Conduta" in secs and prot.doc_type == "protocolo" and prot.tags


def test_chunking_keeps_metadata():
    chunks = chunk_documents(load_knowledge_base(KB))
    assert len(chunks) > 100
    c = next(c for c in chunks if c.doc_id == "PROT-001" and c.section == "Conduta")
    assert c.text.startswith("Protocolo de Sepse") and c.doc_type == "protocolo"
    assert all(len(c.text) <= 1800 for c in chunks)


def test_synthetic_patients_deterministic_and_pii_present():
    a = generate_patients()
    b = generate_patients()
    assert [p["name"] for p in a] == [p["name"] for p in b]
    assert len(a) >= 20
    p = next(p for p in a if p["scenario"] == "sepse_pac")
    assert p["cpf"] in p["notes"][0]["text"]  # PII fictícia presente de propósito
    assert any(e["status"] == "atrasado" for e in p["exams"])
