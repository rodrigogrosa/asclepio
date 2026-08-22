---
id: MOD-001
titulo: Modelo de Laudo de Eletrocardiograma (ECG)
tipo: modelo
categoria: documentacao
setor: Todas as unidades assistenciais
versao: "2.0"
atualizado_em: 2026-02-10
responsavel: "Núcleo de Qualidade e Segurança do Paciente — HU-FIAP"
tags: [ECG, eletrocardiograma, laudo, QTc, supradesnivelamento de ST, ritmo, eixo elétrico]
---

# MOD-001 — Modelo de Laudo de Eletrocardiograma (ECG)

## Finalidade
Padronizar a descrição e a conclusão dos laudos de ECG de 12 derivações no HU-FIAP, garantindo registro mensurável de todos os parâmetros e comparabilidade entre exames.

## Quando usar
- Todo ECG realizado no Pronto-Socorro, enfermarias, UTI e ambulatórios que exija laudo médico formal.
- ECGs seriados em dor torácica (PROT-002), síncope, palpitações, distúrbios eletrolíticos e monitorização de fármacos que prolongam o QT.

## Estrutura / campos obrigatórios
1. Identificação, prontuário, data/hora do traçado e indicação clínica.
2. Calibração (25 mm/s; 10 mm/mV) e qualidade técnica.
3. **Ritmo** e **frequência cardíaca** (bpm).
4. **Eixo** do QRS (normal −30° a +90°).
5. **Onda P** (morfologia, duração < 120 ms).
6. **Intervalo PR**: 120–200 ms.
7. **QRS**: < 120 ms; morfologia, bloqueios, ondas Q patológicas.
8. **QT/QTc** (Bazett: QTc = QT/√RR); normal < 450 ms (homens) e < 460 ms (mulheres).
9. **Segmento ST** (supra/infra em mm e derivações) e **onda T**.
10. **Conclusão** objetiva, comparação com traçado prévio, assinatura e CRM.

## Modelo
```
HU-FIAP — LAUDO DE ELETROCARDIOGRAMA
Paciente: [NOME DO PACIENTE]  Prontuário: [HU-000000]  Idade/Sexo: [IDADE]/[SEXO]
Setor/Leito: [SETOR]/[LEITO]  Data/hora do traçado: [DATA] [HORA]
Indicação: [MOTIVO]  Calibração: 25 mm/s, 10 mm/mV  Qualidade: [ADEQUADA/ARTEFATOS]
Ritmo: [RITMO]   FC: [FC] bpm   Eixo: [EIXO]°
Onda P: [DESCRIÇÃO]   PR: [PR] ms
QRS: [DURAÇÃO] ms — [MORFOLOGIA]
QT/QTc: [QT]/[QTc] ms
Segmento ST: [DESCRIÇÃO, DERIVAÇÕES, mm]   Onda T: [DESCRIÇÃO]
Comparação com ECG prévio ([DATA]): [SEM ALTERAÇÕES / ALTERAÇÕES NOVAS]
CONCLUSÃO: [CONCLUSÃO OBJETIVA]
[MÉDICO RESPONSÁVEL] — CRM [UF] [NÚMERO]   [DATA] [HORA]
```

## Exemplo preenchido
**Exemplo 1 — ECG normal.** J. S. O., 58 anos, masculino, prontuário HU-000123, Ambulatório de Clínica Médica, 12/02/2026, 09h10; indicação: pré-operatório. Ritmo sinusal, FC 72 bpm, eixo +45°. Onda P normal (90 ms). PR 160 ms. QRS 88 ms, sem ondas Q patológicas. QT 380 ms / QTc 416 ms. ST isoelétrico; ondas T positivas e assimétricas. Sem ECG prévio. **Conclusão:** ECG dentro dos limites da normalidade.

**Exemplo 2 — Supradesnivelamento de ST inferior.** M. R. C., 64 anos, feminino, prontuário HU-000456, Pronto-Socorro, leito PS-07, 15/02/2026, 03h22; indicação: dor torácica opressiva há 40 min. Ritmo sinusal, FC 58 bpm, eixo +30°. PR 180 ms. QRS 92 ms. QT 420 ms / QTc 412 ms. **Supradesnivelamento de ST de 2,5 mm em DII, DIII e aVF**, com infradesnivelamento recíproco de 1,5 mm em DI e aVL; ondas T hiperagudas inferiores. **Conclusão:** infarto agudo do miocárdio com supradesnivelamento de ST em parede inferior. Acionar protocolo de dor torácica (PROT-002) imediatamente; obter V3R/V4R e V7–V9.

## Boas práticas e erros comuns
- Laudar em até 10 minutos da chegada em dor torácica; registrar o horário real do traçado.
- Medir o QT em DII ou V5; em FC > 100 bpm considerar Fridericia.
- Erro comum: "ECG normal" sem registrar os intervalos numéricos.
- Erro comum: não comparar com traçado prévio, perdendo alterações novas.
- Erro comum: troca de eletrodos de membros (P negativa em DI) interpretada como dextrocardia.

## Referências
1. Sociedade Brasileira de Cardiologia. Diretriz de Análise e Emissão de Laudos Eletrocardiográficos. Arq Bras Cardiol. 2022.
2. Conselho Federal de Medicina. Resolução CFM nº 1.638/2002 — prontuário médico.
3. Núcleo de Qualidade HU-FIAP. Padronização de laudos de métodos gráficos, fevereiro/2026.

---
*Modelo institucional fictício para fins acadêmicos (Tech Challenge FIAP). Não substitui normas oficiais nem julgamento clínico.*
