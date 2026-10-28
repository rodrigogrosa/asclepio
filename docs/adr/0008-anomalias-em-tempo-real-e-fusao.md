# ADR-0008: Anomalias em tempo real por camadas explicáveis e fusão tardia das modalidades

- **Status**: aceito · **Data**: 2026-10-28 · **Fase**: 4

## Contexto
O edital pede detecção de anomalias em sinais vitais, prescrições e mobilidade, com **alertas em
tempo real** à equipe, e fusão de texto, áudio e vídeo. Alerta demais vira ruído (fadiga de alarme);
alerta sem explicação não é acionável.

## Decisão
- **Sinais vitais, detector online em camadas**: limites fisiológicos (alinhados ao NEWS2 já usado
  na Fase 3) → z-score robusto (mediana/MAD) para mudanças bruscas → EWMA/CUSUM para deriva →
  Isolation Forest multivariado ajustado à linha de base do próprio paciente; com duração mínima,
  histerese e cooldown (antiflood). Cada achado traz os números que o justificam.
- **Prescrições e mobilidade**: regras clínicas declaradas (salto de dose, dose máxima, suspensão
  abrupta, alergia por classe, duplicidade; imobilidade ≥ 2 h, agitação noturna, saída do leito,
  queda) + pontuação estatística em relação ao histórico do paciente.
- **Tempo real**: barramento de eventos em memória + **SSE** (`/alerts/stream`, `/monitoring/live/stream`);
  todo alerta (fluxo, regra ou monitoramento) chega na hora a quem tem `alerts:read`; webhook
  opcional (Teams/Slack) para atenção/crítico.
- **Fusão tardia**: média ponderada dos riscos das modalidades presentes + regra de segurança (achado
  crítico ⇒ risco crítico) + **concordância entre modalidades** no mesmo eixo clínico (ex.: "falta de
  ar" no áudio + queda de SpO2) como achado próprio. Regras legíveis, sem modelo treinado.

## Alternativas
- Autoencoder/LSTM: exige dados rotulados em volume e é opaco para a equipe.
- Fusão precoce (concatenar features): modalidades com taxas e disponibilidades diferentes; perde a
  explicação por modalidade.

## Consequências
+ Explicável, testável e calibrável por paciente; funciona com poucas amostras. + Mesmo vocabulário
de severidade dos alertas da Fase 3. − Barramento em memória vale para um processo da API; com várias
réplicas vira Redis pub/sub (mesma interface).
