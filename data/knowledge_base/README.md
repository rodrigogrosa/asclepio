# Base de Conhecimento — Hospital Universitário FIAP (HU-FIAP)

> **AVISO IMPORTANTE:** todo o conteúdo desta pasta é **fictício e educacional**, criado para o projeto acadêmico *Asclépio — Assistente Clínico Inteligente* (FIAP, Tech Challenge Fase 3). O "Hospital Universitário FIAP" não existe. Os protocolos, modelos e perguntas foram redigidos com base em diretrizes públicas amplamente conhecidas (Surviving Sepsis Campaign, AHA/ACC, ESC, SBC, SBD, ADA, GINA/GOLD, AHA/ASA, ATS/IDSA, KDIGO, WAO, IDSA/EAU, entre outras), mas **não substituem diretrizes oficiais, normas institucionais reais nem o julgamento clínico**. Nenhum dado de paciente real é utilizado; todos os exemplos usam iniciais ou o marcador `[PACIENTE]`.

## Finalidade

Os arquivos servem a dois usos dentro do projeto:

1. **RAG (retrieval-augmented generation)** — os documentos Markdown são divididos em *chunks* por seção (títulos `##`) e indexados em um *vector store*; o assistente recupera os trechos relevantes e responde **citando a fonte** (`id` + seção).
2. **Fine-tuning** — o arquivo `data/synthetic/instructions_seed.jsonl` (fora desta pasta) contém exemplos de instrução/resposta derivados desta base, nas categorias `protocolo`, `documento`, `paciente_contexto`, `recusa_prescricao`, `fora_escopo`, `identidade_limites` e `anonimizacao_seguranca`.

## Estrutura de pastas

```
data/knowledge_base/
├── README.md
├── protocolos/            # 16 protocolos clínicos (PROT-001 … PROT-016)
├── modelos_documentos/    # 10 modelos de documentos (MOD-001 … MOD-010)
└── faq/
    └── perguntas_frequentes.jsonl   # ≥160 perguntas e respostas vinculadas a PROT/MOD
```

### Protocolos (`protocolos/`)

| id | arquivo | categoria |
|---|---|---|
| PROT-001 | PROT-001-sepse.md | emergencia |
| PROT-002 | PROT-002-sindrome-coronariana-aguda.md | cardiologia |
| PROT-003 | PROT-003-avc-isquemico-agudo.md | neurologia |
| PROT-004 | PROT-004-cetoacidose-diabetica.md | endocrinologia |
| PROT-005 | PROT-005-pneumonia-adquirida-comunidade.md | pneumologia |
| PROT-006 | PROT-006-profilaxia-tromboembolismo-venoso.md | clinica-medica |
| PROT-007 | PROT-007-anafilaxia.md | emergencia |
| PROT-008 | PROT-008-crise-hipertensiva.md | cardiologia |
| PROT-009 | PROT-009-insuficiencia-cardiaca-descompensada.md | cardiologia |
| PROT-010 | PROT-010-lesao-renal-aguda.md | nefrologia |
| PROT-011 | PROT-011-hipoglicemia-e-controle-glicemico-internado.md | endocrinologia |
| PROT-012 | PROT-012-hipercalemia.md | nefrologia |
| PROT-013 | PROT-013-exacerbacao-asma-dpoc.md | pneumologia |
| PROT-014 | PROT-014-dor-aguda-analgesia.md | clinica-medica |
| PROT-015 | PROT-015-delirium-idoso-hospitalizado.md | geriatria |
| PROT-016 | PROT-016-infeccao-trato-urinario-antibioticoterapia-empirica.md | infectologia |

Seções (H2) de cada protocolo, sempre nesta ordem — úteis como chave de *chunking* e de citação:
`Objetivo` · `Definições e critérios diagnósticos` · `Avaliação inicial` · `Exames recomendados` · `Conduta` · `Medicamentos e doses usuais` · `Critérios de gravidade e alerta` · `Critérios de internação, UTI e alta` · `Fluxograma` · `Perguntas frequentes da equipe` · `Referências`.

