# ADR-0007: Azure AI (Speech to Text + Text Analytics) com modo local de reserva e texto anonimizado

- **Status**: aceito · **Data**: 2026-10-28 · **Fase**: 4

## Contexto
O edital pede **Azure Speech to Text** para transcrever consultas e **Azure Text Analytics** para
termos críticos e sentimento. As Fases 1–3 eram 100 % locais (nenhum dado sai da máquina). Áudio de
consulta e transcrição são dados de saúde (LGPD, art. 11).

## Decisão
- Integração real pelos **SDKs oficiais** (`azure-cognitiveservices-speech`,
  `azure-ai-textanalytics`): reconhecimento contínuo em pt-BR com timestamps por palavra; sentimento
  com opinion mining, frases-chave e **Text Analytics for Health** (sintomas, diagnósticos,
  medicamentos com negação).
- **Chaves só no `.env`** (`AZURE_SPEECH_KEY`, `AZURE_LANGUAGE_KEY`, …); `make azure-setup` cria os
  recursos F0 pela Azure CLI. A tela mostra se o Azure está conectado ou em modo local.
- **Minimização (LGPD)**: a transcrição passa pelo anonimizador do projeto **antes** de ir ao
  Text Analytics; o relatório registra quantos itens foram mascarados. Recurso em `brazilsouth`.
- **Modo local de reserva** (`STT_PROVIDER/TEXT_PROVIDER=auto`): sem chave ou com erro de cota, o
  Whisper transcreve e um léxico clínico pt-BR (com negação) acha termos críticos; o resultado declara
  o provedor usado em `warnings`/`models` — a análise nunca para por causa da nuvem.

## Alternativas
- Só Azure: a demonstração e a CI dependeriam de chave e de rede.
- Só local: não atende ao edital.

## Consequências
+ Atende ao edital sem perder a operação offline. + Testes rodam sem rede (SDK mockado).
− O áudio vai ao Azure (Speech não aceita texto anonimizado — precisa do som): documentado em
`docs/POLITICAS.md` e no relatório; em produção exigiria contrato de operador (DPA) com a Microsoft.
