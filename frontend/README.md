# Asclépio — Frontend

Interface web do **Asclépio — Assistente Clínico Inteligente** (Tech Challenge FIAP · 8IADT · Fase 3).
Next.js 16 (App Router) · React 19 · TypeScript estrito · Tailwind CSS v4 · Recharts · react-markdown · mermaid · lucide-react.

Implementado **estritamente contra** `docs/CONTRATO_API.md` e a identidade em `docs/IDENTIDADE_VISUAL.md`.

## Rodar

```bash
cd frontend
cp .env.example .env.local      # ajuste NEXT_PUBLIC_API_URL / NEXT_PUBLIC_USE_MOCK
npm install
npm run dev                     # http://localhost:3000
```

| Variável | Padrão | Descrição |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000/api/v1` | Base da API FastAPI |
| `NEXT_PUBLIC_USE_MOCK` | `false` | `true` → usa fixtures locais (`lib/mock/`) para **todos** os endpoints, incluindo o stream SSE simulado. Não precisa de backend. |

Usuários de demonstração (senha `Asclepio@2026`): `admin@asclepio.fiap`, `dra.ana@asclepio.fiap`, `dr.marcos@asclepio.fiap`, `enf.carla@asclepio.fiap`, `auditor@asclepio.fiap`.

## Scripts

```bash
npm run dev      # desenvolvimento
npm run lint     # eslint
npx tsc --noEmit # typecheck
npm run build    # build de produção (output: standalone)
npm start        # serve o build
```

## Docker

```bash
docker build -t asclepio-frontend \
  --build-arg NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1 \
  --build-arg NEXT_PUBLIC_USE_MOCK=false .
docker run -p 3000:3000 asclepio-frontend
```

> As variáveis `NEXT_PUBLIC_*` são embutidas no build — passe-as como `--build-arg`.

## Estrutura

```
app/
  login/                 tela de login (usuários demo)
  (app)/                 área autenticada (sidebar + header)
    page.tsx             dashboard
    assistente/          chat com streaming SSE, fontes e explicabilidade
    pacientes/[id]/      lista e detalhe do paciente
    fluxos/[run_id]/     execuções LangGraph + validação humana
    alertas/ conhecimento/ modelo/ auditoria/
components/
  ui/                    Button, Card, Badge, Input, Tabs, Modal/Drawer, Table, Skeleton, Toast, EmptyState, KpiCard, badges de status, MarkdownView, JsonView
  layout/                Sidebar, Header, AppShell (guarda de rota)
  chat/ patients/ workflows/ alerts/ knowledge/ model/ audit/ dashboard/
lib/
  types.ts               tipos do contrato
  api.ts                 cliente fetch tipado + parser SSE (POST) + tratamento de 401
  api-types.ts           interface ApiClient (implementada por http e mock)
  mock/                  fixtures pt-BR + implementação mock
```

## Autenticação

Token JWT em `localStorage` (`asclepio.token`), enviado como `Authorization: Bearer`. Em `401` a sessão é limpa e o usuário é redirecionado para `/login`. A guarda de rota é client-side no layout `(app)`.
