---
id: MOD-010
titulo: Modelo de Prescrição Hospitalar Padrão
tipo: modelo
categoria: documentacao
setor: Todas as unidades de internação
versao: "2.0"
atualizado_em: 2026-03-20
responsavel: "Núcleo de Qualidade e Segurança do Paciente — HU-FIAP"
tags: [prescrição hospitalar, segurança do paciente, profilaxia TEV, controle glicêmico, oxigenoterapia, enfermaria, pneumonia]
---

# MOD-010 — Modelo de Prescrição Hospitalar Padrão

## Finalidade
Padronizar a prescrição diária de pacientes internados no HU-FIAP, garantindo que itens de segurança (alergias, peso, profilaxias, alvo de SpO2, cuidados de enfermagem) estejam sempre presentes.

## Quando usar
- Toda prescrição de paciente internado, renovada a cada 24 h.

## Estrutura / campos obrigatórios
1. **Cabeçalho:** nome, prontuário, leito, **peso**, **alergias**, data, **dieta** e **escore de risco de TEV** (Pádua/Caprini — PROT-006).
2. Itens numerados: dieta; hidratação venosa; medicamentos por **nome genérico, dose, via, frequência, horários, diluição e velocidade**; "se necessário" com **critério objetivo, dose máxima e intervalo mínimo**; profilaxia de TEV (PROT-006); controle glicêmico (PROT-011); oxigenoterapia com **alvo de SpO2**; cuidados de enfermagem; precauções.
3. Assinatura, CRM, data/hora.

## Modelo
```
PRESCRIÇÃO MÉDICA — HU-FIAP   Data: [DATA]  D+[DIA]
Paciente: [NOME DO PACIENTE]  Prontuário: [HU-000000]  Leito: [LEITO]
Peso: [PESO] kg  ALERGIAS: [LISTA / NEGA]  Dieta: [TIPO]  Risco TEV (Pádua/Caprini): [ESCORE]
1. Dieta [TIPO / CONSISTÊNCIA / RESTRIÇÕES] — [VIA ORAL / ENTERAL / JEJUM]
2. Hidratação venosa: [SOLUÇÃO] [VOLUME] mL IV a [VELOCIDADE] mL/h
3. [MEDICAMENTO GENÉRICO] [DOSE] [VIA] [FREQUÊNCIA] — horários [ ] — diluição [ ] — tempo de infusão [ ]
4. SE NECESSÁRIO: [MEDICAMENTO] [DOSE] [VIA] se [CRITÉRIO OBJETIVO], intervalo mínimo [ ] h, máx. [ ]/dia
5. Profilaxia de TEV (PROT-006): [ENOXAPARINA 40 mg SC 1x/dia] — [OU: MECÂNICA / CONTRAINDICADA — MOTIVO]
6. Controle glicêmico (PROT-011): glicemia capilar [FREQUÊNCIA]; insulina regular SC conforme escala [ESCALA]
7. Oxigenoterapia: [DISPOSITIVO] [FLUXO] L/min — alvo SpO2 [92–96% / 88–92% se DPOC]
8. Cuidados de enfermagem: sinais vitais [6/6 h]; balanço hídrico; cabeceira [30–45°]; mudança de decúbito 2/2 h
9. Precauções: [PADRÃO / CONTATO / GOTÍCULAS / AEROSSÓIS]
[MÉDICO RESPONSÁVEL] — CRM [UF] [NÚMERO]   [DATA] [HORA]
```

## Exemplo preenchido
PRESCRIÇÃO MÉDICA — HU-FIAP. 05/03/2026, D+2. J. S. O., 58 anos, masculino. Prontuário HU-000123. Leito 3B-14. Peso 82 kg. **ALERGIAS: nega.**

1. Dieta geral hipossódica via oral.
2. Sem hidratação venosa; acesso periférico salinizado.
3. **Ceftriaxona 1 g IV 1x/dia (10h)** — diluir em 100 mL de SF 0,9%, infundir em 30 min — D2.
4. **Azitromicina 500 mg VO 1x/dia** — D2.
5. Losartana 50 mg VO 1x/dia (8h).
6. SE NECESSÁRIO: dipirona 1 g IV se Tax ≥ 37,8 °C, intervalo mínimo 6 h, máximo 4 g/dia.
7. Profilaxia de TEV (PROT-006): enoxaparina 40 mg SC 1x/dia (20h).
8. Controle glicêmico (PROT-011): glicemia capilar antes das refeições e às 22h; insulina regular SC se > 180 mg/dL.
9. Oxigenoterapia: cateter nasal 2 L/min — **alvo SpO2 92–96%**.
10. Cuidados de enfermagem: sinais vitais 6/6 h; balanço hídrico; cabeceira elevada 30–45°; mudança de decúbito 2/2 h.
11. Precauções: padrão.

[MÉDICO RESPONSÁVEL] — CRM [UF] [NÚMERO] — 05/03/2026, 07h50.

## Boas práticas e erros comuns
- Revisar diariamente cada item ("ainda é necessário?").
- Erro comum: "se necessário" sem critério objetivo ("se dor", "SOS"), dose máxima ou intervalo mínimo.
- Erro comum: ausência de profilaxia de TEV; oxigênio sem alvo de SpO2 (hiperóxia em DPOC).

## Referências
1. Ministério da Saúde / ANVISA / FIOCRUZ. Protocolo de Segurança na Prescrição, Uso e Administração de Medicamentos. 2013.
2. ISMP Brasil. Lista de abreviaturas, siglas e símbolos que não devem ser utilizados. 2019.
3. Núcleo de Qualidade HU-FIAP. Manual de prescrição segura, março/2026.

---
*Modelo institucional fictício para fins acadêmicos (Tech Challenge FIAP). Não substitui normas oficiais nem julgamento clínico.*
