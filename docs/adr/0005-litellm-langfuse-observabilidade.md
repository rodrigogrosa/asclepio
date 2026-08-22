# ADR-0005: LiteLLM como gateway opcional e Langfuse para observabilidade de LLM

- **Status**: aceito · **Data**: 2026-08-21

## Contexto
Queremos trocar de provedor sem mexer no código, ter controle de chaves/limites/custos e rastrear prompts, tokens e latência por conversa/fluxo.

## Decisão
`LLM_PROVIDER=litellm` aponta o `ChatOpenAI` para o **LiteLLM Proxy** (config em `infra/litellm/config.yaml` com fallbacks `asclepio-med → llama3.1:8b → llama3.2:3b`). **Langfuse v3** self-hosted no compose (perfil `observability`, init headless com chaves conhecidas) ou cloud via env; `LLMFactory.run_config()` injeta o `CallbackHandler` com `session_id`/`user_id`/tags. O padrão continua `ollama` direto (zero dependências extras).

## Consequências
+ Observabilidade completa em 1 comando (`make up-full`). − Stack do Langfuse é pesada (ClickHouse/MinIO/Redis) — por isso é perfil opcional.