### Modelos de documentos (`modelos_documentos/`)

| id | arquivo |
|---|---|
| MOD-001 | MOD-001-laudo-ecg.md |
| MOD-002 | MOD-002-laudo-radiografia-torax.md |
| MOD-003 | MOD-003-laudo-tomografia-cranio.md |
| MOD-004 | MOD-004-receita-medica.md |
| MOD-005 | MOD-005-evolucao-soap.md |
| MOD-006 | MOD-006-sumario-de-alta.md |
| MOD-007 | MOD-007-pedido-de-parecer.md |
| MOD-008 | MOD-008-atestado-medico.md |
| MOD-009 | MOD-009-termo-consentimento-procedimento.md |
| MOD-010 | MOD-010-prescricao-hospitalar-padrao.md |

Seções (H2) de cada modelo: `Finalidade` · `Quando usar` · `Estrutura / campos obrigatórios` · `Modelo` · `Exemplo preenchido` · `Boas práticas e erros comuns` · `Referências`.

## Esquema do front matter (YAML)

Todo arquivo `.md` começa com um bloco YAML entre `---`, com as chaves abaixo (todas obrigatórias):

```yaml
---
id: PROT-001                      # PROT-0XX ou MOD-0XX
titulo: Protocolo de Sepse e Choque Séptico
tipo: protocolo                   # protocolo | modelo
categoria: emergencia             # emergencia | clinica-medica | cardiologia | neurologia |
                                  # endocrinologia | nefrologia | pneumologia | geriatria |
                                  # infectologia | farmacia | documentacao (modelos)
setor: Pronto-Socorro / Unidades de Internação
versao: "3.2"                     # string
atualizado_em: 2026-03-15         # AAAA-MM-DD
responsavel: Comissão de Protocolos Clínicos — HU-FIAP
tags: [sepse, choque séptico, lactato]
---
```

Após o front matter há um título H1 (`# PROT-001 — …`), as seções H2 na ordem fixa e, ao final, o rodapé obrigatório:

> *Protocolo institucional fictício para fins acadêmicos (Tech Challenge FIAP). Não substitui diretrizes oficiais nem julgamento clínico.*
> (nos modelos: *Modelo institucional fictício para fins acadêmicos…*)

## FAQ (`faq/perguntas_frequentes.jsonl`)

Uma linha JSON por pergunta:

```json
{"id":"FAQ-0001","pergunta":"...","resposta":"...","protocolo_id":"PROT-001","secao":"Conduta","tags":["sepse"],"categoria":"emergencia"}
```

- `protocolo_id` aponta para um `PROT-0XX` ou `MOD-0XX`; `secao` corresponde ao título H2 de origem.
- Cobertura mínima: ≥ 8 perguntas por protocolo e ≥ 2 por modelo.

## Validação rápida

```bash
# JSONL válido
python3 -c "import json; [json.loads(l) for l in open('data/knowledge_base/faq/perguntas_frequentes.jsonl')]"
python3 -c "import json; [json.loads(l) for l in open('data/synthetic/instructions_seed.jsonl')]"
# estrutura dos markdown (11 H2 em protocolos, 7 em modelos)
grep -c '^## ' data/knowledge_base/protocolos/*.md data/knowledge_base/modelos_documentos/*.md
```

## Convenções de segurança aplicadas ao conteúdo

- Doses e limiares são **educacionais, típicos de adulto**; ajustes individuais ficam a cargo do médico assistente.
- Nenhum texto prescreve para paciente específico; respostas de apoio terminam com lembrete de validação médica.
- Dados de pacientes nos exemplos são fictícios e anonimizados (`[PACIENTE]`, iniciais, prontuários `HU-000xxx`).

*Comissão de Protocolos Clínicos e Núcleo de Qualidade e Segurança do Paciente — HU-FIAP (fictícios). Última atualização: 2026-08.*
