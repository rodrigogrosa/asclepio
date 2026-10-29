# Manual de testes da Fase 4 — passo a passo para conferir cada exigência

> Para quem vai **avaliar ou demonstrar** o Asclépio. Cada bloco traz a **exigência do edital**, **o que
> fazer** (clique a clique), **o que deve aparecer** e **onde está a prova**. Tempo total: 40–60 min (a
> primeira análise de vídeo e de áudio baixa os modelos; as seguintes são rápidas).
> Resultados descritos aqui foram medidos na plataforma rodando em Docker, em 28–29/10/2026.

---

## 0. Antes de começar

**0.1 Instale e suba** seguindo o [README](../../README.md) (Passos 1–4). Ao final, abra
<http://localhost:3000> — ou a porta que o instalador mostrar (`WEB_PORT` no `.env`).

**0.2 Logins de demonstração** (senha de todos: `Asclepio@2026`):

| Quem | E-mail | Para quê |
|---|---|---|
| Médica | `dra.ana@asclepio.fiap` | Rodar as análises (vídeo, áudio, tempo real) e recalcular pacientes |
| Enfermeira | `enf.carla@asclepio.fiap` | Receber os alertas em tempo real e reconhecê-los |
| Auditoria | `auditor@asclepio.fiap` | Auditoria (trilha imutável) e central de Documentação |

**0.3 Duas janelas lado a lado** (recomendado): a **Dra. Ana** numa janela normal e a **Enf. Carla** numa
janela anônima. É assim que se vê o alerta chegando sozinho para a equipe.

**0.4 Azure (opcional, mas exigido no edital).** Sem chave, tudo funciona em **modo local** (Whisper +
léxico clínico) e a tela avisa. Para ligar o Azure: `make azure-setup` e `make azure-check` — passo a
passo em [GUIA_AZURE.md](GUIA_AZURE.md). Depois, `docker compose up -d api`.

**0.5 Primeira execução.** A primeira análise de vídeo baixa o OpenPose (~200 MB) e a primeira de áudio
baixa os modelos de som (~0,4 GB com Azure; ~1,2 GB sem Azure, pois inclui o Whisper). Para baixar antes:
`make fase4-assets`.

---

## Parte A — Visão geral e integração com a nuvem

**Exigência:** *"Integrar tudo isso com serviços gerenciados em nuvem, como Azure Cognitive Services."*

1. Entre como **Dra. Ana** → menu lateral **Monitoramento**.
2. Veja o cartão **Integração Azure e modelos** no topo.

**Deve aparecer:**

- Selo **Azure conectado** (ou **Modo local**, se você não configurou as chaves).
- *Transcrição da fala* → "Azure Speech to Text · região brazilsouth"; *Análise do texto clínico* →
  Azure Text Analytics.
- **Modelos prontos (7 de 7):** OpenPose COCO 18 pontos (CMU), YOLOv8n, transcrição (Azure ou Whisper),
  análise de texto (Azure ou léxico), AST treinado no AudioSet, Praat e o detector online.

✅ **Prova:** tela `docs/assets/fase4/telas/10_azure_conectado.jpg` · relatório §8.

---

## Parte B — Análise de vídeo

### B1. Vídeo de fisioterapia com OpenPose (postura)
**Exigência:** *"Processar vídeos clínicos (fisioterapia ou cirurgias)"* e *"detectar movimentos fora do
padrão com OpenPose para análise postural."*

1. **Monitoramento** → aba **Vídeo**.
2. **Paciente:** qualquer um (ex.: *Ana Liz Rios*).
3. **Usar vídeo de exemplo** → *"Fisioterapia · agachamento unipodal (teste funcional do joelho)"*.
   O perfil e o exercício do exemplo são aplicados automaticamente.
4. **Analisar vídeo** → acompanhe as etapas (YOLOv8 → OpenPose → cinemática) → **Abrir resultado**.

**Deve aparecer:**

- Achado **"Inclinação excessiva do tronco no agachamento unipodal"** (atenção), trecho 4,2–6,8 s:
  *"pior: 72°; limite 30°"* — sinal de compensação.
- **Vídeo anotado** com o esqueleto de 18 pontos do OpenPose; clique em **Ir para 0:04** e o vídeo pula
  para o trecho.
- **Séries medidas**: ângulos de joelho, quadril e tronco no tempo, com o instante do achado marcado.
- **Modelos aplicados:** *OpenPose COCO (CMU) — Local*, *YOLOv8n — Local*, *Regras de perfil + z-score*.

