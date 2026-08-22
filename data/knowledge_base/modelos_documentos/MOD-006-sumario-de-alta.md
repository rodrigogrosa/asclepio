---
id: MOD-006
titulo: Modelo de Sumário de Alta Hospitalar
tipo: modelo
categoria: documentacao
setor: Todas as unidades de internação
versao: "2.0"
atualizado_em: 2026-03-12
responsavel: "Núcleo de Qualidade e Segurança do Paciente — HU-FIAP"
tags: [sumário de alta, alta hospitalar, reconciliação medicamentosa, CID-10, transição de cuidado, insuficiência cardíaca]
---

# MOD-006 — Modelo de Sumário de Alta Hospitalar

## Finalidade
Padronizar o sumário de alta do HU-FIAP como documento de transição de cuidado, com síntese da internação e reconciliação medicamentosa explícita.

## Quando usar
- Toda alta hospitalar (melhorada, a pedido, transferência) de unidades de internação e UTI.

## Estrutura / campos obrigatórios
1. **Identificação:** nome, prontuário, nascimento, leito, equipe.
2. **Datas** de admissão e alta; permanência; tipo de alta.
3. **Diagnóstico principal** e **secundários** com CID-10.
4. **Resumo da internação** e **procedimentos** com datas.
5. **Exames relevantes** (admissão → alta) e **condição na alta**.
6. **Medicações de alta com reconciliação:** novas / alteradas / mantidas / suspensas, com motivo.
7. **Orientações**, **sinais de alerta**, **retorno/seguimento**, assinatura e CRM.

## Modelo
```
SUMÁRIO DE ALTA HOSPITALAR — HU-FIAP
Paciente: [NOME DO PACIENTE]  Prontuário: [HU-000000]  Nascimento: [DD/MM/AAAA]  Leito: [LEITO]
Admissão: [DATA]  Alta: [DATA]  Permanência: [N] dias  Tipo: [MELHORADA / A PEDIDO]
Diagnóstico principal: [DIAGNÓSTICO] (CID-10 [CÓDIGO])
Diagnósticos secundários: [DIAGNÓSTICO] (CID-10 [CÓDIGO]); [...]
Resumo da internação: [MOTIVO, EVOLUÇÃO, INTERCORRÊNCIAS]   Procedimentos: [PROCEDIMENTO — DATA]
Exames relevantes: [ADMISSÃO → ALTA]   Condição na alta: [SINAIS VITAIS, PESO, FUNCIONALIDADE]
MEDICAÇÕES DE ALTA — NOVAS: [FÁRMACO — DOSE — VIA — FREQUÊNCIA — MOTIVO]
  ALTERADAS: [DE ... PARA ... — MOTIVO]   MANTIDAS: [...]   SUSPENSAS: [FÁRMACO — MOTIVO]
Orientações: [DIETA, ATIVIDADE, CUIDADOS]
Sinais de alerta — procurar o PS se: [LISTA]
Retorno/seguimento: [CONSULTA — DATA — LOCAL]; pendências: [EXAMES]
[CIDADE], [DATA]   [MÉDICO RESPONSÁVEL] — CRM [UF] [NÚMERO]
```

## Exemplo preenchido
L. F. B., 72 anos, masculino. Prontuário HU-000987. Leito 4A-08. Admissão 04/03/2026; alta 11/03/2026 (7 dias), melhorada.

**Diagnóstico principal:** insuficiência cardíaca descompensada, perfil B (quente e congesto), FEVE 32% (CID-10 I50.0). **Secundários:** hipertensão arterial (I10); diabetes tipo 2 (E11.9).

**Resumo:** dispneia progressiva, ortopneia e edema de membros inferiores após abandono do diurético. Tratado conforme PROT-009 com furosemida IV, perda de 6,2 kg e desmame de O2 em 72 h. **Exames:** NT-proBNP 6.800 → 1.950 pg/mL; creatinina 1,6 → 1,4 mg/dL. **Condição na alta:** PA 118 × 72 mmHg, FC 68 bpm, SpO2 96% em ar ambiente, peso seco 78,4 kg.

**Medicações de alta:** NOVAS — dapagliflozina 10 mg VO 1x/dia; espironolactona 25 mg VO 1x/dia. ALTERADAS — furosemida de 40 para 80 mg VO pela manhã; enalapril substituído por sacubitril-valsartana 49/51 mg VO 12/12 h. MANTIDAS — carvedilol 12,5 mg 12/12 h. SUSPENSAS — ibuprofeno de uso próprio (risco de descompensação e lesão renal).

**Orientações:** sal < 5 g/dia, líquidos 1,5 L/dia, pesar-se diariamente. **Sinais de alerta:** ganho > 2 kg em 3 dias, dispneia em repouso, edema crescente, síncope. **Retorno:** ambulatório de IC em 18/03/2026 com creatinina e potássio. [MÉDICO RESPONSÁVEL] — CRM [UF] [NÚMERO].

## Boas práticas e erros comuns
- Concluir no dia da alta; entregar cópia e explicar verbalmente (*teach-back*).
- A reconciliação deve listar explicitamente o que foi suspenso e por quê.
- Erro comum: medicações por nome comercial ou sem dose/frequência.
- LGPD: compartilhar com terceiros apenas com consentimento.

## Referências
1. Conselho Federal de Medicina. Resolução CFM nº 1.638/2002 — prontuário e documentos de alta.
2. Sociedade Brasileira de Cardiologia. Diretriz Brasileira de Insuficiência Cardíaca Crônica e Aguda. 2021.
3. Núcleo de Qualidade HU-FIAP. Programa de transição segura do cuidado, março/2026.

---
*Modelo institucional fictício para fins acadêmicos (Tech Challenge FIAP). Não substitui normas oficiais nem julgamento clínico.*
