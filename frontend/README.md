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

Usuários de demonstração (ambiente acadêmico, senha `Asclepio@2026`): `dra.ana@asclepio.fiap`, `dr.marcos@asclepio.fiap`, `enf.carla@asclepio.fiap`, `auditor@asclepio.fiap`. Os administradores (`admin@asclepio.fiap`, `rodrigo.grosa2011@gmail.com`) têm senha privada (gerada pelo `make setup` do backend) e MFA obrigatório — não aparecem na lista da tela de login.

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
  login/                 login em etapas (credenciais → código MFA) + usuários demo
  (app)/                 área autenticada (sidebar + header)
    page.tsx             dashboard
    assistente/          chat com streaming SSE, fontes e explicabilidade
    pacientes/[id]/      lista e detalhe do paciente
    fluxos/[run_id]/     execuções LangGraph + validação humana
    alertas/ conhecimento/ modelo/ auditoria/
    conta/               minha conta (perfil, MFA, sessões) · conta/senha · conta/mfa
    usuarios/            usuários & profissionais (admin)
    catalogos/           especialidades e setores (admin)
    configuracoes/       identidade, versão e status dos serviços (admin)
components/
  ui/                    Button, Card, Badge, Input, Tabs, Modal/Drawer, Table, Skeleton, Toast, EmptyState, KpiCard, badges de status, MarkdownView, JsonView
  layout/                Sidebar, Header, AppShell (guarda de rota + redirecionamentos obrigatórios), Guard (RequirePermission / 403)
  admin/                 CatalogsView, SettingsView
  providers/             AuthProvider, ConfigProvider (/public/config), ToastProvider
  account/               AccountView, ChangePasswordView, MfaSetupView, CodeInput (6 dígitos), PasswordStrength
  users/                 UsersView (tabela + modais de criar/editar/resetar)
  chat/ patients/ workflows/ alerts/ knowledge/ model/ audit/ dashboard/
lib/
  types.ts               tipos do contrato (v1 + auth v1.1)
  api.ts                 cliente fetch tipado + parser SSE (POST) + refresh automático (401) + 428
  api-types.ts           interface ApiClient (implementada por http e mock)
  session.ts             persistência da sessão (localStorage) e eventos globais
  permissions.ts         hasPermission() sobre user.permissions
  nav.ts                 buildNav(user) — menu por permissões
  password.ts            política de senha
  mock/                  fixtures pt-BR + implementação mock (inclui auth v1.1 e usuários)
