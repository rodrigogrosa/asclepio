"""Anonimização de PII (dados pessoais) em texto clínico livre e registros estruturados.

Princípio do projeto: **a LLM nunca recebe dado identificável**. Tudo que sai do
banco (prontuário, evoluções, nomes) passa por aqui antes de virar prompt.

Estratégia (didática e auditável):
1. Padrões determinísticos (regex) para identificadores fortes: CPF, RG, CNS, telefone,
   e-mail, CEP, datas de nascimento, endereços.
2. Padrões contextuais para nomes: "Paciente: Fulano", "Sr./Sra./Dr./Dra. Fulano",
   "mãe: Fulana", "acompanhante: ...".
3. Lista de nomes conhecidos (opcional) — ex.: nomes dos pacientes do banco — para
   substituição garantida.
4. Pseudonimização consistente: o mesmo valor vira sempre o mesmo placeholder dentro de
   um texto (ex.: ``[PACIENTE-1]``), preservando coerência para a LLM.

O resultado carrega a lista de entidades encontradas (tipo, trecho, substituto) para
fins de auditoria e explicabilidade (o frontend mostra "N dados pessoais redigidos").
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Padrões
# ---------------------------------------------------------------------------

_CPF = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")
_CNS = re.compile(r"\b(?:CNS|Cart[ãa]o\s+SUS)[:\s]*\d{3}\s?\d{4}\s?\d{4}\s?\d{4}\b", re.IGNORECASE)
_CNS_BARE = re.compile(r"\b[12789]\d{14}\b")
_RG = re.compile(r"\bRG[:\s]*\d{1,2}\.?\d{3}\.?\d{3}-?[\dXx]?\b", re.IGNORECASE)
_PHONE = re.compile(r"(?:\+55\s?)?\(?\b\d{2}\)?\s?9?\d{4}-?\d{4}\b")
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_CEP = re.compile(r"\b\d{5}-?\d{3}\b")
_BIRTHDATE = re.compile(
    r"(?:nascid[oa]\s+em|data\s+de\s+nascimento|DN|D\.N\.|nasc\.?)[:\s]*"
    r"(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})",
    re.IGNORECASE,
)
_ADDRESS = re.compile(
    r"\b(?:Rua|R\.|Avenida|Av\.|Alameda|Al\.|Travessa|Tv\.|Rodovia|Rod\.|Estrada|Praça)\s+"
    r"[A-ZÀ-Üa-zà-ü0-9][^,\n;.]{2,60}(?:,\s*(?:n[ºo°]?\.?\s*)?\d{1,5})?(?:\s*[-–,]\s*[^,\n;.]{2,40}){0,3}",
)
_NAME_TOKEN = r"[A-ZÀ-Ü][a-zà-ü']+(?:\s+(?:d[aeo]s?\s+)?[A-ZÀ-Ü][a-zà-ü']+){1,4}"
_CONTEXT_NAME = re.compile(
    r"(?P<prefix>\b(?:Paciente|Nome|Nome\s+completo|Sr\.?|Sra\.?|Srta\.?|Dr\.?|Dra\.?|"
    r"M[ãa]e|Pai|Acompanhante|Respons[áa]vel|Esposa|Esposo|Filh[oa]|Contato)\s*:?\s*)"
    r"(?P<name>" + _NAME_TOKEN + ")",
)

_PLACEHOLDER_BASE = {
    "CPF": "[CPF]",
    "CNS": "[CNS]",
    "RG": "[RG]",
    "TELEFONE": "[TELEFONE]",
    "EMAIL": "[EMAIL]",
    "CEP": "[CEP]",
    "DATA_NASCIMENTO": "[DATA_NASC]",
    "ENDERECO": "[ENDERECO]",
    "NOME": "[NOME]",
    "PACIENTE": "[PACIENTE]",
    "PROFISSIONAL": "[PROFISSIONAL]",
}

# Palavras que parecem nome próprio mas são termos clínicos comuns (evita falso positivo)
_CLINICAL_STOPWORDS = {
    "Paciente",
    "Pronto Socorro",
    "Clínica Médica",
    "Unidade Terapia",
    "Terapia Intensiva",
    "Sinais Vitais",
    "Exame Físico",
    "História Clínica",
    "Hipótese Diagnóstica",
    "Conduta",
    "Ausculta Pulmonar",
    "Ausculta Cardíaca",
    "Estado Geral",
    "Bom Estado",
    "Regular Estado",
    "Mau Estado",
    "Ritmo Cardíaco",
    "Raio X",
    "Sem Alterações",
    "Sem Queixas",
    "Mantém Quadro",
}


@dataclass
class PIIEntity:
    type: str
    original: str
    replacement: str
    start: int
    end: int


@dataclass
class AnonymizationResult:
    text: str
    entities: list[PIIEntity] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.entities)

    @property
    def by_type(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for e in self.entities:
            out[e.type] = out.get(e.type, 0) + 1
        return out


class Anonymizer:
    """Anonimizador determinístico de texto clínico.

    Parameters
    ----------
    known_names:
        Nomes completos conhecidos (ex.: pacientes e profissionais do banco) que devem
        ser substituídos mesmo sem contexto textual.
    professional_names:
        Nomes de profissionais (substituídos por ``[PROFISSIONAL]`` em vez de ``[PACIENTE]``).
    pseudonymize:
        Se True, usa placeholders numerados consistentes (``[PACIENTE-1]``) em vez de
        placeholder genérico; útil quando o texto menciona mais de uma pessoa.
    """

    def __init__(
        self,
        known_names: list[str] | None = None,
        professional_names: list[str] | None = None,
        pseudonymize: bool = False,
    ) -> None:
        self.known_names = sorted(
            {n.strip() for n in (known_names or []) if n and len(n.strip()) > 3},
            key=len,
            reverse=True,
        )
        self.professional_names = {n.strip() for n in (professional_names or []) if n}
        self.pseudonymize = pseudonymize

    # -- API pública -------------------------------------------------------
    def anonymize(self, text: str) -> AnonymizationResult:
        if not text:
            return AnonymizationResult(text="")
        entities: list[PIIEntity] = []
        out = text
        out = self._replace(out, _CNS, "CNS", entities)
        out = self._replace(out, _CNS_BARE, "CNS", entities)
        out = self._replace(out, _CPF, "CPF", entities)
        out = self._replace(out, _RG, "RG", entities)
        out = self._replace(out, _EMAIL, "EMAIL", entities)
        out = self._replace(out, _PHONE, "TELEFONE", entities)
        out = self._replace_birthdate(out, entities)
        out = self._replace(out, _ADDRESS, "ENDERECO", entities)
        out = self._replace(out, _CEP, "CEP", entities)
        out = self._replace_known_names(out, entities)
        out = self._replace_context_names(out, entities)
        return AnonymizationResult(text=out, entities=entities)

    def anonymize_record(
        self,
        record: dict[str, Any],
        text_fields: tuple[str, ...] = ("text", "note", "texto", "observacao"),
    ) -> tuple[dict[str, Any], int]:
        """Anonimiza recursivamente os campos textuais de um dicionário. Retorna (registro, nº de entidades)."""
        total = 0

        def walk(obj: Any) -> Any:
            nonlocal total
            if isinstance(obj, dict):
                return {
                    k: (
                        self._anon_str(v, total_ref)
                        if (k in text_fields and isinstance(v, str))
                        else walk(v)
                    )
                    for k, v in obj.items()
                }
            if isinstance(obj, list):
                return [walk(i) for i in obj]
            return obj

        total_ref = [0]
        new = walk(record)
        total = total_ref[0]
        return new, total

    def _anon_str(self, s: str, total_ref: list[int]) -> str:
        r = self.anonymize(s)
        total_ref[0] += r.count
        return r.text

    # -- internos ----------------------------------------------------------
    def _placeholder(self, kind: str, original: str) -> str:
        base = _PLACEHOLDER_BASE.get(kind, f"[{kind}]")
        if not self.pseudonymize:
            return base
        h = hashlib.sha256(original.strip().lower().encode()).hexdigest()[:4]
        return base[:-1] + f"-{h}]"

    def _replace(
        self, text: str, pattern: re.Pattern[str], kind: str, entities: list[PIIEntity]
    ) -> str:
        def sub(m: re.Match[str]) -> str:
            original = m.group(0)
            # Evita tratar valores de exame/datas simples como CEP/telefone: exige contexto mínimo
            if kind == "CEP" and not re.search(
                r"\b(CEP|cep)\b", text[max(0, m.start() - 12) : m.start()]
            ):
                return original
            if (
                kind == "TELEFONE"
                and not re.search(
                    r"(tel|cel|fone|whats|contato|ligar)",
                    text[max(0, m.start() - 25) : m.start()],
                    re.IGNORECASE,
                )
                and "(" not in original
                and "-" not in original
            ):
                return original
            rep = self._placeholder(kind, original)
            entities.append(PIIEntity(kind, original, rep, m.start(), m.end()))
            return rep

        return pattern.sub(sub, text)

    def _replace_birthdate(self, text: str, entities: list[PIIEntity]) -> str:
        def sub(m: re.Match[str]) -> str:
            full = m.group(0)
            date = m.group(1)
            rep = full.replace(date, self._placeholder("DATA_NASCIMENTO", date))
            entities.append(PIIEntity("DATA_NASCIMENTO", date, "[DATA_NASC]", m.start(1), m.end(1)))
            return rep

        return _BIRTHDATE.sub(sub, text)

    def _replace_known_names(self, text: str, entities: list[PIIEntity]) -> str:
        for name in self.known_names:
            if name in text:
                kind = "PROFISSIONAL" if name in self.professional_names else "PACIENTE"
                rep = self._placeholder(kind, name)
                for m in re.finditer(re.escape(name), text):
                    entities.append(PIIEntity(kind, name, rep, m.start(), m.end()))
                text = text.replace(name, rep)
            # também apenas primeiro + último nome (ex.: "Maria Souza" de "Maria Aparecida Souza")
            parts = name.split()
            if len(parts) > 2:
                short = f"{parts[0]} {parts[-1]}"
                if short in text:
                    kind = "PROFISSIONAL" if name in self.professional_names else "PACIENTE"
                    rep = self._placeholder(kind, name)
                    for m in re.finditer(re.escape(short), text):
                        entities.append(PIIEntity(kind, short, rep, m.start(), m.end()))
                    text = text.replace(short, rep)
        return text

    def _replace_context_names(self, text: str, entities: list[PIIEntity]) -> str:
        def sub(m: re.Match[str]) -> str:
            prefix, name = m.group("prefix"), m.group("name")
            if name in _CLINICAL_STOPWORDS or name.startswith("["):
                return m.group(0)
            low = prefix.strip().lower().rstrip(":").strip()
            if low.startswith(("dr", "dra")):
                kind = "PROFISSIONAL"
            elif low in {
                "paciente",
                "nome",
                "nome completo",
                "sr",
                "sr.",
                "sra",
                "sra.",
                "srta",
                "srta.",
            }:
                kind = "PACIENTE"
            else:
                kind = "NOME"
            rep = self._placeholder(kind, name)
            entities.append(PIIEntity(kind, name, rep, m.start("name"), m.end("name")))
            return f"{prefix}{rep}"

        return _CONTEXT_NAME.sub(sub, text)


def detect_pii(text: str) -> list[PIIEntity]:
    """Atalho: retorna as entidades de PII detectadas sem alterar o texto."""
    return Anonymizer().anonymize(text).entities


def contains_pii(text: str) -> bool:
    return bool(detect_pii(text))
