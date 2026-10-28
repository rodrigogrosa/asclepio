# Roteiro do vídeo da Fase 4 (≤ 15 min) — Asclépio

> O edital pede: upload no **YouTube ou Vimeo** (público ou não listado) e demonstração do processamento
> multimodal — **exemplo prático da análise de áudio e vídeo**, **detecção e resposta a anomalias**,
> **integração dos serviços Azure** e **fluxo final do alerta à equipe médica**. Cada cena abaixo indica
> o item do edital que cobre (🎯).

## Antes de gravar (checklist de 10 min)
1. `make azure-setup` (ou portal, `docs/fase4/GUIA_AZURE.md`) e `make azure-check` → os dois serviços com ✔.
2. `make fase4-assets` (pesos e vídeos de exemplo) e `make up`. Abra <http://localhost:3000>.
3. Rode **uma vez** um vídeo e um áudio de exemplo antes de gravar: a primeira execução baixa os modelos
   (Whisper/AST ~1,2 GB) e fica mais lenta. Na gravação, corte as esperas de processamento.
4. Duas janelas lado a lado: **Dra. Ana** (`dra.ana@asclepio.fiap`) e **Enf. Carla**
   (`enf.carla@asclepio.fiap`, aba anônima), senha `Asclepio@2026`. Gravação em 1080p.
5. Opcional: portal do Azure aberto no recurso Speech → *Métricas* (prova das chamadas).

## Cenas

| Tempo | Cena | O que mostrar / falar | 🎯 Edital |
|---|---|---|---|
| 0:00–0:50 | **Abertura e desafio** | "Fase 4: o hospital quer monitorar continuamente o paciente com vídeo, áudio e texto para achar sinais precoces de risco." Diagrama do fluxo multimodal (relatório §2). | contexto |
| 0:50–1:40 | **Monitoramento e Azure** | Dra. Ana → menu **Monitoramento**. Cabeçalho: **Integração Azure — Speech: conectado (brazilsouth) · Language: conectado**; modelos prontos (OpenPose, YOLOv8, Azure Speech, Azure Text Analytics, AST/AudioSet, Praat, detector online). | Azure |
| 1:40–4:00 | **Vídeo · fisioterapia** | Aba **Vídeo** → paciente → perfil *Fisioterapia* → exemplo **"agachamento unipodal"** → acompanhar as etapas (YOLOv8 → OpenPose → cinemática). Resultado: vídeo anotado com esqueleto de 18 pontos, gráfico dos ângulos, achado **"inclinação excessiva do tronco" (72° × limite 30°)** — clicar no achado leva o vídeo ao trecho. Abrir **Relatório** e baixar o Markdown. Mencionar o agachamento lateral com 6 repetições sem desvios. | vídeo · OpenPose · relatório automático |
| 4:00–5:30 | **Vídeo · queda no quarto (YOLOv8 + OpenPose)** | Perfil *Quarto* → exemplo **"paciente cai ao levantar (URFD)"**. Enquanto processa, mostrar a janela da **Enf. Carla**: o **toast crítico "Queda do paciente detectada"** chega sozinho. Abrir: quadro anotado (caixas do YOLOv8 + esqueleto), trecho 3–5 s. Citar o resultado no dataset: sensibilidade 0,90 e especificidade 0,95 em 70 vídeos. | vídeo · YOLOv8 · anomalia de movimentação · alerta |
| 5:30–8:00 | **Áudio · consulta com falta de ar** | Aba **Áudio** → exemplo **"Consulta · falta de ar"** → etapas: *Azure Speech to Text* → *anonimização* → *Azure Text Analytics* → *Praat* → *AudioSet*. Resultado: transcrição com o tempo das palavras; **termos críticos destacados** ("falta de ar", "dor no peito" = crítico); negação respeitada ("nega febre" não vira alerta); sentimento por frase; entidades de saúde; indicador **"dificuldade respiratória"** e **respiração audível** no gráfico de F0/intensidade. Em **Modelos aplicados**: "Azure Speech to Text — azure", "Azure Text Analytics — azure". (Opcional: portal Azure → métricas de chamadas.) | áudio · Azure Speech · Azure Text Analytics · alteração vocal |
| 8:00–10:00 | **Anomalias em tempo real · sinais vitais** | Aba **Tempo real** → paciente → fonte **"Cenário sintético · deterioração tipo sepse"** (ou **PhysioNet 203**) → *Iniciar*. Gráficos ao vivo de FC, PA/PAM, SpO2 e FR, pontos anômalos em vermelho, score subindo; feed de achados (deriva de PAM, taquipneia, **índice de choque** crítico). Os alertas chegam à Enf. Carla na hora. Falar das camadas (limites NEWS2 · z-score · CUSUM · Isolation Forest) e do antiflood (−97,8 % de alertas). | anomalias em séries · tempo real |
| 10:00–11:30 | **Prescrições, mobilidade e fusão** | **Pacientes** → paciente → card **Monitoramento multimodal** → *Recalcular agora*: linha do tempo de prescrição com o alerta (ex.: salto de dose de insulina / antibiótico para alérgico), gráfico de mobilidade (imobilidade > 2 h ou agitação noturna). **Risco fundido** e chips por modalidade; se houver áudio + sinais, o achado **"Sinais concordantes de desconforto respiratório (áudio + sinais vitais)"**. | prescrições · mobilidade · fusão |
| 11:30–13:00 | **Fluxo final do alerta à equipe** | Enf. Carla → **Alertas**: origem (vídeo, áudio, sinais, prescrição, mobilidade, fusão), mensagem com trecho e recomendação, link **ver análise** → **Reconhecer**. Admin/auditor → **Auditoria**: `monitoring.analysis.create`, `monitoring.analysis.view`, `alert.ack`; **Verificar integridade da cadeia**. (Opcional: `ALERT_WEBHOOK_URL` para um canal do Teams.) | fluxo do alerta |
| 13:00–14:20 | **Resultados e limites** | Relatório técnico §4–§6: URFD (0,90/0,95), VOICED (AUC 0,62 — triagem, não diagnóstico), PhysioNet 2009 (ensemble sensível 0,84; PAM mínima AUC 0,89), antiflood. Limitações (§11). | relatório |
| 14:20–15:00 | **Encerramento** | Checklist do edital (`EVIDENCIAS_FASE4.md`), repositório, como rodar (`make up`). | — |

Dicas: grave as cenas de processamento separadamente e corte a espera; deixe as perguntas/arquivos
prontos; mantenha a janela da enfermagem visível nas cenas de alerta — é a prova do tempo real.