Para comparar: *"Fisioterapia · agachamento com carga, vista lateral"* conta **6 repetições** sem desvios.

### B2. Queda no quarto com YOLOv8 + OpenPose (evento fora do padrão)
**Exigência:** *"YOLOv8 para detecção de objetos e áreas críticas"* + padrões de movimentação.

1. Deixe a janela da **Enf. Carla** visível.
2. Na janela da Dra. Ana: aba **Vídeo** → paciente **Matheus Garcia** → **Usar vídeo de exemplo** →
   *"Quarto · paciente cai ao levantar (URFD fall-01)"* → **Analisar vídeo**.

**Deve aparecer:**

- Achado **"Queda detectada"** (crítico): *descida brusca seguida de postura deitada*.
- Na janela da enfermeira, **sem recarregar**: aviso vermelho **"Alerta crítico: Queda detectada —
  Matheus Garcia · origem: mobilidade"** com **Ver** e **Reconhecer**.
- No resultado: **Quadros-chave** com as **caixas do YOLOv8** (pessoa, cadeiras) e o esqueleto.

Controle negativo: *"Quarto · atividade normal, sem queda (URFD adl-01)"* → **nenhum achado**.

### B3. Relatório automático de desvios
**Exigência:** *"Gerar relatórios automáticos indicando desvios ou falhas no procedimento."*

1. Em qualquer resultado de vídeo, role até **Relatório** → **Baixar relatório**.

**Deve aparecer:** Markdown com resumo, tabela de achados (trecho, evidência numérica, recomendação),
métricas, modelos usados e limitações — gerado sozinho, sem intervenção.

### B4. (Opcional) Seu próprio vídeo
**Enviar arquivo** aceita MP4, MOV, AVI, MKV, WEBM e OGV (até 200 MB; analisa até 5 min). Perfis:
*Fisioterapia* (agachamento), *Quarto do paciente* (queda, imobilidade, agitação) e *Cirurgia* (lotação da
área estéril, objetos não permitidos como celular/garrafa). Um arquivo que não é vídeo é recusado com
mensagem clara.

✅ **Prova:** telas `02`, `03` em `docs/assets/fase4/telas/` · relatório §4 (URFD: sensibilidade 0,90 e
especificidade 0,95 em 70 vídeos).

---

## Parte C — Análise de áudio

### C1. Processar o áudio de uma consulta
**Exigência:** *"Processar áudios de consultas médicas."*

1. **Monitoramento** → aba **Áudio** → paciente **Bento Guerra** (Pneumologia, 27B).
2. **Usar áudio de exemplo** → *"Consulta · falta de ar (sintético)"* → **Analisar áudio** → **Abrir resultado**.

### C2. Transcrição com Azure Speech to Text
**Exigência:** *"Utilizar Azure Speech to Text para transcrever e analisar os áudios."*

**Deve aparecer:**

- **Transcrição** frase a frase, com o instante de cada uma (clique e o áudio pula para o trecho).
- **Modelos aplicados:** *Azure Speech to Text — **Azure***.
- Sem chave Azure: *Whisper (local)* e o aviso *"Azure Speech não configurado — transcrição feita
  localmente"*.

### C3. Termos críticos e sentimento com Azure Text Analytics
**Exigência:** *"Identificar termos críticos e sentimentos com Azure Text Analytics."*

**Deve aparecer:**

- Na transcrição, por severidade: **"falta de ar"** e **"dor no peito"** em vermelho (crítico),
  **"chiado no peito"** e **"cansaço"** em laranja (atenção) e **"febre" riscada** (o paciente *negou* febre —
  negação reconhecida pelo Text Analytics for Health, não gera alerta).
- **Sentimento:** *Negativo* (~0,9).
- **Entidades de saúde** (Text Analytics for Health) e frases-chave.
- **Modelos aplicados:** *Azure Text Analytics (Language) — **Azure***. Antes de ir ao Azure, o texto é
  **anonimizado** (LGPD).

### C4. Alterações vocais (cansaço, dificuldade respiratória)
**Exigência:** *"Detectar alterações vocais indicativas de condições médicas."*

**Deve aparecer (mesma análise):** **Indicadores vocais** com *"Sinais vocais de dificuldade
respiratória"* (frases curtas, pausas frequentes) e *"Sinais vocais de fadiga"*; **Eventos sonoros**
(modelo treinado no AudioSet) com *"Respiração audível"*; gráfico de F0/intensidade com as pausas.

Outros exemplos para comparar:

