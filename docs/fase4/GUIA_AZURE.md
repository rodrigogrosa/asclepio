# Guia de configuração do Azure — Fase 4

O Asclépio usa dois serviços gerenciados do **Azure AI Services** na análise de áudio das consultas:

| Serviço | Para quê | Recurso no Azure | Tier |
|---|---|---|---|
| **Azure Speech to Text** | Transcrever a consulta em pt-BR com o instante de cada palavra (ritmo da fala, pausas) | *Speech* (`SpeechServices`) | F0 (gratuito: 5 h de áudio/mês) |
| **Azure Text Analytics** (AI Language) | Termos críticos (Text Analytics for Health: sintomas, diagnósticos, medicamentos, com negação), sentimento por frase e frases-chave | *Language* (`TextAnalytics`) | F0 (gratuito: 5 mil registros de texto/mês) |

Sem as chaves, a plataforma continua funcionando em **modo local** (Whisper + léxico clínico) e avisa na
tela **Monitoramento** ("Integração Azure: modo local"). Com as chaves, o selo muda para "conectado" e
cada relatório de áudio lista `Azure Speech to Text` e `Azure Text Analytics` em "Modelos aplicados".

## Opção A — automático (Azure CLI), 3 minutos

Pré-requisitos: conta Azure (para estudantes: <https://azure.microsoft.com/free/students/>, sem cartão)
e a Azure CLI (`brew install azure-cli` no macOS; no Windows/WSL e Linux:
<https://learn.microsoft.com/cli/azure/install-azure-cli>).

```bash
cd ~/asclepio
make azure-setup      # faz login, cria rg-asclepio + Speech F0 + Language F0 em brazilsouth e grava as chaves no .env
make azure-check      # chamada real aos dois serviços com um áudio de exemplo
make up               # reinicia a API com as chaves
```

Para apagar tudo depois da avaliação: `az group delete -n rg-asclepio --yes`.

## Opção B — pelo portal

1. <https://portal.azure.com> → **Criar um recurso** → procure **Speech** → *Criar*.
   Grupo de recursos `rg-asclepio`, região **Brazil South**, nome `asclepio-speech-<suas iniciais>`,
   tipo de preço **Free F0** → *Revisar + criar*.
2. Abra o recurso → **Chaves e ponto de extremidade** → copie a **Chave 1** e a **Região**.
3. **Criar um recurso** → procure **Language service** → *Criar* (pode pular os recursos extras) →
   mesma região e grupo, preço **Free F0**, marque o aviso de IA responsável → *Criar*.
4. Abra o recurso → **Chaves e ponto de extremidade** → copie a **Chave 1** e o **Ponto de extremidade**.
5. No arquivo `.env` da pasta do projeto:

```dotenv
AZURE_SPEECH_KEY=<chave 1 do Speech>
AZURE_SPEECH_REGION=brazilsouth
AZURE_LANGUAGE_KEY=<chave 1 do Language>
AZURE_LANGUAGE_ENDPOINT=https://<seu-recurso>.cognitiveservices.azure.com/
```

6. `make azure-check` e depois `make up`.

> Só é permitido **um** recurso Language F0 por assinatura. Se já existir, reutilize as chaves dele.

## Privacidade (LGPD)

- O **áudio** precisa ir ao Speech (o serviço transcreve o som); use região brasileira (`brazilsouth`).
- A **transcrição é anonimizada** pelo `asclepio_core.anonymizer` (nomes, CPF, telefone, endereço…)
  **antes** de ir ao Text Analytics; o relatório mostra quantos itens foram mascarados.
- As chaves ficam só no `.env` (fora do Git) e nunca aparecem na API nem na tela (o status mostra
  apenas "configurado" e a região/endpoint).
- Em produção, a instituição precisaria de contrato de operador de dados com a Microsoft e de
  avaliação de impacto (RIPD) — fora do escopo acadêmico.
