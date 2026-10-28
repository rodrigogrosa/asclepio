"""Léxico local pt-BR de termos clínicos críticos, com negação.

Serve de plano B quando o Text Analytics for Health não está configurado e também de régua de
severidade para as entidades que o Azure devolve. A busca ignora acentos e maiúsculas, mas as
posições (``start``/``end``) valem para o texto original, para a tela poder destacar o trecho.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass
from itertools import pairwise

# (padrão sem acento, rótulo, categoria, severidade). Padrões são regex sobre o texto normalizado.
_RAW: list[tuple[str, str, str, str]] = [
    # --- cardiovascular ---
    (
        r"\b(?:dor(?:es)?|aperto|pressao|peso|queimacao) (?:no|na|em|sobre o|do lado do) "
        r"(?:peito|torax|coracao|regiao do coracao)\b",
        "dor no peito",
        "cardiovascular",
        "critico",
    ),
    (r"\bdor (?:toracica|precordial)\b", "dor torácica", "cardiovascular", "critico"),
    (r"\bdor no (?:braco|ombro) esquerdo\b", "dor no braço esquerdo", "cardiovascular", "critico"),
    (
        r"\b(?:palpitacoes?|coracao (?:disparado|acelerado)|taquicardia|batedeira)\b",
        "palpitações",
        "cardiovascular",
        "atencao",
    ),
    (r"\b(?:inchaco|edema|pernas inchadas|pes inchados)\b", "inchaço", "cardiovascular", "atencao"),
    (r"\bpressao (?:muito )?(?:alta|baixa)\b", "alteração de pressão", "cardiovascular", "atencao"),
    # --- respiratório ---
    (
        r"\b(?:nao consigo respirar|nao estou conseguindo respirar|sufocando|sufocamento|"
        r"sem conseguir respirar|asfixia)\b",
        "não consegue respirar",
        "respiratorio",
        "critico",
    ),
    (
        r"\b(?:falta de ar|dispneia|dificuldade (?:para|de|em) respirar|respiracao (?:curta|dificil)|"
        r"ofegante|ofegando|sem folego|folego curto)\b",
        "falta de ar",
        "respiratorio",
        "critico",
    ),
    (
        r"\b(?:chiado|chiando|sibilo|sibilancia)(?: no peito)?\b",
        "chiado no peito",
        "respiratorio",
        "atencao",
    ),
    (r"\bengasg(?:o|ando|uei|ou)\b", "engasgo", "respiratorio", "atencao"),
    (
        r"\btosse (?:com|e) (?:sangue|escarro com sangue)\b|\bhemoptise\b",
        "tosse com sangue",
        "hemorragia",
        "critico",
    ),
    (
        r"\btosse (?:persistente|seca|forte|ha (?:\w+ )?(?:semanas|meses|dias))\b|\btossindo muito\b",
        "tosse persistente",
        "respiratorio",
        "atencao",
    ),
    (r"\btosse\b", "tosse", "respiratorio", "info"),
    # --- neurológico ---
    (
        r"\b(?:desmai(?:o|ei|ou|ar)|perdi (?:os sentidos|a consciencia)|perda de consciencia|"
        r"apaguei|sincope)\b",
        "desmaio",
        "neurologico",
        "critico",
    ),
    (
        r"\b(?:convuls(?:ao|oes|ionei|ionou)|ataque epileptico)\b",
        "convulsão",
        "neurologico",
        "critico",
    ),
    (
        r"\b(?:confusao mental|confus[oa]|desorientad[oa]|nao sei onde estou|"
        r"perdendo a memoria)\b",
        "confusão mental",
        "neurologico",
        "critico",
    ),
    (
        r"\b(?:fala enrolada|dificuldade para falar|boca torta|rosto torto|paralisia|"
        r"fraqueza (?:em um lado|no (?:braco|lado)|subita)|avc|derrame)\b",
        "sinais de AVC",
        "neurologico",
        "critico",
    ),
    (
        r"\bdor de cabeca (?:muito )?(?:forte|intensa|subita|insuportavel)|pior dor de cabeca\b",
        "dor de cabeça intensa",
        "neurologico",
        "atencao",
    ),
    (
        r"\b(?:tontura|tonteira|vertigem|cabeca (?:girando|rodando))\b",
        "tontura",
        "neurologico",
        "atencao",
    ),
    # --- sangramento ---
    (
        r"\b(?:sangramento|sangrando|hemorragia|sangue (?:nas fezes|na urina|no vomito)|"
        r"vomit(?:o|ando) (?:com )?sangue|fezes pretas)\b",
        "sangramento",
        "hemorragia",
        "critico",
    ),
    # --- infeccioso / febre ---
    (
        r"\bfebre (?:muito )?alta\b|\bfebre de (?:39|40)\b|\b(?:39|40) graus\b",
        "febre alta",
        "infeccioso",
        "critico",
    ),
    (r"\b(?:febre|febril|calafrios?)\b", "febre", "infeccioso", "atencao"),
    # --- saúde mental ---
    (
        r"\b(?:ideacao suicida|suicidio|quero morrer|vontade de morrer|pensando em me matar|"
        r"tirar (?:a )?minha vida|nao quero mais viver|me machucar|"
        r"pens(?:o|ando|ei) em me matar|vontade de me matar)\b",
        "ideação suicida",
        "saude_mental",
        "critico",
    ),
    (
        r"\b(?:desesper(?:o|ado|ada)|crise de panico|ataque de panico|ansiedade forte)\b",
        "sofrimento psíquico",
        "saude_mental",
        "atencao",
    ),
    # --- alergia grave ---
    (
        r"\b(?:garganta fechando|lingua inchada|labios inchados|anafilaxia|reacao alergica grave)\b",
        "reação alérgica grave",
        "alergia",
        "critico",
    ),
    # --- dor intensa, trauma e outros ---
    (
        r"\bdor (?:insuportavel|muito forte|intensa|lancinante|aguda)\b",
        "dor intensa",
        "dor",
        "atencao",
    ),
    (
        r"\b(?:dor (?:forte )?(?:na|no) (?:barriga|abdomen|abdome)|dor abdominal)\b",
        "dor abdominal",
        "dor",
        "atencao",
    ),
    (
        r"\b(?:sofri uma queda|cai (?:da|na|no|de)|bati a cabeca|queda recente)\b",
        "queda/trauma",
        "trauma",
        "atencao",
    ),
    (r"\b(?:vomit(?:o|ando|ei)|nauseas?|enjoo)\b", "náusea/vômito", "gastrointestinal", "info"),
    (r"\bperda de peso\b|\bemagreci\b", "perda de peso", "geral", "atencao"),
    # --- fadiga ---
    (
        r"\b(?:cansaco|cansad[oa]|fadiga|fraqueza|sem energia|exaust[oa]|esgotad[oa]|indisposicao)\b",
        "cansaço/fadiga",
        "geral",
        "atencao",
    ),
    (r"\b(?:diabetes|hipertensao|colesterol)\b", "condição crônica", "geral", "info"),
]

_PATTERNS = [(re.compile(p), label, cat, sev) for p, label, cat, sev in _RAW]
_SEV = {"info": 0, "atencao": 1, "critico": 2}

# Sinal de negação até 2 palavras antes do termo, na mesma oração (recortada em _is_negated)
_NEG_PRE = re.compile(
    r"\b(?:nega(?:r|ndo|m)?|nego|negou|sem|nunca|nenhum[a]?|ausencia de|ausente|descarta|"
    r"livre de|isento de|nem|nao)\s+(?:\S+ ){0,2}$"
)
_NEG_POST = re.compile(
    r"^\W{0,3}(?:nao|negativo|nada)\b[\s,]*(?:doutor|doutora|doc|obrigad[oa])?\W{0,2}(?:$|[.?!;])"
)
_CLAUSE_BREAK = re.compile(
    r"[.;!?:]|\b(?:mas|porem|contudo|entretanto|so que|exceto)\b|,\s*(?:e|mas)\b"
)


_LIST_JOINER = re.compile(r"\s*(?:,\s*)?(?:e |ou |nem )?\s*")


@dataclass
class CriticalTerm:
    text: str
    label: str
    category: str
    severity: str
    negated: bool
    start: int
    end: int
    source: str = "lexicon"

    def to_dict(self) -> dict:
        return asdict(self)


def fold(text: str) -> str:
    """Minúsculas e sem acento, **mantendo o comprimento** (posições valem no texto original)."""
    out = []
    for ch in text:
        d = unicodedata.normalize("NFD", ch)
        out.append(d[0].lower() if d else ch)
    return "".join(out)


def _is_negated(norm: str, start: int, end: int) -> bool:
    # só a oração do termo conta: recorta a partir da última quebra de oração antes dele
    before = norm[max(0, start - 60) : start]
    breaks = list(_CLAUSE_BREAK.finditer(before))
    if breaks:
        before = before[breaks[-1].end() :]
    before = re.sub(
        r"\bnao\s*,", " ", before
    )  # "não, eu tenho…": resposta, não nega o que vem depois
    before = re.sub(r"[\s,]+", " ", before).strip() + " "
    if _NEG_PRE.search(before):
        return True
    return bool(_NEG_POST.match(norm[end : end + 25]))


def find_critical_terms(text: str) -> list[CriticalTerm]:
    """Termos críticos do texto, do mais ao menos severo em caso de sobreposição, em ordem de posição."""
    norm = fold(text)
    cands = []
    for rx, label, cat, sev in _PATTERNS:
        for m in rx.finditer(norm):
            cands.append((m.start(), m.end(), label, cat, sev))
    cands.sort(key=lambda c: (-_SEV[c[4]], -(c[1] - c[0]), c[0]))
    taken: list[tuple[int, int]] = []
    out: list[CriticalTerm] = []
    for s, e, label, cat, sev in cands:
        if any(s < b and a < e for a, b in taken):
            continue
        taken.append((s, e))
        out.append(CriticalTerm(text[s:e], label, cat, sev, _is_negated(norm, s, e), s, e))
    out.sort(key=lambda t: t.start)
    # "nega febre, tosse ou dor no peito": a negação vale para a lista ligada por vírgula/e/ou/nem
    for prev, cur in pairwise(out):
        if prev.negated and _LIST_JOINER.fullmatch(norm[prev.end : cur.start]):
            cur.negated = True
    return out


def classify_entity(text: str, category: str = "", negated: bool = False) -> tuple[str, str, str]:
    """Severidade de uma entidade do Azure (texto + categoria) → (severidade, rótulo, categoria).

    Se o léxico reconhece o texto usa a severidade dele; senão sintoma/diagnóstico sem negação
    vira ``info`` (aparece na tela, não vira alerta).
    """
    hits = find_critical_terms(text)
    if hits:
        best = max(hits, key=lambda h: _SEV[h.severity])
        sev, label, cat = best.severity, best.label, best.category
    else:
        sev, label, cat = "info", text, category or "geral"
    return ("info" if negated else sev), label, cat
