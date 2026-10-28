"""Léxico de termos críticos pt-BR: severidade, posição e negação."""

from __future__ import annotations

import pytest
from asclepio_multimodal.audio.critical_terms import classify_entity, find_critical_terms


def by_label(text: str) -> dict[str, tuple[str, bool]]:
    return {t.label: (t.severity, t.negated) for t in find_critical_terms(text)}


@pytest.mark.parametrize(
    ("text", "label", "severity"),
    [
        ("Estou com dor no peito desde ontem.", "dor no peito", "critico"),
        ("Tenho falta de ar ao subir a escada.", "falta de ar", "critico"),
        ("Eu não consigo respirar direito.", "não consegue respirar", "critico"),
        ("Ela desmaiou ontem.", "desmaio", "critico"),
        ("Tem sangramento nas fezes.", "sangramento", "critico"),
        ("Ele ficou confuso e desorientado.", "confusão mental", "critico"),
        ("Está com febre alta.", "febre alta", "critico"),
        ("Às vezes penso em me matar.", "ideação suicida", "critico"),
        ("Sinto muito cansaço.", "cansaço/fadiga", "atencao"),
        ("DOR TORÁCICA há dois dias", "dor torácica", "critico"),  # acento e caixa
    ],
)
def test_termos_detectados(text, label, severity):
    assert by_label(text)[label] == (severity, False)


@pytest.mark.parametrize(
    "text",
    [
        "Nego dor no peito.",
        "Paciente nega dor no peito e febre.",
        "Não tenho falta de ar.",
        "Sem febre, sem falta de ar.",
        "Nunca desmaiei.",
        "Dor no peito? Não.",
        "Não sinto dor no peito nem falta de ar.",
        "Tem tosse, mas não tem febre.",
    ],
)
def test_negacao(text):
    terms = find_critical_terms(text)
    assert terms and all(t.negated for t in terms if t.severity != "info" and t.label != "tosse")


def test_negacao_nao_vaza_para_outra_oracao():
    terms = {t.label: t.negated for t in find_critical_terms("Nego febre, mas sinto dor no peito.")}
    assert terms == {"febre": True, "dor no peito": False}
    # "Não," é só resposta: não nega o que vem depois
    assert not find_critical_terms("Não, eu tenho palpitações.")[0].negated
    # a falta de ar afirmada logo depois de uma dor negada continua afirmada
    t = {
        x.label: x.negated for x in find_critical_terms("Nego dor no peito. Mas tenho falta de ar.")
    }
    assert t == {"dor no peito": True, "falta de ar": False}


def test_posicoes_valem_no_texto_original():
    text = "Doutora, tenho FALTA DE AR e dor no peito."
    for t in find_critical_terms(text):
        assert text[t.start : t.end] == t.text
    assert [t.text for t in find_critical_terms(text)] == ["FALTA DE AR", "dor no peito"]


def test_sobreposicao_fica_com_o_mais_grave():
    terms = find_critical_terms("Sinto aperto no peito.")
    assert [t.label for t in terms] == ["dor no peito"]


def test_classifica_entidade_do_azure():
    assert classify_entity("dor no peito", "SymptomOrSign")[0] == "critico"
    assert classify_entity("dor no peito", "SymptomOrSign", negated=True)[0] == "info"
    sev, label, cat = classify_entity("coceira", "SymptomOrSign")
    assert (sev, label, cat) == ("info", "coceira", "SymptomOrSign")
