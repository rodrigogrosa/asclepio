---
id: MOD-003
titulo: Modelo de Laudo de Tomografia de Crânio sem Contraste
tipo: modelo
categoria: documentacao
setor: Radiologia e Diagnóstico por Imagem / Pronto-Socorro / Neurologia
versao: "2.0"
atualizado_em: 2026-02-10
responsavel: "Núcleo de Qualidade e Segurança do Paciente — HU-FIAP"
tags: [tomografia de crânio, laudo, AVC, ASPECTS, hemorragia, desvio de linha média, neuroimagem]
---

# MOD-003 — Modelo de Laudo de Tomografia de Crânio sem Contraste

## Finalidade
Padronizar o laudo da TC de crânio sem contraste no HU-FIAP, com ênfase na avaliação rápida do paciente com suspeita de AVC, trauma ou rebaixamento de consciência, garantindo que informações críticas (hemorragia, ASPECTS, desvio de linha média) sejam sempre explicitadas.

## Quando usar
- Toda TC de crânio sem contraste em adultos.
- Protocolo de AVC agudo (PROT-003): laudo preliminar em até 20 minutos da aquisição, antes da decisão de trombólise.
- Trauma craniano, cefaleia súbita, crise convulsiva nova, controle neurocirúrgico.

## Estrutura / campos obrigatórios
1. Identificação, prontuário, data/hora, indicação e horário do ictus (em AVC).
2. **Técnica:** multislice sem contraste, reconstruções multiplanares, janelas de parênquima e óssea.
3. **Parênquima** (atenuação, lesões focais, edema).
4. **Diferenciação substância branca/cinzenta.**
5. **Sistema ventricular.**
6. **Desvio de linha média** em mm (septo pelúcido).
7. **Cisternas da base.**
8. **Hemorragia** (tipo, localização, volume estimado ABC/2).
9. **Sinais precoces de isquemia** e **ASPECTS** (0–10).
10. **Calota craniana e seios paranasais**; comparação, conclusão, assinatura e CRM.

## Modelo
```
HU-FIAP — LAUDO DE TOMOGRAFIA DE CRÂNIO SEM CONTRASTE
Paciente: [NOME DO PACIENTE]  Prontuário: [HU-000000]  Idade/Sexo: [IDADE]/[SEXO]
Setor/Leito: [SETOR]/[LEITO]  Data/hora: [DATA] [HORA]
Indicação: [MOTIVO]  Ictus: [DATA/HORA OU DESCONHECIDO]
Técnica: TC multislice sem contraste, reconstruções multiplanares, janelas de parênquima e óssea.
Parênquima: [DESCRIÇÃO]
Diferenciação branca/cinzenta: [PRESERVADA / APAGADA EM ...]
Sistema ventricular: [DIMENSÕES / SIMETRIA]
Desvio de linha média: [0 mm / X mm PARA DIREITA/ESQUERDA]
Cisternas da base: [PÉRVIAS / APAGADAS]
Hemorragia: [AUSENTE / TIPO, LOCAL, VOLUME]
Sinais precoces de isquemia: [AUSENTES / DESCRIÇÃO]   ASPECTS: [0–10]
Calota e seios paranasais: [DESCRIÇÃO]
Comparação com exame de [DATA]: [EVOLUÇÃO / SEM EXAME PRÉVIO]
CONCLUSÃO: [CONCLUSÃO OBJETIVA]
[MÉDICO RESPONSÁVEL] — CRM [UF] [NÚMERO]   [DATA] [HORA]
```

## Exemplo preenchido
R. T. M., 67 anos, masculino. Prontuário HU-000321. Sala de emergência, leito SE-02. Exame em 20/02/2026, 10h48. Indicação: hemiparesia esquerda e disartria súbitas; ictus às 09h55 (NIHSS 9). PROT-003 acionado.
Parênquima de atenuação preservada, sem lesões focais ou edema. Diferenciação substância branca/cinzenta preservada, incluindo núcleos da base e ínsula. Sistema ventricular normal e simétrico. Desvio de linha média: 0 mm. Cisternas da base pérvias. **Ausência de hemorragia intra ou extra-axial.** Sinais precoces de isquemia ausentes; **ASPECTS 10**. Calota íntegra; seios paranasais normoaerados.
**Conclusão:** TC sem evidência de hemorragia ou sinais precoces de isquemia (ASPECTS 10). Achados não contraindicam trombólise venosa; correlacionar com critérios clínicos do PROT-003 e considerar angiotomografia para oclusão de grande vaso.

## Boas práticas e erros comuns
- Em suspeita de AVC, comunicar laudo preliminar verbal ao neurologista e registrar o horário.
- Informar o ASPECTS numericamente, mesmo quando 10.
- Medir o desvio de linha média em mm; "discreto desvio" é impreciso.
- Erro comum: não avaliar janela óssea em trauma (fraturas da base passam despercebidas).
- Erro comum: omitir o horário do ictus, essencial para a janela terapêutica.

## Referências
1. Sociedade Brasileira de Doenças Cerebrovasculares / Academia Brasileira de Neurologia. Diretrizes para tratamento do AVC isquêmico agudo. 2022.
2. Colégio Brasileiro de Radiologia (CBR). Laudo estruturado em neurorradiologia de urgência. 2023.
3. Núcleo de Qualidade HU-FIAP. Padronização de laudos de imagem, fevereiro/2026.

---
*Modelo institucional fictício para fins acadêmicos (Tech Challenge FIAP). Não substitui normas oficiais nem julgamento clínico.*
