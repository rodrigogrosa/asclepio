# Política de Segurança

Este é um projeto acadêmico (Tech Challenge FIAP) com dados **100% sintéticos**. Mesmo assim, seguimos boas práticas:

- Autenticação JWT com expiração, política de senha, bloqueio por tentativas, RBAC declarativo (`backend/asclepio_api/core/policies.py`).
- Anonimização de PII antes de qualquer chamada a LLM; guardrails de entrada/saída; trilha de auditoria com cadeia de hashes.
- Dependências verificadas na CI (`pip-audit`, `gitleaks`).

Encontrou uma vulnerabilidade? Abra uma *issue* com o rótulo `security` ou envie e-mail aos mantenedores (ver README). Não publique detalhes de exploração antes da correção.

Detalhes das políticas: `docs/POLITICAS.md`.
