# Checklist e evidências da Fase 4 — onde cada exigência está

> Para a avaliação: cada linha do edital da Fase 4, o **status**, **onde ver no sistema**, **onde está
> no código** e **a prova** (teste, avaliação com números medidos ou artefato). Entre como
> `dra.ana@asclepio.fiap` / `Asclepio@2026` (médica) para as telas clínicas; `admin` vê tudo.
> URLs consideram `make up` (Web `:3000`, API `:8000`).

Legenda: ✅ concluído e provado · 🟡 concluído, depende de ação do avaliador/aluno (ex.: chave Azure, gravação do vídeo)

**Prova de uso real:** prints das telas rodando em Docker em [`docs/assets/fase4/telas/`](../assets/fase4/telas/)
(relatório §8.1): integração Azure e modelos, queda detectada com alerta em tempo real, análise de áudio
com termos críticos (e negação), monitor ao vivo, painel multimodal com concordância de 3 fontes e a lista
de alertas da equipe.

## 1. Análise de vídeo

| Exigência do edital | Status | Onde ver | Código | Prova |
|---|---|---|---|---|
| Processar vídeos clínicos (fisioterapia ou cirurgia gravada) | ✅ | **Monitoramento → Vídeo**: enviar arquivo ou escolher exemplo (agachamento, agachamento unipodal, quarto) → acompanhar etapas → resultado | `multimodal/asclepio_multimodal/video/` · `backend/asclepio_api/services/monitoring.py` | `make fase4-demo`; testes `multimodal/tests/test_video*.py` |
| Detectar movimentos/eventos fora do padrão com **OpenPose** (postura) | ✅ | Resultado da análise: vídeo anotado com o esqueleto de 18 pontos, gráfico dos ângulos, achados com o trecho (s) | `video/pose.py` (OpenPose COCO, pesos oficiais CMU via OpenCV DNN) | Relatório §4; ADR-0006 |
| … e **YOLOv8** para objetos e áreas críticas | ✅ | Caixas e zonas críticas no vídeo anotado; perfis *quarto* (chão/leito) e *cirurgia* (área estéril, objetos não permitidos) | `video/detect.py` (Ultralytics YOLOv8n) | Relatório §4 |
| Relatórios automáticos com desvios/falhas do procedimento | ✅ | Detalhe da análise → **Relatório** (Markdown, baixável), quadros-chave anotados, vídeo anotado H.264 | `video/report.py` | `docs/assets/fase4/video/` (exemplos) |

## 2. Análise de áudio

| Exigência do edital | Status | Onde ver | Código | Prova |
|---|---|---|---|---|
| Processar áudios de consultas | ✅ | **Monitoramento → Áudio**: enviar arquivo (WAV/MP3/M4A/OGG/WEBM) ou exemplo (fluente, fadiga, falta de ar) | `multimodal/asclepio_multimodal/audio/` | testes `multimodal/tests/test_audio*.py` |
| Detectar alterações vocais (cansaço, dificuldade respiratória) | ✅ | Detalhe da análise → **Indicadores vocais** (fadiga, dificuldade respiratória, alteração articulatória) com a evidência acústica; eventos sonoros (tosse, respiração) | `audio/features.py` (Praat), `audio/vocal.py`, `audio/events.py` (AST · AudioSet) | Avaliação com o **VOICED (PhysioNet)** — Relatório §5 |
| Transcrever e analisar com **Azure Speech to Text** | 🟡 | Transcrição com tempo por palavra; "Modelos aplicados: Azure Speech to Text (azure)"; selo **Integração Azure: conectado** no topo da tela | `audio/azure_speech.py` | `make azure-check` (chamada real); testes com SDK simulado. Requer chave (F0 gratuito): `docs/fase4/GUIA_AZURE.md` |
| Termos críticos e sentimentos com **Azure Text Analytics** | 🟡 | Transcrição com termos críticos destacados (com negação: "nega febre"), entidades de saúde, sentimento por frase, frases-chave | `audio/azure_text.py` (Text Analytics for Health + sentimento) — texto **anonimizado** antes do envio | idem; sem chave, cai para o léxico clínico local e a tela avisa |

## 3. Detecção de anomalias

| Exigência do edital | Status | Onde ver | Código | Prova |
|---|---|---|---|---|
| Séries temporais de sinais vitais (FC, PA, SpO2) | ✅ | **Monitoramento → Tempo real**: paciente + fonte (PhysioNet ou cenário) → gráficos ao vivo com pontos anômalos e score | `anomaly/vitals.py` (limites · z-score robusto · CUSUM/EWMA · Isolation Forest · antiflood) | Avaliação com **PhysioNet** — Relatório §6 |
| Evolução de prescrições (alterações inesperadas) | ✅ | **Paciente → Monitoramento multimodal → Recalcular agora** → linha do tempo de prescrições com o achado (salto de dose, alergia, suspensão abrupta) | `anomaly/prescriptions.py` | Avaliação contra o gabarito sintético — Relatório §6 |
| Padrões de movimentação na internação | ✅ | Mesmo painel → gráfico de mobilidade (imobilidade ≥ 2 h, agitação noturna, saída do leito, queda); queda também pelo vídeo do quarto | `anomaly/mobility.py`; perfil `quarto` do vídeo | Avaliação URFD (quedas) + gabarito sintético — Relatório §4 e §6 |
| Alertas automáticos para a equipe médica | ✅ | Toast em tempo real em qualquer tela; **Alertas** com a origem (vídeo, áudio, sinais, prescrição, mobilidade, fusão) e o link para a análise; reconhecer (ack); webhook opcional (Teams/Slack) | `services/alerts.py`, `services/events.py`, `GET /alerts/stream` (SSE) | `backend/tests/test_monitoring.py` |

## 4. Objetivos

| Objetivo | Status | Evidência |
|---|---|---|
| Análise e **fusão** de texto, áudio e vídeo | ✅ | `multimodal/asclepio_multimodal/fusion.py` (fusão tardia + concordância entre modalidades); painel do paciente mostra o risco fundido e a contribuição de cada modalidade |
| Serviços em nuvem para ampliar processamento e inteligência | 🟡 | Azure Speech to Text + Azure Text Analytics (ADR-0007, `GUIA_AZURE.md`) |
| Detecção de anomalias **em tempo real** | ✅ | Detector online + SSE (`/monitoring/live/stream`, `/alerts/stream`); Relatório §6–§7 |

## 5. Entregáveis

| Entregável | Status | Onde |
|---|---|---|
| Código-fonte completo | ✅ | Este repositório (`multimodal/`, `backend/`, `frontend/`), CI no GitHub Actions |
| Relatório técnico: descrição do fluxo multimodal | ✅ | `docs/fase4/RELATORIO_TECNICO_FASE4.md` §2–§3 (+ PDF) |
| Relatório técnico: modelos aplicados em cada tipo de dado | ✅ | idem §3 (tabela) e §4–§6 |
| Relatório técnico: resultados e exemplos de anomalias detectadas | ✅ | idem §4–§7, figuras em `docs/assets/fase4/`, números em `multimodal/reports/*.json` |
| Vídeo (≤ 15 min) no YouTube/Vimeo | 🟡 | Roteiro cena a cena: `docs/fase4/ROTEIRO_VIDEO_FASE4.md` (gravação e upload são do aluno) |
