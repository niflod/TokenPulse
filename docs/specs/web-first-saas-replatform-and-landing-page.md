# Especificação: Reformulação Web-First SaaS e Landing Page Pública

## Problem Statement

Atualmente, o repositório e a apresentação do TokenPulse ainda são conduzidos sob uma ótica voltada a terminal, contêineres e configuração manual em IDEs. Quem visita o repositório ou acessa o produto pela primeira vez é recebido por diagramas ASCII imitando interfaces de terminal, instruções para configurar proxies em clientes Python/curl e scripts de inicialização de console. Não existe uma página inicial pública (Landing Page) que comunique visualmente o valor da plataforma, os recursos de observabilidade, as garantias de segurança e o fluxo simples de uso (criar conta, conectar chaves e acompanhar faturamento). Isso cria atrito de adoção para usuários que desejam apenas uma ferramenta web acessível diretamente no navegador, sem intervenção em seus ambientes de desenvolvimento ou dependência de terminal.

## Solution

Reformular a arquitetura de apresentação, a documentação e as ferramentas de desenvolvimento do repositório para posicionar o TokenPulse fundamentalmente como uma plataforma Web SaaS moderna e intuitiva:

1. **Portal Público e Landing Page:** Transformar o ponto de entrada raiz em uma página institucional moderna, com proposta de valor clara (*"Observe your AI"*), vitrine de recursos de observabilidade de custos e telemetria, garantias de segurança e isolamento, lista de provedores suportados e chamadas claras para ação (Cadastro, Login e Demonstração ao Vivo).
2. **Segregação de Rotas do Web App:** Mover o painel operacional de telemetria para uma rota dedicada e protegida (`/dashboard` e `/app`), mantendo os fluxos de autenticação desacoplados da vitrine pública.
3. **Acesso Direto à Demonstração:** Permitir que visitantes do site explorem o painel de telemetria em modo demonstração com um único clique a partir da Landing Page, sem necessidade de cadastro prévio.
4. **Ecossistema Web de Desenvolvimento:** Fornecer scripts padronizados do ecossistema web para desenvolvimento, inicialização e testes locais, além de mensagens de console amigáveis que direcionam o desenvolvedor para URLs no navegador.
5. **Documentação e README Web-First:** Reestruturar totalmente o README principal e os guias de uso para priorizar a experiência de uso no navegador (SaaS), implantação em nuvem (Netlify + backend gerenciado) e instruir a execução em terminal/Docker apenas como opção técnica secundária de auto-hospedagem.

## User Stories

1. As a visitor browsing the repository or site, I want to see a clear and modern landing page on the root address, so that I understand immediately what TokenPulse does without reading terminal command logs.
2. As a visitor on the landing page, I want to see an overview of key platform capabilities (spend tracking, live latency telemetry, automated burn rate projection, and provider sync), so that I can evaluate whether the tool meets my needs.
3. As a privacy-conscious user, I want to read clear explanations of the security architecture on the landing page (symmetric Fernet encryption, tenant isolation, and zero plain-text key storage), so that I trust the platform with my provider credentials.
4. As a prospect exploring the tool, I want a "View Live Demo" button on the landing page, so that I can interact with the dashboard populated with mock telemetry without creating an account first.
5. As a prospect clicking the live demo button, I want to be taken straight to the dashboard with demo mode enabled and an informative banner, so that I understand the data is simulated.
6. As a prospect in demo mode, I want a visible option to exit demo mode or register a real account, so that I can transition smoothly to personal usage.
7. As a visitor on the landing page, I want clear "Log In" and "Sign Up Free" call-to-action buttons in both the navigation bar and hero section, so that I can quickly start using the service.
8. As a user on the authentication pages (login or signup), I want a visible link to return to the landing page, so that I can navigate back if I need more information before signing in.
9. As a user completing registration or login, I want to be redirected automatically to the authenticated dashboard route, so that I can access my metrics immediately.
10. As an unauthenticated user attempting to directly access the dashboard route, I want to be safely redirected to the login page, so that my account security and data boundaries are respected.
11. As a logged-in user returning to the root landing page, I want the navigation header to show a direct "Go to Dashboard" button, so that I can resume my session effortlessly.
12. As a web user on the dashboard, I want to configure provider credentials entirely via graphical modal dialogs, so that I never have to touch an IDE config file or run terminal commands.
13. As a web user on the dashboard, I want to trigger manual synchronization and view real-time status indicators in the interface, so that I know my metrics are up to date.
14. As a mobile or tablet web user, I want the landing page and authentication views to be completely responsive, so that I can browse and register from any device.
15. As a cloud site administrator, I want Netlify routing configuration to properly handle clean paths for the landing page, dashboard, login, and registration pages, so that URLs remain clean and bookmarkable.
16. As a cloud site administrator, I want static assets to be served with strict security headers (no-sniff, clickjacking protection, referrer policies) across all public pages, so that users are protected from web vulnerabilities.
17. As a web developer cloning the project, I want a standard package descriptor with dev and start commands, so that I can inspect and run the project using familiar web workflows.
18. As a web developer running the local server, I want the startup output to present clickable web URLs for the site and dashboard, so that I can launch the application immediately in my browser.
19. As a developer reading the repository README, I want to see a visual product showcase and a 2-step browser usage guide at the very top, so that I understand this is a web product rather than a CLI tool.
20. As a DevOps engineer reading the README, I want step-by-step guides for one-click deployment of the frontend to Netlify and the backend to managed containers (Render/Railway), so that I can publish the site to production quickly.
21. As an open-source contributor, I want terminal execution, Docker containerization, and local Python setup explained in a dedicated developer section at the bottom of the documentation, so that technical setup does not obscure the product description.
22. As an advanced API developer, I want documentation about the optional transparent gateway proxy and client API keys preserved in a secondary section, so that I can still utilize direct proxying if needed without cluttering the primary web flow.

