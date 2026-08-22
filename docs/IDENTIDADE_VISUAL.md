# Identidade Visual — Asclépio

Inspirada na identidade da FIAP: **fundo quase preto, rosa-magenta vibrante, tipografia pesada em caixa alta, muito contraste, pouca ornamentação**. Dark-mode only (como o site da FIAP).

## Nome
**Asclépio** — deus grego da medicina; seu bastão com uma serpente é o símbolo universal da medicina.
Tagline: **Assistente Clínico Inteligente**. Subtítulo institucional: *Hospital Universitário FIAP (fictício) · Tech Challenge 8IADT · Fase 3*.

## Logo
- `docs/assets/brand/asclepio-mark.svg` — símbolo (bastão branco + serpente rosa + nós de rede neural), app icon / favicon.
- `docs/assets/brand/asclepio-logo-horizontal.svg` — lockup horizontal com wordmark.
- Wordmark: `ASCLÉPIO` em Montserrat 800, letter-spacing 0.04em, o **É** em rosa.

## Tokens (Tailwind `theme.extend`)
| Token | Valor | Uso |
|---|---|---|
| `bg` | `#0B0B10` | fundo da página |
| `surface` | `#14141B` | cards, sidebar |
| `surface-2` | `#1C1C26` | inputs, hover, tabelas zebra |
| `border` | `#2A2A38` | bordas sutis |
| `text` | `#F5F5F7` | texto principal |
| `muted` | `#9A9AAB` | texto secundário |
| `primary` | `#ED145B` | rosa FIAP — ações primárias, destaques |
| `primary-hover` | `#FF3D7F` | hover |
| `primary-dark` | `#C40A4A` | gradientes / pressed |
| `accent` | `#7B2FF7` | fim de gradiente (rosa → roxo) |
| `success` | `#2ECC71` | ok / aprovado |
| `warning` | `#F5A623` | atenção |
| `danger` | `#FF4D4F` | crítico / bloqueado |
| `info` | `#3AA0FF` | informativo |

- Gradiente de marca: `linear-gradient(135deg, #ED145B 0%, #7B2FF7 100%)`.
- Raio: cards `16px`, botões/inputs `12px`, chips `999px`.
- Sombras: quase nenhuma; use borda `border` + leve glow rosa em foco (`0 0 0 3px rgba(237,20,91,.35)`).
- Tipografia: **Montserrat** (títulos, 700/800, uppercase com tracking em labels de seção) + **Inter** (corpo). Via `next/font/google`.
- Ícones: `lucide-react`, stroke 1.75.
- Dados clínicos críticos sempre com cor semântica + ícone (nunca só cor).
- Tom de voz da UI: direto, didático, em pt-BR. Termos: "Assistente", "Fluxos clínicos", "Pacientes", "Auditoria", "Modelo".

## Padrões de componente
- Sidebar fixa à esquerda (240px) com logo no topo, itens com ícone + label, item ativo com barra rosa à esquerda.
- Header com título da página, breadcrumb e avatar/perfil (nome + papel) à direita.
- Cards KPI: valor grande (Montserrat 800), label muted em caixa alta, ícone rosa.
- Badges de severidade: `critico` danger, `alto` danger-outline, `moderado` warning, `baixo` success, `info` info.
- Badge do guardrail: `aprovado` success, `ajustado` warning, `bloqueado` danger.
- Citações/fontes: chips numerados `[1]`, `[2]` no texto e painel lateral "Fontes" com título do documento, seção, score e trecho.
- Disclaimer fixo no chat: "Sugestões do Asclépio são apoio à decisão e exigem validação de um profissional habilitado."
