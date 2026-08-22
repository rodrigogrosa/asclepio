"""Políticas de segurança declaradas em código (policy-as-code) — fáceis de ler, testar e auditar.

1. **RBAC**: matriz papel → permissões. As rotas declaram a permissão que exigem
   (``require_permission("workflows:decide")``) em vez de checar papéis soltos.
2. **Senhas**: política mínima (tamanho, maiúscula, minúscula, dígito, símbolo) e bloqueio
   temporário após N falhas (mitiga força bruta).
3. **Sessão/Token**: JWT curto (configurável), assinatura HS256 com segredo forte,
   claims mínimas (sub, role, jti, iat, exp) — sem dados sensíveis no token.
4. **Assistente**: papéis que podem conversar/executar fluxos e quem pode *aprovar*
   (validação humana é exclusiva de médico/admin).

Documentação completa em ``docs/POLITICAS.md``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

Role = str  # "admin" | "medico" | "enfermagem" | "auditor"

ROLES: tuple[Role, ...] = ("admin", "medico", "enfermagem", "auditor")

# Permissões nomeadas como recurso:ação
PERMISSIONS: dict[Role, frozenset[str]] = {
    "admin": frozenset({"*"}),
    "medico": frozenset(
        {
            "dashboard:read",
            "patients:read",
            "patients:context",
            "assistant:chat",
            "assistant:history",
            "assistant:feedback",
            "workflows:run",
            "workflows:read",
            "workflows:decide",
            "alerts:read",
            "alerts:ack",
            "knowledge:read",
            "knowledge:search",
            "model:read",
        }
    ),
    "enfermagem": frozenset(
        {
            "dashboard:read",
            "patients:read",
            "patients:context",
            "assistant:chat",
            "assistant:history",
            "assistant:feedback",
            "workflows:run",
            "workflows:read",
            "alerts:read",
            "alerts:ack",
            "knowledge:read",
            "knowledge:search",
            "model:read",
        }
    ),
    "auditor": frozenset(
        {
            "dashboard:read",
            "audit:read",
            "model:read",
            "knowledge:read",
            "workflows:read",
            "alerts:read",
        }
    ),
}

ADMIN_ONLY = frozenset({"knowledge:reindex", "model:switch", "users:manage", "audit:read"})


def has_permission(role: Role, permission: str) -> bool:
    perms = PERMISSIONS.get(role, frozenset())
    return "*" in perms or permission in perms


def permissions_for(role: Role) -> list[str]:
    perms = PERMISSIONS.get(role, frozenset())
    if "*" in perms:
        all_perms = set().union(*[p for r, p in PERMISSIONS.items() if r != "admin"]) | ADMIN_ONLY
        return sorted(all_perms)
    return sorted(perms)


@dataclass(frozen=True)
class PasswordPolicy:
    min_length: int = 10
    require_upper: bool = True
    require_lower: bool = True
    require_digit: bool = True
    require_symbol: bool = True

    def validate(self, password: str) -> list[str]:
        problems: list[str] = []
        if len(password) < self.min_length:
            problems.append(f"mínimo de {self.min_length} caracteres")
        if self.require_upper and not re.search(r"[A-ZÀ-Ü]", password):
            problems.append("ao menos uma letra maiúscula")
        if self.require_lower and not re.search(r"[a-zà-ü]", password):
            problems.append("ao menos uma letra minúscula")
        if self.require_digit and not re.search(r"\d", password):
            problems.append("ao menos um dígito")
        if self.require_symbol and not re.search(r"[^\w\s]", password):
            problems.append("ao menos um símbolo")
        return problems


DEFAULT_PASSWORD_POLICY = PasswordPolicy()