| Exemplo de áudio | Deve aparecer |
|---|---|
| *Consulta · fala fluente* | Sem indicadores vocais; "dor no peito/falta de ar" **negados** |
| *Consulta · sinais de fadiga* | **Sinais vocais de fadiga** (atenção) |
| *Tosses reais (ESC-50)* | **Tosse frequente** (atenção) |
| *Respiração (ESC-50)* | **Respiração audível** + inspirações bruscas |
| *Vogal sustentada · saudável × disfonia (VOICED)* | Sem achado; qualidade vocal **0,00 × 0,26** e o aviso "Pouca fala no áudio" |

✅ **Prova:** telas `04`, `11`, `12` · relatório §5 (VOICED, ESC-50) e §8 (prova do Azure).

---

## Parte D — Detecção de anomalias

### D1. Sinais vitais em tempo real
**Exigência:** *"Séries temporais de sinais vitais (batimentos, pressão arterial, oxigenação)"* e
*"anomalias em tempo real."*

1. **Monitoramento** → aba **Tempo real** → paciente **Liam Montenegro**.
2. **Fonte dos dados:** *"Cenário sintético · deterioração tipo sepse"*; **Velocidade do replay:** *10×*.
3. **Iniciar** (dura ~30 s nessa velocidade).

**Deve aparecer:** gráficos de FC, pressão, SpO₂ e FR chegando ao vivo, pontos anômalos em vermelho,
**score de anomalia** subindo até *"Anômalo — avise a equipe"*, e no feed (e na janela da enfermeira):
*Taquipneia*, *Deriva de PAM: queda progressiva*, ***Índice de choque elevado*** (crítico), *PAS baixa*,
*SpO2 baixa*, *Taquicardia*.

Dados **reais** de UTI: fonte *"PhysioNet · UTI real (MIMIC-II, registro 203) — episódio hipotensivo"*.

### D2. Evolução de prescrições
**Exigência:** *"Evolução de prescrições (alterações inesperadas no tratamento)."*

1. Menu **Pacientes** → **Matheus Garcia** (Geriatria, 19C).
2. No cartão **Monitoramento multimodal**, clique **Recalcular agora**.

**Deve aparecer:** na **Linha do tempo das prescrições**, o alerta **"Salto de dose: Morfina ×5.0"**.
Outros pacientes com alterações plantadas no seed:

| Paciente | Alteração esperada |
|---|---|
| Enrico Montenegro | Salto de dose: Insulina glargina ×2.6 |
| Liam Montenegro | Alergia registrada: Piperacilina-tazobactam |
| Maria Julia da Mata | Suspensão abrupta: Apixabana |
| Juan da Mata | Duplicidade terapêutica: anticoagulantes |
| Luiz Fernando Jesus | Dose acima da máxima diária: Dipirona |
| Thomas Moreira | Tratamento instável: Tramadol |

### D3. Padrões de movimentação durante a internação
**Exigência:** *"Padrões de movimentação do paciente durante a internação."*

No mesmo cartão do **Matheus Garcia**, gráfico **Mobilidade**: **"Agitação noturna acima da linha de base
diurna"** e **"Saída do leito à noite"**. Em **Ísis Barros**: **"Sem mudança de decúbito há 5.0 h"**
(risco de lesão por pressão). E a **queda em vídeo** do bloco B2.

### D4. Alertas automáticos para a equipe médica
**Exigência:** *"Gerar alertas automáticos para a equipe médica com base nas anomalias detectadas."*

1. Na janela da **Enf. Carla**: observe os avisos chegando durante B2, C1 e D1 (rajadas de atenção vêm
   agrupadas; crítico aparece sozinho, em destaque).
2. Menu **Alertas**: cada alerta tem a **origem** (vídeo, áudio, sinais, prescrição, mobilidade, fusão),
   a evidência, a recomendação e o link **ver análise**. Clique **Reconhecer**.
3. Entre como **auditor** → **Auditoria**: as ações `monitoring.analysis.create`, `monitoring.analysis.view`,
   `monitoring.scan`, `alert.ack` estão registradas → **Verificar integridade da cadeia** (ok).

✅ **Prova:** telas `05`, `06`, `08` · relatório §6 e §7.

---

## Parte E — Objetivos do edital

### E1. Fusão de texto, áudio e vídeo
**Exigência:** *"Realizar a análise e fusão de diferentes tipos de dados médicos."*

1. Depois do bloco C1 (áudio do Bento Guerra), vá a **Pacientes** → **Bento Guerra** → **Recalcular agora**.

