---
id: MOD-008
titulo: Modelo de Atestado Médico
tipo: modelo
categoria: documentacao
setor: Todas as unidades assistenciais
versao: "2.0"
atualizado_em: 2026-03-18
responsavel: "Núcleo de Qualidade e Segurança do Paciente — HU-FIAP"
tags: [atestado médico, afastamento, declaração de comparecimento, CID, sigilo, CFM]
---

# MOD-008 — Modelo de Atestado Médico

## Finalidade
Padronizar a emissão de atestados e declarações de comparecimento no HU-FIAP, assegurando veracidade, sigilo e identificação do emitente.

## Quando usar
- Atestado de **afastamento** por doença, acidente ou procedimento, para fins trabalhistas, escolares ou previdenciários.
- **Declaração de comparecimento** quando não há afastamento, mas o paciente ou acompanhante esteve na unidade.

## Estrutura / campos obrigatórios
1. Cabeçalho institucional (HU-FIAP, endereço, CNPJ).
2. **Identificação do paciente:** nome completo e documento (RG ou CPF).
3. **Finalidade:** afastamento, comparecimento, acompanhante.
4. **Período de afastamento** em dias, **por extenso e em algarismos**, com data de início; ou horários de entrada e saída na declaração.
5. **CID-10 somente com consentimento expresso do paciente** (ou exigência legal), registrando "a pedido do paciente".
6. **Data e hora do atendimento**, assinatura, carimbo e CRM (ICP-Brasil se eletrônico).

## Modelo
```
HOSPITAL UNIVERSITÁRIO FIAP (HU-FIAP) — [ENDEREÇO] — CNPJ [CNPJ]

ATESTADO MÉDICO
Atesto, para os devidos fins, que [NOME DO PACIENTE], documento [RG/CPF], foi atendido(a)
neste serviço em [DATA], às [HORA], e necessita de afastamento de suas atividades
[LABORAIS / ESCOLARES] por [N] ([NÚMERO POR EXTENSO]) dia(s), a partir de [DATA DE INÍCIO].
CID-10: [CÓDIGO] — declarado a pedido do(a) paciente. [OU: omitido a pedido do(a) paciente]
[CIDADE], [DATA].   [MÉDICO RESPONSÁVEL] — CRM [UF] [NÚMERO]

DECLARAÇÃO DE COMPARECIMENTO
Declaro que [NOME DO PACIENTE], documento [RG/CPF], esteve neste serviço em [DATA],
das [HORA DE ENTRADA] às [HORA DE SAÍDA], para [CONSULTA / EXAME / ACOMPANHAR O(A)
PACIENTE [NOME], grau de parentesco [PARENTESCO]].
[CIDADE], [DATA].   [MÉDICO RESPONSÁVEL] — CRM [UF] [NÚMERO]
```

## Exemplo preenchido
**Atestado de afastamento** — Atesto, para os devidos fins, que **P. H. G., 34 anos**, documento RG [NÚMERO FICTÍCIO], foi atendido no Pronto-Socorro do HU-FIAP em 18/03/2026, às 07h40, e necessita de afastamento de suas atividades laborais por **3 (três) dias**, a partir de 18/03/2026. CID-10: J03.9 — declarado a pedido e com consentimento do paciente (registrado no prontuário HU-000777). São Paulo, 18/03/2026. [MÉDICO RESPONSÁVEL] — CRM [UF] [NÚMERO].

**Declaração de comparecimento** — Declaro que **D. M. V., 41 anos**, documento CPF [NÚMERO FICTÍCIO], esteve no Ambulatório de Endocrinologia do HU-FIAP em 18/03/2026, das 13h30 às 15h10, para consulta médica e coleta de exames. São Paulo, 18/03/2026. [MÉDICO RESPONSÁVEL] — CRM [UF] [NÚMERO].

## Boas práticas e erros comuns
- O atestado tem presunção de veracidade; atestar apenas o constatado no atendimento (Resolução CFM nº 1.658/2002, alterada pela nº 1.851/2008; Código de Ética Médica, art. 80).
- **Nunca incluir diagnóstico ou CID sem autorização** do paciente (sigilo, art. 73; LGPD — dados sensíveis), salvo dever legal ou justa causa.
- Escrever o número de dias **por extenso**; não deixar espaços em branco.
- Erro comum: atestado retroativo para datas sem avaliação, ou "em branco" a pedido de terceiros.
- Registrar no prontuário a emissão, o período e se o CID foi incluído; afastamento > 15 dias: orientar perícia do INSS.

## Referências
1. Conselho Federal de Medicina. Resolução CFM nº 1.658/2002 e Resolução CFM nº 1.851/2008 — atestados médicos.
2. Conselho Federal de Medicina. Resolução CFM nº 2.217/2018 — Código de Ética Médica, arts. 73, 80 e 91.
3. Núcleo de Qualidade HU-FIAP. Orientações para emissão de documentos médicos, março/2026.

---
*Modelo institucional fictício para fins acadêmicos (Tech Challenge FIAP). Não substitui normas oficiais nem julgamento clínico.*