## Implementation Decisions

### Architectural Separation of Public Site and Authenticated Application
- Establish the root path as the public-facing promotional and onboarding site (Landing Page), serving unauthenticated visitors with semantic HTML5 markup, responsive CSS styling matching the platform design tokens, and Lucide icons.
- Designate the private analytics application to a dedicated dashboard path (`/dashboard` and `/app`), requiring valid session credentials to display personal tenant data, while granting graceful read-only demo access when explicitly initiated from the public showcase.
- Ensure authentication views provide two-way navigation: visitors can enter from the landing page and navigate back to the landing page, with successful authentication flows leading directly to the dashboard path.

### Web Server Entry Point and Hosting Rules
- Maintain single-origin local hosting via the backend static file mount: the server serves the landing page at root, exposes rewrite endpoints for the dashboard route, and mounts all frontend stylesheet and script assets.
- Configure cloud static hosting redirects to rewrite public vanity paths (`/dashboard`, `/app`, `/login`, `/signup`) to their respective HTML artifacts, while maintaining the transparent reverse proxy rule for backend API calls (`/api/*`).
- Inject dynamic navigation states on the landing page: if an active local session token exists, the header dynamically presents a quick link to the active dashboard.

### Developer Tooling and Web Workflow Alignment
- Provide a standard web package definition at the repository root outlining project metadata, dependencies, and scripts (`dev`, `start`, `test`, `build`) that bridge web development habits with backend service execution.
- Update development launcher scripts to emit clean, formatted web URLs pointing developers to the browser rather than describing terminal commands.

### Repository Presentation and Documentation Overhaul
- Rewrite the repository README from the ground up:
  - Replace ASCII terminal illustrations with visual SaaS highlights and badges.
  - Present TokenPulse as a full-featured web observability platform.
  - Detail the web onboarding journey: Account Creation -> Provider Key Sync -> Real-time Telemetry.
  - Detail production deployment onto Netlify (frontend) and managed cloud services (backend).
  - Condense local setup and Docker execution into a clear "Self-Hosting & Local Development" section at the end of the guide.
  - Relegate gateway proxy forwarding, TTFT measurement, and client API keys into an "Advanced Features" subsection.

## Testing Decisions

### Behavior-Driven Testing at the Highest Seam
- Tests will drive the system exclusively through external web interfaces: HTTP responses against public and authenticated routes, assertion of redirection headers, and validation of static asset delivery.
- No tests should assert against private implementation details, internal styling class permutations, or helper closures.

### Target Test Suites
- **Route Resolution & Static Serving:** Assert that requesting the root path (`/`) returns the landing page HTML with HTTP 200, requesting `/dashboard` serves the dashboard application, and static assets (CSS, JS) load with appropriate content types.
- **Authentication Guard & Redirection:** Assert that navigating to the dashboard without credentials correctly prompts redirection to the login interface, whereas supplying demo parameters permits immediate demonstration mode.
- **Reverse Proxy and Endpoint Health:** Verify that `/api/ping` and telemetry routes remain accessible across root path reallocations.

## Out of Scope

- Migrating the frontend codebase from vanilla HTML/CSS/JavaScript to complex JavaScript meta-frameworks (e.g., Next.js, Nuxt, Remix).
- Payment processing, billing tiers, or Stripe checkout integrations.
- Native mobile application builds (iOS/Android).

## Further Notes

- Status triage label: `ready-for-agent`.