**Deve aparecer:** **Risco fundido: Crítico** e o achado **"Sinais concordantes de desconforto respiratório
(áudio da consulta + sinais vitais + relato transcrito)"** — três fontes independentes concordando (voz,
SpO₂ do prontuário e o que o paciente disse). Os chips por modalidade mostram a contribuição de cada uma.

### E2. Serviços em nuvem → Parte A, C2 e C3.
### E3. Anomalias em tempo real → D1 e D4.

✅ **Prova:** tela `07_paciente_fusao.jpg` · relatório §7.

---

## Parte F — Entregáveis

| Entregável | Onde conferir |
|---|---|
| Código-fonte completo | Este repositório; CI verde no GitHub Actions; `make test-multimodal` roda os testes da Fase 4 sem rede |
| Relatório técnico: fluxo multimodal, modelos por tipo de dado, resultados e exemplos de anomalias | Entre como **auditor** → **Documentação** → *Fase 4 · Monitoramento multimodal* → **Relatório Técnico da Fase 4** (também em [`RELATORIO_TECNICO_FASE4.md`](RELATORIO_TECNICO_FASE4.md) e PDF) |
| Resultados medidos (reprodutíveis) | `multimodal/reports/*.json` e `docs/assets/fase4/`; para refazer: `make fase4-eval` (demorado) |
| Checklist do edital | [`EVIDENCIAS_FASE4.md`](EVIDENCIAS_FASE4.md) |
| Vídeo (≤ 15 min) | Link: **(preencher com o link do YouTube/Vimeo)** · roteiro em [`ROTEIRO_VIDEO_FASE4.md`](ROTEIRO_VIDEO_FASE4.md) |

**Pela linha de comando** (alternativa às telas): `make fase4-demo` (vídeo de queda, agachamento e áudio
com falta de ar) e `make azure-check` (chamada real ao Azure).

---

## Parte G — Mais exemplos reais

A tela tem **13 vídeos e 10 áudios** de exemplo (licença de cada um na tela): quedas reais da URFD,
afundo, teste *Timed Up and Go*, marcha com Parkinson, tosses e respiração reais, estridor, chiado e vozes
do VOICED. O resultado esperado de cada um — inclusive o que **não** é detectado (limitações) — está em
[`data/samples/exemplos/LEIAME.md`](../../data/samples/exemplos/LEIAME.md).

---

## Parte H — Se algo não sair como descrito

| O que acontece | Por quê / o que fazer |
|---|---|
| Análise demora na primeira vez | Está baixando os modelos (ver 0.5). As seguintes são rápidas |
| Selo "Modo local" | Sem chave Azure — ver 0.4 e [GUIA_AZURE.md](GUIA_AZURE.md) |
| Fila "Na fila" | Uma análise pesada por vez (CPU); a próxima começa sozinha |
| Áudio leva ~2 min | Whisper local em CPU; com o Azure a transcrição é bem mais rápida |
| Não aparece aviso na janela da enfermeira | Confira se ela está logada (a página precisa estar aberta); os alertas também ficam em **Alertas** |
| "Análise interrompida porque o servidor reiniciou" | A API reiniciou no meio; envie de novo |
| Paciente sem dados no cartão multimodal | Clique **Recalcular agora** |

---

## Checklist rápido

| # | Exigência do edital | Bloco | ☐ |
|---|---|---|---|
| 1 | Processar vídeos clínicos (fisioterapia/cirurgia) | B1, B4 | ☐ |
| 2 | OpenPose para análise postural | B1 | ☐ |
| 3 | YOLOv8 para objetos e áreas críticas | B2, B4 | ☐ |
| 4 | Relatórios automáticos de desvios | B3 | ☐ |
| 5 | Processar áudios de consultas | C1 | ☐ |
| 6 | Alterações vocais (cansaço, dificuldade respiratória) | C4 | ☐ |
| 7 | Azure Speech to Text | C2 | ☐ |
| 8 | Termos críticos e sentimentos com Azure Text Analytics | C3 | ☐ |
| 9 | Anomalias em sinais vitais | D1 | ☐ |
| 10 | Anomalias na evolução de prescrições | D2 | ☐ |
| 11 | Anomalias de movimentação na internação | D3, B2 | ☐ |
| 12 | Alertas automáticos à equipe médica | D4 | ☐ |
| 13 | Fusão de texto, áudio e vídeo | E1 | ☐ |
| 14 | Serviços em nuvem | A, C2, C3 | ☐ |
| 15 | Anomalias em tempo real | D1, D4 | ☐ |
| 16 | Relatório técnico (fluxo, modelos, resultados, exemplos) | F | ☐ |
| 17 | Vídeo ≤ 15 min | F | ☐ |
