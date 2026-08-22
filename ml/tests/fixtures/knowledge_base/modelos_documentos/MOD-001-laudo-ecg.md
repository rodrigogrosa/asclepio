---
id: MOD-001
titulo: Modelo de Laudo de Eletrocardiograma (ECG)
tipo: modelo
categoria: documentacao
versao: "1.0"
tags: [ECG, laudo]
---

# MOD-001 — Modelo de Laudo de ECG

## Finalidade
Padronizar a descrição e a conclusão dos laudos de ECG no HU-FIAP.

## Quando usar
- Todo ECG que exija laudo médico formal.

## Estrutura / campos obrigatórios
1. Identificação e indicação clínica.
2. Ritmo e frequência cardíaca.
3. Eixo, intervalos PR, QRS e QTc.
4. Conclusão e assinatura com CRM.

## Modelo
```
HU-FIAP — LAUDO DE ELETROCARDIOGRAMA
Paciente: [NOME DO PACIENTE]  Prontuário: [HU-000000]
Ritmo: [RITMO]   FC: [FC] bpm   Eixo: [EIXO]°
Conclusão: [CONCLUSÃO]
```

## Exemplo preenchido
Ritmo sinusal, FC 72 bpm, eixo +45°, QTc 410 ms. Conclusão: ECG normal.

## Boas práticas e erros comuns
- Sempre medir o QTc; erro comum: omitir comparação com traçado prévio.

## Referências
1. SBC. Material fictício/didático.
