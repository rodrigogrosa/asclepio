---
id: MOD-007
titulo: Modelo de Pedido de Parecer (Interconsulta)
tipo: modelo
categoria: documentacao
setor: Todas as unidades assistenciais
versao: "2.0"
atualizado_em: 2026-03-12
responsavel: "Núcleo de Qualidade e Segurança do Paciente — HU-FIAP"
tags: [parecer, interconsulta, nefrologia, lesão renal aguda, KDIGO, comunicação entre equipes]
---

# MOD-007 — Modelo de Pedido de Parecer (Interconsulta)

## Finalidade
Padronizar a solicitação e a resposta de pareceres entre especialidades no HU-FIAP, garantindo pergunta clínica objetiva, urgência classificada e resposta acionável.

## Quando usar
- Sempre que a equipe assistente necessitar de opinião, conduta ou procedimento de outra especialidade para paciente internado ou em observação.
- Em risco iminente, acionar por telefone e registrar depois.

## Estrutura / campos obrigatórios
1. Identificação, prontuário, leito, equipe solicitante e contato.
2. **Especialidade solicitada.**
3. **Urgência:** rotina (48 h), prioritário (24 h) ou urgente (2 h, com contato telefônico prévio).
4. **Resumo clínico:** motivo da internação, comorbidades, evolução, medicações, alergias.
5. **Pergunta objetiva.**
6. **Exames relevantes** com datas e valores; assinatura e CRM.
7. **Resposta do parecerista:** data/hora, avaliação, impressão, condutas (quem executa), seguimento, assinatura e CRM.

## Modelo
```
PEDIDO DE PARECER — HU-FIAP
Paciente: [NOME DO PACIENTE]  Prontuário: [HU-000000]  Idade: [IDADE]  Leito: [LEITO]
Equipe: [EQUIPE]  Contato: [RAMAL]  Data/hora: [DATA] [HORA]
Especialidade solicitada: [ESPECIALIDADE]
Urgência: [ ] Rotina (48 h)  [ ] Prioritário (24 h)  [ ] Urgente (2 h — telefonema às [HORA])
Resumo clínico: [MOTIVO, COMORBIDADES, EVOLUÇÃO, MEDICAÇÕES, ALERGIAS]
Pergunta objetiva: [O QUE SE ESPERA DO PARECER]
Exames relevantes: [EXAME — DATA — VALOR]
Solicitante: [MÉDICO RESPONSÁVEL] — CRM [UF] [NÚMERO]

RESPOSTA DO PARECERISTA — Data/hora: [DATA] [HORA]
Avaliação: [HISTÓRIA/EXAME DIRIGIDOS]   Impressão diagnóstica: [DIAGNÓSTICO]
Condutas sugeridas: [CONDUTA — RESPONSÁVEL]   Procedimentos: [SIM/NÃO — QUAL]
Seguimento: [ ] Acompanhamento conjunto  [ ] Reavaliação em [N] dias  [ ] Parecer único
Parecerista: [MÉDICO RESPONSÁVEL] — CRM [UF] [NÚMERO]
```

## Exemplo preenchido
C. E. N., 66 anos, feminino. Prontuário HU-000432. Leito 5C-03. Clínica Médica 1, ramal 4512. 09/03/2026, 10h30. **Especialidade: Nefrologia. Urgência: prioritário (24 h).**

**Resumo clínico:** internada há 4 dias por pielonefrite aguda, em uso de ceftriaxona 2 g IV 1x/dia (D4). Em uso de losartana 100 mg/dia e hidroclorotiazida 25 mg/dia. Recebeu contraste iodado em TC de abdome em 06/03. Evoluiu com diurese de 0,4 mL/kg/h nas últimas 12 h e elevação de creatinina.

**Pergunta objetiva:** lesão renal aguda KDIGO estágio 2 (PROT-010) — há indicação de investigação adicional, ajuste de medicações ou terapia renal substitutiva?

**Exames:** creatinina basal 1,0 mg/dL; 05/03: 1,1; 07/03: 1,6; 09/03: **2,3 mg/dL** (2,3× basal); potássio 5,4 mEq/L; urina I: proteína +, leucócitos 40/campo; US de rins (08/03) sem hidronefrose. Solicitante: [MÉDICO RESPONSÁVEL] — CRM [UF] [NÚMERO].

**Resposta (09/03/2026, 15h10):** paciente discretamente hipovolêmica, sem congestão. **Impressão:** LRA KDIGO 2, multifatorial (contraste iodado, hipovolemia, BRA e diurético). **Condutas:** suspender losartana e hidroclorotiazida; cristaloide balanceado 500 mL e reavaliar diurese em 6 h; ceftriaxona sem ajuste; evitar AINEs e novo contraste; creatinina e eletrólitos diários. Sem critérios para diálise. **Seguimento:** conjunto, reavaliação em 24 h. Parecerista: [MÉDICO RESPONSÁVEL] — CRM [UF] [NÚMERO].

## Boas práticas e erros comuns
- Formular **uma pergunta clara**; "avaliar paciente" é inespecífico.
- Erro comum: classificar tudo como "urgente"; urgente exige contato telefônico.
- O parecer é consultivo; a equipe assistente mantém a responsabilidade pelo paciente.

## Referências
1. Conselho Federal de Medicina. Resolução CFM nº 2.217/2018 — Código de Ética Médica.
2. KDIGO. Clinical Practice Guideline for Acute Kidney Injury. Kidney Int Suppl. 2012.
3. Núcleo de Qualidade HU-FIAP. Fluxo de interconsultas e prazos de resposta, março/2026.

---
*Modelo institucional fictício para fins acadêmicos (Tech Challenge FIAP). Não substitui normas oficiais nem julgamento clínico.*
