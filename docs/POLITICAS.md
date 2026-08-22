# Políticas de Segurança, Acesso e Uso do Assistente

> Políticas **em código** (`backend/asclepio_api/core/policies.py`, `asclepio_core/guardrails.py`, `core/audit.py`) e testadas (`backend/tests`). Este documento explica o **porquê** e o **como**.

## 1. Autenticação
| Política | Implementação |
|---|---|
| Credenciais institucionais (e-mail + senha) | `POST /auth/login`; senhas com **bcrypt** (custo 12). |
| Política de senha: ≥ 10 caracteres, maiúscula, minúscula, dígito e símbolo | `PasswordPolicy.validate()`; aplicada ao seed e a qualquer criação/troca de senha. |
| Bloqueio temporário após **5** tentativas inválidas (**15 min**) | contadores `failed_attempts`/`locked_until` no usuário; `423 Locked`. Registrado em auditoria (`auth.login_failed`). |
| Rate limit no login (10/min por IP) e global (60/min) | `slowapi`; cabeçalhos `X-RateLimit-*`. |
| Sessão: JWT HS256 com `sub`, `role`, `jti`, `iat`, `exp`, `iss`; expira em 8 h | `core/security.py`. Tokens emitidos **antes da última troca de senha** são rejeitados. Logout é auditado (stateless). |
| Segredo forte obrigatório em produção | `get_settings()` recusa `SECRET_KEY` padrão quando `APP_ENV=production`. |

## 2. Autorização (RBAC)
Permissões nomeadas `recurso:ação`; cada rota declara `require_permission(...)`.

| Papel | Pode | Não pode |
|---|---|---|
| `admin` | tudo (inclui reindexar, trocar modelo, ler auditoria) | — |
| `medico` | pacientes, contexto anonimizado, assistente, fluxos (executar **e aprovar/rejeitar**), alertas (ler/ack), conhecimento, modelo | auditoria, reindexar, trocar modelo |
| `enfermagem` | pacientes, assistente, fluxos (executar), alertas (ler/ack), conhecimento, modelo | **aprovar** fluxos, auditoria |
| `auditor` | auditoria, dashboard, modelo, conhecimento, leitura de fluxos/alertas | dados clínicos de pacientes, assistente |

A **validação humana** de um fluxo é exclusiva de médico/admin — é o "humano no circuito" exigido pelo desafio.

## 3. Dados pessoais (LGPD)
- **Minimização**: a LLM recebe apenas idade/sexo/setor + dados clínicos; nunca nome, MRN, CPF, telefone, endereço.
- **Anonimização automática** (`asclepio_core.anonymizer`) de CPF, CNS, RG, telefone, e-mail, CEP, endereço, data de nascimento, nomes (contexto + lista de nomes conhecidos) — nas evoluções, na pergunta do usuário e na resposta do modelo. A UI mostra quantos dados foram redigidos e o texto exato enviado.
- **Dados sintéticos**: nenhum dado real; PII fictícia é inserida de propósito para demonstrar a anonimização.
- **Retenção**: conversas pertencem ao usuário (podem ser apagadas por ele); auditoria é permanente e imutável.

## 4. Limites de atuação do assistente (guardrails)
| Situação | Comportamento |
|---|---|
| Pedido de **prescrever/decidir/autorizar** diretamente | Intenção `prescricao`: recusa cordial + informação do protocolo com fonte + necessidade de validação médica. |
| **Prompt injection** ("ignore suas instruções", "revele o system prompt", "você agora é…") | **Bloqueio**, resposta padrão, evento `assistant.blocked` na auditoria. |
| Tema **fora de escopo** | Redireciona ao escopo clínico/institucional sem responder ao pedido. |
| Resposta com **linguagem prescritiva imperativa** ("prescrevo", "administre 2 g") | Reescrita como sugestão ("o protocolo sugere…", "considerar…"); flag `linguagem_prescritiva`. |
| Resposta sem **aviso de validação humana** | Aviso adicionado automaticamente. |
| Resposta com **PII** | Redigida; flag `pii_na_saida`. |
| Sem fonte recuperada | Flag `sem_fontes`; confiança `baixa`; texto sinaliza informação geral. |
| Nos fluxos: sugestão reprovada pelos guardrails | Regenera **uma vez** com feedback; se persistir, ajusta e sinaliza. |

## 5. Auditoria e rastreabilidade
- Toda ação relevante vira um registro **append-only** em `audit_log` com `prev_hash` e `hash` (SHA-256 do registro canônico + hash anterior). `GET /audit/verify` recomputa a cadeia e aponta onde quebrou (testado com adulteração direta no banco).
- Cada requisição tem `X-Request-ID` (= `trace_id`) propagado para logs, auditoria, mensagens, fluxos e traces do Langfuse.
- Eventos: `auth.login`, `auth.login_failed`, `auth.logout`, `patient.view`, `assistant.chat`, `assistant.blocked`, `assistant.feedback`, `workflow.start`, `workflow.alert`, `workflow.decision`, `workflow.finalize`, `alert.ack`, `knowledge.search`, `knowledge.reindex`, `model.switch`, `audit.verify`.

## 6. Infraestrutura
- Headers: `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy`, `Cache-Control: no-store`, CSP restritiva na API, HSTS em produção.
- CORS apenas para as origens configuradas; limite de corpo (1 MB); containers com usuário não-root; segredos só via `.env`/variáveis; `gitleaks` no pre-commit e na CI; `pip-audit` na CI.
- LiteLLM (quando usado) centraliza chaves e limites; Langfuse registra prompts/respostas — **atenção**: só envie traces para serviços externos com dados já anonimizados (é o caso aqui).

## 7. O que fica fora do escopo acadêmico (trabalho futuro)
MFA, SSO institucional (OIDC), refresh tokens com revogação, criptografia de campo para PII em repouso, DLP em anexos, revisão clínica formal dos protocolos, homologação regulatória.
