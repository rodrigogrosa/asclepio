# Exemplos reais para testar a Fase 4

Vídeos e áudios públicos, com licença aberta, que aparecem na tela **Monitoramento** em
**Usar vídeo de exemplo** / **Usar áudio de exemplo** (os áudios ficam em `data/samples/audio/`).
Os vídeos da URFD (quedas) não são redistribuídos aqui: a plataforma baixa do site oficial na
primeira vez e confere o SHA-256 (`multimodal/asclepio_multimodal/assets.py`).

| Exemplo | Perfil | O que a plataforma mostra (medido em 28/10/2026) |
|---|---|---|
| Afundo (avanço), várias repetições | Fisioterapia · agachamento | 7 repetições, sem desvios; trechos atípicos informativos |
| Teste Timed Up and Go | Quarto | Nenhum achado: execução normal, sem queda |
| Marcha · Parkinson com bloqueios (1 e 2) | Quarto | Nenhum achado — **limitação**: não há perfil de análise de marcha |
| Marcha · Parkinson com discinesia (35 s) | Quarto | Nenhum achado (mesma limitação) |
| URFD fall-22 / fall-26 | Quarto | **Possível queda** (atenção): o clipe termina na queda |
| URFD adl-12 | Quarto | Nenhum achado (correto) |
| Tosses reais (ESC-50) | Áudio | **Tosse frequente** (atenção) |
| Respiração (ESC-50) | Áudio | **Respiração audível** + inspirações bruscas |
| Respiração ofegante | Áudio | **Inspirações bruscas** (atenção) |
| Estridor | Áudio | **Qualidade vocal alterada** — não há classe de estridor; som tonal anormal |
| Chiado pulmonar (estetoscópio) | Áudio | Nenhum achado — **limitação** do modelo AudioSet |
| Vogal sustentada · saudável × disfonia (VOICED) | Áudio | Sem achado; qualidade vocal 0,00 × 0,26 (limiar de atenção 0,33) |

## Créditos e licenças
- `afundo_lunge.webm` — Wikimedia Commons, *Forward lunge training*, CC BY-SA 4.0.
- `tug_teste_mobilidade.mp4` — CDC/STEADI, *The Timed Up and Go (TUG) Test* (domínio público), trecho 46–67 s.
- `parkinson_marcha_bloqueio_1.ogv`, `_2.ogv` — Arias & Cudeiro, *Effect of Rhythmic Auditory Stimulation on Gait in
  Parkinsonian Patients with and without Freezing*, PLoS ONE 5(3): e9675 (2010), vídeos S1 e S3, CC BY 2.5.
- `parkinson_discinesia.mp4` — Wikimedia Commons, *Cueing for Levodopa-Induced Dyskinesias in Parkinson's Disease*, Video 1
  (primeiros 35 s), CC BY 4.0.
- `../audio/tosses_esc50.wav`, `respiracao_esc50.wav` — Piczak, *ESC-50* (2015), clipes das classes coughing e
  breathing concatenados e convertidos para 16 kHz, CC BY-NC 3.0 (uso não comercial).
- `../audio/respiracao_ofegante.ogg` — Wikimedia Commons, *Breathing man.ogg*, domínio público.
- `../audio/estridor.ogg`, `chiado_wheeze.ogg` — Wikimedia Commons, *Stridor NP OGG.ogg* e *Wheeze2O.ogg*, CC BY-SA 3.0.
- `../audio/voz_saudavel_voiced002.wav`, `voz_disfonia_voiced001.wav` — Cesari et al., *VOICED* (PhysioNet, 2018),
  registros voice002 e voice001, ODC-By 1.0.
- URFD — Kwolek & Kepski, *UR Fall Detection Dataset* (2014), uso em pesquisa (baixado sob demanda).
