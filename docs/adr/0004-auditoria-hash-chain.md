# ADR-0004: Trilha de auditoria append-only com cadeia de hashes

- **Status**: aceito · **Data**: 2026-08-21

## Contexto
O desafio pede "logging detalhado para rastreamento e auditoria". Logs de aplicação são voláteis e editáveis; precisamos de evidência durável de quem perguntou o quê, que fontes foram usadas e qual guardrail atuou.

## Decisão
Tabela `audit_log` com `prev_hash` e `hash = SHA-256(prev_hash + registro_canônico)`; endpoint `GET /audit/verify` recomputa a cadeia. Cada registro carrega `trace_id` (= `X-Request-ID`) que também aparece nos logs estruturados e nos traces do Langfuse.

## Alternativas
- Apenas logs em arquivo/ELK — sem garantia de integridade. - Blockchain/ledger externo — exagero para o escopo.

## Consequências
+ Adulteração detectável (testado); explicabilidade forte. − Escritas sequenciais (ok para o volume do projeto).
