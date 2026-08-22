---
id: MOD-004
titulo: Modelo de Receita Médica (simples e controle especial)
tipo: modelo
categoria: documentacao
setor: Todas as unidades assistenciais
versao: "2.0"
atualizado_em: 2026-03-05
responsavel: "Núcleo de Qualidade e Segurança do Paciente — HU-FIAP"
tags: [receita médica, prescrição, controle especial, Portaria 344/98, DCB, segurança do paciente]
---

# MOD-004 — Modelo de Receita Médica (simples e controle especial)

## Finalidade
Padronizar a emissão de receitas médicas no HU-FIAP, garantindo legibilidade, completude e conformidade com a legislação sanitária, para reduzir erros de dispensação e de uso pelo paciente.

## Quando usar
- Toda prescrição de medicamentos para uso fora do hospital (alta, ambulatório, liberação do PS).
- Receita de **controle especial** (2 vias) para medicamentos das listas B1, C1, C2, C4 e C5 da Portaria SVS/MS nº 344/1998 (benzodiazepínicos, antidepressivos, anticonvulsivantes, opioides fracos, antipsicóticos); entorpecentes (A) exigem notificação de receita específica.

## Estrutura / campos obrigatórios
1. **Cabeçalho institucional:** hospital, endereço, telefone, CNPJ.
2. **Identificação do paciente:** nome completo, data de nascimento, endereço (obrigatório em controle especial).
3. **Medicamento:** nome genérico (DCB), concentração, forma farmacêutica.
4. **Posologia:** dose, via, frequência, horários; **quantidade total por extenso**; duração; orientações.
5. **Data, assinatura, carimbo com nome e CRM.**
6. Controle especial: 2 vias, validade 30 dias, campos de comprador e fornecedor. Antimicrobianos: 2 vias, validade 10 dias (RDC 471/2021).

## Modelo
```
HOSPITAL UNIVERSITÁRIO FIAP (HU-FIAP) — [ENDEREÇO] — Tel. [TELEFONE] — CNPJ [CNPJ]
RECEITUÁRIO [SIMPLES / DE CONTROLE ESPECIAL — 1ª VIA FARMÁCIA / 2ª VIA PACIENTE]
Paciente: [NOME DO PACIENTE]  Nascimento: [DD/MM/AAAA]  Prontuário: [HU-000000]
Endereço: [ENDEREÇO DO PACIENTE]

Uso [ORAL / TÓPICO / INALATÓRIO / SUBCUTÂNEO]
1) [NOME GENÉRICO — DCB] [CONCENTRAÇÃO] — [FORMA FARMACÊUTICA] ...... [QUANTIDADE] ([POR EXTENSO])
   Tomar [DOSE] via [VIA] a cada [INTERVALO] ([HORÁRIOS]), por [DURAÇÃO]. Orientações: [ORIENTAÇÕES]
2) [...]

[CIDADE], [DATA]
[MÉDICO RESPONSÁVEL] — CRM [UF] [NÚMERO]
```

## Exemplo preenchido
**Receita simples** — M. A. S., 45 anos, prontuário HU-000654, nascimento 11/04/1981. São Paulo, 05/03/2026. Uso oral:
1) Amoxicilina + clavulanato 875 mg + 125 mg — comprimido revestido ...... 14 (quatorze) comprimidos. Tomar 1 comprimido via oral a cada 12 horas (8h e 20h), por 7 dias. Orientações: ingerir com alimentos; completar o tratamento.
2) Dipirona 500 mg — comprimido ...... 20 (vinte) comprimidos. Tomar 1 comprimido via oral a cada 6 horas se dor ou febre (≥ 37,8 °C), por até 5 dias; máximo 4 comprimidos/dia.
[MÉDICO RESPONSÁVEL] — CRM [UF] [NÚMERO]

**Receita de controle especial (2 vias)** — mesma paciente, endereço preenchido, mesma data.
1) Clonazepam 0,5 mg — comprimido ...... 30 (trinta) comprimidos. Tomar 1 comprimido via oral à noite (22h), por 30 dias. Orientações: não associar a álcool; evitar dirigir; não interromper abruptamente.
[MÉDICO RESPONSÁVEL] — CRM [UF] [NÚMERO]

## Boas práticas e erros comuns
- Letra legível ou receita eletrônica com assinatura digital ICP-Brasil (Resolução CFM nº 2.299/2021).
- Usar **sempre o nome genérico (DCB)**; marca comercial apenas entre parênteses.
- Evitar abreviaturas perigosas ("U", "cp", "SOS"); escrever "unidades", "comprimido", "se necessário".
- Erro comum: **ausência de duração do tratamento** ou de quantidade total.
- Erro comum: controle especial em via única ou sem endereço do paciente — recusada pela farmácia.
- Não rasurar; em caso de erro, emitir nova receita.

## Referências
1. Brasil. Ministério da Saúde. Portaria SVS/MS nº 344/1998 e Portaria nº 6/1999.
2. ANVISA. RDC nº 471/2021 — prescrição e dispensação de antimicrobianos.
3. Núcleo de Qualidade HU-FIAP. Manual de prescrição segura, março/2026.

---
*Modelo institucional fictício para fins acadêmicos (Tech Challenge FIAP). Não substitui normas oficiais nem julgamento clínico.*
