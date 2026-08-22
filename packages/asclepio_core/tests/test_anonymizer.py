from asclepio_core.anonymizer import Anonymizer, contains_pii, detect_pii


def test_anonymizes_strong_identifiers():
    t = "Paciente: João Carlos da Silva, CPF 123.456.789-09, tel (11) 98765-4321, e-mail joao@gmail.com, CNS 898001234567890, nascido em 12/03/1959."
    r = Anonymizer().anonymize(t)
    assert "123.456.789-09" not in r.text
    assert "98765-4321" not in r.text
    assert "joao@gmail.com" not in r.text
    assert "12/03/1959" not in r.text
    assert "João Carlos" not in r.text
    assert {"CPF", "TELEFONE", "EMAIL", "DATA_NASCIMENTO", "PACIENTE"} <= set(r.by_type)


def test_known_names_and_professionals():
    a = Anonymizer(
        known_names=["Maria Aparecida Souza", "Dra. Ana Beatriz Souza"],
        professional_names=["Dra. Ana Beatriz Souza"],
    )
    r = a.anonymize(
        "Maria Aparecida Souza foi avaliada por Dra. Ana Beatriz Souza. Maria Souza segue estável."
    )
    assert "Maria" not in r.text
    assert "[PACIENTE]" in r.text and "[PROFISSIONAL]" in r.text


def test_address_does_not_swallow_next_sentence():
    r = Anonymizer().anonymize(
        "Residente à Rua das Flores, 123, São Paulo - SP. Mãe: Maria Aparecida Silva. Fim."
    )
    assert "[ENDERECO]. Mãe: [NOME]. Fim." in r.text


def test_keeps_clinical_values_intact():
    t = "PA 120/80 mmHg, FC 88 bpm, glicemia 486 mg/dL, lactato 3,4 mmol/L, K 6,4."
    r = Anonymizer().anonymize(t)
    assert r.text == t and r.count == 0


def test_pseudonymize_consistent():
    a = Anonymizer(known_names=["Carlos Eduardo Lima"], pseudonymize=True)
    r = a.anonymize("Carlos Eduardo Lima chegou. Carlos Eduardo Lima saiu.")
    toks = [e.replacement for e in r.entities]
    assert len(set(toks)) == 1 and toks[0].startswith("[PACIENTE-")


def test_record_anonymization_counts():
    a = Anonymizer()
    rec, n = a.anonymize_record(
        {"notes": [{"text": "CPF 123.456.789-09"}, {"text": "sem pii"}], "x": 1}
    )
    assert n == 1 and "[CPF]" in rec["notes"][0]["text"]


def test_detect_helpers():
    assert contains_pii("CPF 123.456.789-09")
    assert not detect_pii("lactato 2,1")
