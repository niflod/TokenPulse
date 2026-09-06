# Especificação: TokenPulse Web SaaS & Sincronização Direta de Consumo

## Problem Statement

Atualmente, o TokenPulse opera como uma aplicação local voltada para desenvolvedores, exigindo execução via terminal (Python/Uvicorn) ou contêineres Docker, e dependendo de configuração manual de proxy/gateway em IDEs ou terminais de clientes. Usuários que utilizam provedores de IA (OpenAI, Anthropic, Gemini, Groq, OpenRouter) não dispõem de uma forma simples, acessível via navegador e sem atrito técnico, para acompanhar seus gastos, consumo de tokens, quebra por modelos e previsões de custo de forma centralizada e sem intervenção em seus ambientes de desenvolvimento.

## Solution

Transformar o TokenPulse em uma plataforma Web SaaS hospedada na nuvem:
1. **Frontend no Netlify:** Interface web moderna e estática acessível publicamente via navegador, com proxy reverso transparente para a API em nuvem, eliminando complexidades de CORS e exigência de terminal.
2. **Multi-tenancy Público:** Cadastro aberto e autenticação segura com isolamento estrito de dados por usuário.
3. **Sincronização Direta de Consumo (Zero IDE/Terminal):** O usuário insere suas chaves de API/Admin diretamente no navegador; o sistema valida a conexão instantaneamente e sincroniza o histórico e faturamento periódico das APIs oficiais dos provedores, disponibilizando também um botão "Sincronizar Agora" para atualização sob demanda.
4. **Armazenamento Seguro e Nuvem Gerenciada:** Criptografia simétrica de chaves por usuário no banco de dados e compatibilidade agnóstica entre SQLite e PostgreSQL para implantação em provedores gerenciados (Render, Railway, Fly.io).

## User Stories

1. As a general AI user, I want to open TokenPulse directly in my browser, so that I don't need to install Docker, Python, or open a terminal.
2. As a new user, I want to register for a personal account with my email and password, so that my AI usage metrics remain private and isolated.
3. As an existing user, I want to log in securely with JWT session management, so that I can access my dashboard from any device.
4. As a user, I want to add my OpenAI organization admin key in a simple web form, so that TokenPulse can fetch my historical and current token consumption.
5. As a user, I want to see immediate visual validation when I connect a provider key, so that I know right away whether my key is valid.
6. As a user, I want to connect multiple providers (OpenAI, Anthropic, Gemini, Groq, OpenRouter) in one place, so that I have a single pane of glass for all my AI spending.
7. As a user, I want TokenPulse to periodically poll the official usage APIs in the background, so that my dashboard stays up-to-date even when I am offline.
8. As a user, I want a "Sync Now" button on my dashboard, so that I can refresh my consumption numbers immediately after running heavy workloads.
9. As a user, I want to see a timestamp indicating when my data was last synchronized, so that I know how fresh the displayed metrics are.
10. As a user, I want to view my total spending and token volume broken down by day, week, and month, so that I can budget effectively.
11. As a user, I want to see my AI usage segmented by model, so that I can identify which models are driving the highest costs.
12. As a user, I want to view my daily burn rate and estimated end-of-month invoice, so that I avoid surprise overages.
13. As a user, I want to set custom usage budget limits, so that I can monitor when my consumption reaches critical thresholds.
14. As a developer or advanced user, I want access to a hosted proxy URL with my personal virtual key, so that I still have the option to capture real-time streaming telemetry if desired.
15. As a user, I want my provider API keys to be encrypted in the database, so that my credentials cannot be compromised in plain text.
16. As a user, I want to disconnect or delete a provider connection at any time, so that TokenPulse immediately stops tracking and purges the stored credential.
17. As a user, I want clear, friendly error messages if a provider key has insufficient permissions, so that I can fix the key scope in the provider console without confusion.
18. As a user, I want the dashboard to gracefully display partial data if one provider's API is temporarily unreachable, so that the rest of my dashboard remains functional.
19. As a user, I want to export my consolidated consumption metrics to CSV or JSON directly from the browser, so that I can use them in financial reports.
20. As an operations engineer, I want the web frontend to deploy to Netlify via a declarative configuration file, so that updates can be delivered continuously via Git.

## Implementation Decisions

### Multi-Tenant Data Model and Tenant Isolation
- Extend user entities to support standard public registration with bcrypt-hashed passwords.
- Associate all provider configurations, usage sync logs, custom rules, and alert settings with a tenant owner identifier.
- Enforce tenant isolation across all query layers; every data access operation must strictly filter by the authenticated user context.

### Provider Usage Sync Engine
- Introduce an asynchronous background synchronization service capable of fetching consumption data from provider management APIs:
  - OpenAI Organization Usage API (token and cost breakdowns by model and date).
  - OpenRouter Generation/Auth Key API (credit usage and token consumption).
  - Anthropic, Gemini, and Groq usage/quota metrics.
- Normalize heterogeneous provider consumption records into uniform daily/hourly usage structures to populate analytical dashboard views.
- Provide idempotent ingestion: running a sync multiple times for the same time window must update existing records rather than duplicating totals.
- Track synchronization lifecycle states per provider connection (idle, in-progress, failed, succeeded, and last synchronized timestamp).

### Key Encryption and Credential Security
- Maintain symmetric AES-GCM / Fernet encryption for provider keys stored at rest, utilizing server secret material combined with user-specific salt.
- Never expose decrypted provider keys in API responses or frontend client states; return masked representations exclusively.

### Netlify Deployment and Reverse Proxy Routing
- Configure declarative static site hosting for the frontend on Netlify.
- Define reverse proxy redirect rules in the hosting configuration to transparently forward all API traffic (`/api/*`) to the managed cloud backend service, eliminating browser cross-origin resource sharing (CORS) restrictions.

### Cloud Database Portability
- Maintain database engine neutrality: allow seamless operation on SQLite for local verification and managed PostgreSQL (e.g., Render, Railway, Neon) in cloud environments via environment-driven connection URIs.

## Testing Decisions

### Behavior-Driven Testing at the Highest Seam
- Tests will drive the system exclusively through external interfaces: HTTP requests against FastAPI endpoints and simulated external provider APIs via HTTP client transport mocks.
- No tests should assert against private implementation details, helper functions, or internal caching dictionaries.

### Target Test Suites
- **Tenant Isolation:** Assert that User A cannot read, modify, or trigger sync for User B's provider credentials or usage records.
- **Usage Synchronization:** Using HTTP mock transports, simulate official provider usage API payloads (OpenAI and OpenRouter) and verify that the sync service correctly normalizes and aggregates tokens, costs, and model metrics.
- **Idempotency:** Assert that executing back-to-back synchronization calls for the same billing window results in identical aggregate metrics without metric drift or duplication.
- **Credential Masking & Security:** Verify that creating and retrieving provider connections never returns plain-text keys and that invalid keys fail validation with appropriate domain errors.

## Out of Scope

- Self-hosted billing gateway charging end-users for TokenPulse subscriptions (Stripe integration is deferred to a future milestone).
- Direct screen-scraping of provider consumer web interfaces (e.g., ChatGPT Plus web UI or Claude.ai web sessions).
- Mobile native application development (the web application is fully responsive on mobile browsers).

## Further Notes

- Existing proxy routing, virtual key generation, and fallback capabilities are preserved as an opt-in advanced feature for users who want direct gateway routing in addition to automated billing synchronization.
- Status triage label: `ready-for-agent`.
