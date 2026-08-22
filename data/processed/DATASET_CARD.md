# Dataset Card — Asclépio (instruções clínicas em pt-BR)

> Gerado automaticamente por `uv run python -m asclepio_ml prepare` em 2026-08-21T20:56:03. Semente: 42.

## O que é
Dataset de instrução (formato *chat messages*: `system` / `user` / `assistant`) usado para o
fine-tuning LoRA do **Asclépio — Assistente Clínico Inteligente** (Tech Challenge FIAP, Fase 3).
Cada exemplo ensina o modelo a: responder sobre protocolos institucionais com citação da fonte,
descrever modelos de documentos, interpretar contexto clínico anonimizado, **recusar prescrever**,
recusar temas fora de escopo e proteger dados pessoais.

## Composição
**Total final: 2046 exemplos** (após augmentação, anonimização e curadoria).

### Por categoria
| chave | valor |
|---|---|
| anonimizacao_seguranca | 84 |
| documento | 248 |
| fora_escopo | 108 |
| identidade_limites | 66 |
| paciente_contexto | 111 |
| protocolo | 1300 |
| recusa_prescricao | 129 |

### Por origem
| chave | valor |
|---|---|
| builtin | 36 |
| faq | 379 |
| modelo | 120 |
| paciente | 70 |
| protocolo_faq | 202 |
| protocolo_farmaco | 233 |
| protocolo_secao | 272 |
| seed | 734 |

Fontes brutas carregadas: | chave | valor |
|---|---|
| faq | 167 |
| modelos_documentos | 10 |
| protocolos | 16 |
| seed_instructions | 233 |

Exemplos gerados por origem (antes da augmentação): | chave | valor |
|---|---|
| builtin | 8 |
| faq | 167 |
| modelo | 50 |
| paciente | 72 |
| protocolo_faq | 80 |
| protocolo_farmaco | 135 |
| protocolo_secao | 144 |
| seed | 233 |
Após augmentação por paráfrase templada: **3497**.

## Anonimização (LGPD)
Todos os textos (pergunta e resposta) passaram pelo `asclepio_core.anonymizer.Anonymizer`.
- Exemplos com ≥ 1 entidade removida: **0** (0.0% do total pré-curadoria)
- Entidades removidas: **0** — por tipo: {}
- Entidades removidas nas evoluções dos pacientes sintéticos (antes de montar o contexto): 49

Os contextos de paciente são construídos a partir de **pacientes 100% sintéticos** (Faker, semente fixa) com PII
fictícia inserida de propósito — justamente para demonstrar a anonimização antes do treino.

## Curadoria
| chave | valor |
|---|---|
| capped_protocolo | 1350 |
| disclaimer_added | 123 |
| kept | 2046 |
| refusal_reinforced | 114 |
| removed_exact_duplicates | 93 |
| removed_near_duplicates | 8 |

Regras: descarte de respostas vazias/curtas, dedupe exato e aproximado (normalização sem acento/pontuação),
truncamento de respostas longas em limite de parágrafo, balanceamento por categoria (cap), aviso de validação
humana obrigatório nas categorias clínicas e reforço de recusa nas categorias de recusa.

## Splits (estratificado por categoria; paráfrases do mesmo exemplo ficam no mesmo split)
| split | n | por categoria |
|---|---|---|
| train | 1719 | anonimizacao_seguranca: 72, documento: 205, fora_escopo: 87, identidade_limites: 56, paciente_contexto: 93, protocolo: 1104, recusa_prescricao: 102 |
| val | 165 | anonimizacao_seguranca: 6, documento: 23, fora_escopo: 9, identidade_limites: 5, paciente_contexto: 10, protocolo: 98, recusa_prescricao: 14 |
| test | 162 | anonimizacao_seguranca: 6, documento: 20, fora_escopo: 12, identidade_limites: 5, paciente_contexto: 8, protocolo: 98, recusa_prescricao: 13 |

## Tamanhos
| chave | valor |
|---|---|
| approx_tokens_mean | 497 |
| assistant_chars_max | 1657 |
| assistant_chars_mean | 583 |
| user_chars_max | 1260 |
| user_chars_mean | 126 |

System prompt: 1030 caracteres (idêntico em todos os exemplos; ver `asclepio_ml/prompts.py`).

## Licença e aviso
Conteúdo **fictício e educacional** (hospital fictício HU-FIAP), produzido para o Tech Challenge FIAP.
Não substitui protocolos reais nem orientação médica. Os dados de pacientes são sintéticos; nenhuma pessoa real é
descrita. Uso livre para fins acadêmicos (MIT, ver `LICENSE` na raiz do repositório).


