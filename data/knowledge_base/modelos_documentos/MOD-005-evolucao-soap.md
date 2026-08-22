---
id: MOD-005
titulo: Modelo de Evolução Médica (SOAP)
tipo: modelo
categoria: documentacao
setor: Todas as unidades assistenciais
versao: "2.0"
atualizado_em: 2026-03-05
responsavel: "Núcleo de Qualidade e Segurança do Paciente — HU-FIAP"
tags: [evolução médica, SOAP, prontuário, lista de problemas, plano terapêutico, enfermaria]
---

# MOD-005 — Modelo de Evolução Médica (SOAP)

## Finalidade
Padronizar a evolução diária de pacientes internados no HU-FIAP no formato SOAP, favorecendo raciocínio orientado por problemas e comunicação segura entre plantões.

## Quando usar
- Evolução diária de todo paciente internado (enfermaria, UTI, observação do PS).
- Reavaliações em intercorrências, com horário.

## Estrutura / campos obrigatórios
1. Cabeçalho: data, hora, dia de internação (D+), leito, equipe.
2. **S — Subjetivo:** queixas, dor (0–10), aceitação da dieta, sono.
3. **O — Objetivo:** sinais vitais, exame físico, **dispositivos** (dia de uso), **balanço hídrico**, exames novos, antibióticos (D+).
4. **A — Avaliação:** lista numerada de **problemas ativos**, com impressão e evolução.
5. **P — Plano por problema:** exames, medicações, metas, pareceres, **previsão de alta**.
6. Assinatura e CRM.

## Modelo
```
EVOLUÇÃO MÉDICA — HU-FIAP   Data: [DATA]  Hora: [HORA]  D+[DIA]
Paciente: [NOME DO PACIENTE]  Prontuário: [HU-000000]  Leito: [LEITO]  Equipe: [EQUIPE]
S: [QUEIXAS, DOR 0–10, DIETA, SONO]
O: PA [ ] mmHg | FC [ ] bpm | FR [ ] irpm | Tax [ ] °C | SpO2 [ ]% em [AA / O2 L/min]
   Exame físico: [GERAL / CARDIORRESPIRATÓRIO / ABDOME / NEUROLÓGICO / EXTREMIDADES]
   Dispositivos: [AVP D+ / CVC D+ / SVD D+]   Balanço hídrico: [± mL]   Diurese: [mL/kg/h]
   Exames novos: [LABORATÓRIO / IMAGEM / CULTURAS]   Medicações: [ANTIBIÓTICO D+ / OUTRAS]
A: 1. [PROBLEMA — IMPRESSÃO — EVOLUÇÃO]   2. [...]
P: 1. [CONDUTA]   2. [CONDUTA]   Metas: [ALVOS]   Previsão de alta: [DATA / CRITÉRIOS]
[MÉDICO RESPONSÁVEL] — CRM [UF] [NÚMERO]
```

## Exemplo preenchido
EVOLUÇÃO MÉDICA — HU-FIAP. 06/03/2026, 08h15, D+3. J. S. O., 58 anos, masculino, prontuário HU-000123, leito 3B-14, Clínica Médica 2.

**S:** Melhora da dispneia e da tosse; expectoração em menor volume. Dor 0/10. Aceitou a dieta.

**O:** PA 122 × 78 mmHg, FC 84 bpm, FR 18 irpm, Tax 36,7 °C (afebril há 36 h), SpO2 95% em ar ambiente. Estertores crepitantes em base direita, reduzidos em relação a D+1; sem sibilos. Balanço hídrico +350 mL; diurese 1,1 mL/kg/h. Leucócitos 9.800/mm³, PCR 48 mg/L, creatinina 0,9 mg/dL. **Ceftriaxona 1 g IV 1x/dia — D3**; azitromicina 500 mg VO — D3; enoxaparina 40 mg SC 1x/dia.

**A:** 1. Pneumonia adquirida na comunidade em lobo inferior direito, CURB-65 = 1 (PROT-005) — melhora clínica e laboratorial. 2. Hipertensão arterial — controlada. 3. Profilaxia de TEV (PROT-006) em curso.

**P:** 1. Manter ceftriaxona; transição para amoxicilina-clavulanato VO em D+4 se afebril ≥ 48 h, SpO2 ≥ 92% em ar ambiente e via oral funcionante; completar 5–7 dias. 2. Manter losartana 50 mg VO 1x/dia. 3. Manter enoxaparina. **Previsão de alta: 07/03/2026**, com retorno em 7 dias.

[MÉDICO RESPONSÁVEL] — CRM [UF] [NÚMERO]

## Boas práticas e erros comuns
- Evoluir todos os dias, inclusive fins de semana, com horário real do exame.
- Registrar dia de uso de cada dispositivo e antibiótico (D+).
- Erro comum: copiar e colar a evolução anterior sem atualizar sinais vitais e exames.
- Erro comum: lista de problemas ausente ou plano genérico ("manter conduta").

## Referências
1. Conselho Federal de Medicina. Resolução CFM nº 1.638/2002 — prontuário do paciente.
2. Núcleo de Qualidade HU-FIAP. Padronização do prontuário eletrônico, março/2026.

---
*Modelo institucional fictício para fins acadêmicos (Tech Challenge FIAP). Não substitui normas oficiais nem julgamento clínico.*