```

## Perfis e navegação

O menu e as rotas são montados a partir de **`user.permissions`** (contrato v1.2), não do papel fixo — `lib/permissions.ts` (`hasPermission`) e `lib/nav.ts` (`buildNav`). Páginas protegidas usam `<RequirePermission perms="…">` (`components/layout/guard.tsx`) e mostram a tela **"Sem acesso" (403)** quando falta permissão.

| Perfil | Vê |
|---|---|
| **medico** | Dashboard clínico (+ "Meu trabalho"), Pacientes, Assistente, Fluxos clínicos (executa e aprova), Alertas, Protocolos e documentos (leitura/busca), Minha conta |
| **enfermagem** | Igual ao médico, sem aprovar/rejeitar fluxos (`workflows:decide`) |
| **auditor** | Dashboard (resumo), Auditoria, Protocolos (leitura), Alertas (leitura), Minha conta |
| **admin** | Tudo + seção **Administração**: Usuários & profissionais, Catálogos (Especialidades/Setores), IA & Modelos, Base de conhecimento (gestão + reindexar), Auditoria, Configurações |

Permissões usadas: `patients:read`, `assistant:chat`, `workflows:run`, `workflows:decide`, `alerts:read`, `alerts:ack`, `knowledge:read`, `knowledge:manage`, `model:read`, `system:internals`, `users:manage`, `catalog:read`, `catalog:manage`, `audit:read`, `settings:read` (`"*"` = todas).

- **Detalhes técnicos** (grafo Mermaid, nomes de nós, JSON dos passos, trace/modelo no chat) só aparecem com `system:internals`; para os demais, linha do tempo clínica e indicador simples ("consultando os protocolos…").
- **Identidade**: `GET /public/config` (sem auth, `ConfigProvider`) fornece `hospital_name`/`hospital_short_name`/`version`/`demo_mode`; usados no login, sidebar, header e rodapé ("{hospital_name} · Asclépio v{version}"). A lista "Acesso de demonstração" no login só aparece com `demo_mode=true`.
- **Dashboard por perfil**: KPIs clínicos sempre; `my_work` (revisões aguardando validação, alertas, conversas) para medico/enfermagem; `model`/`guardrail_blocks_today`/`system` (podem vir `null`) só para admin.
- **Cadastros**: `/usuarios` (filtros papel/ativo/busca; especialidade e setor via `GET /catalog/*`; CRM obrigatório para médico no formato `CRM 123456-UF`), `/catalogos` (abas Especialidades e Setores), `/configuracoes` (config pública + `/health`).

## Autenticação

Implementa a seção **"Autenticação real (v1.1)"** de `docs/CONTRATO_API.md` (MFA TOTP, sessões/refresh, troca de senha, gestão de usuários).

**Sessão (localStorage)** — `asclepio.token` (access JWT, 30 min), `asclepio.refresh` (refresh opaco, 12 h), `asclepio.expires_at` (epoch ms) e `asclepio.user`. O access token vai em `Authorization: Bearer`.

**Renovação** — em `401` o cliente (`lib/api.ts`) chama `POST /auth/refresh` **uma única vez** (mutex: requisições simultâneas compartilham o mesmo refresh) e repete a requisição; se o refresh falhar, limpa a sessão e redireciona para `/login`. O `AuthProvider` também renova **proativamente** quando faltam < 2 min para o access token expirar (verifica a cada 30 s e ao voltar para a aba).

**428 Precondition Required** — `must_change_password` → `/conta/senha?forced=1`; `code: "mfa_required_setup"` → `/conta/mfa`. O layout `(app)` aplica as mesmas regras a partir de `user.must_change_password` e `role=admin && !mfa_enabled` (modo restrito: sem navegação até concluir).

**Login em etapas** (`app/login`) — e-mail/senha → se a resposta for `MfaChallenge`, etapa "Código do autenticador" (6 dígitos com foco automático, ou código de recuperação `XXXX-XXXX`) → `POST /auth/mfa/verify` → `TokenOut`. Se `must_change_password`, vai para `/conta/senha?forced=1`.

**Conta** — `/conta` (perfil, status do MFA com ativar/desativar, sessões ativas com "Encerrar"/"Encerrar todas"), `/conta/senha` (política: ≥10 caracteres, maiúscula, minúscula, dígito e símbolo, com indicador visual), `/conta/mfa` (QR `qr_svg` + `secret` copiável → código → **códigos de recuperação exibidos uma única vez**, copiar/baixar .txt).

**Usuários** (`/usuarios`, só admin) — listar, criar (exibe a **senha temporária** uma única vez), editar papel/ativo/CRM/especialidade, resetar senha, resetar MFA. Ações destrutivas pedem confirmação.

**Header** — menu do avatar: Minha conta · Alterar senha · Sair (`POST /auth/logout` com o refresh token). Badge "MFA" no avatar quando ativo.

### Modo mock (`NEXT_PUBLIC_USE_MOCK=true`)

| usuário | papel | senha (mock) | observação |
|---|---|---|---|
| `admin@asclepio.fiap` | admin | `Admin#Asclepio2026` | MFA ativo — código `123456`, recuperação `AAAA-BBBB` |
| `rodrigo.grosa2011@gmail.com` | admin | `Admin#Asclepio2026` | `must_change_password=true` e sem MFA → força troca de senha e depois a ativação do MFA |
| `dra.ana`, `dr.marcos`, `enf.carla`, `auditor` `@asclepio.fiap` | medico/enfermagem/auditor | `Asclepio@2026` | `is_demo=true`, sem MFA |

O mock de `/public/config` devolve `hospital_name="Hospital Universitário"`, `hospital_short_name="HU"`, `demo_mode=true`; catálogos com 30 especialidades (CFM) e os setores dos pacientes.

Na ativação do MFA o mock aceita o código `123456`; o `qr_svg` é um SVG ilustrativo (o QR real vem do backend). O mock aplica 428 (troca de senha / MFA obrigatório) a todas as rotas exceto `/auth/*`, como o backend.
