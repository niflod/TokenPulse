# Especificação: Auditoria de Segurança Pré-Lançamento (Parte 1 - Hardening & Isolamento)

## Problem Statement

O TokenPulse é uma plataforma Web SaaS multi-tenant que processa credenciais sensíveis de provedores de IA e roteia chamadas de inferência de múltiplos clientes. Embora o repositório já conte com criptografia simétrica Fernet para chaves em repouso, hashing bcrypt para senhas e proteção contra SSRF, a auditoria de segurança pré-lançamento identificou vulnerabilidades críticas e lacunas de blindagem na camada de aplicação e roteamento:

1. **Vazamento entre tenants no cache do gateway:** O cache de respostas do gateway gera chaves baseadas exclusivamente no provedor, modelo e corpo da requisição, sem segregação por tenant. Como resultado, dois clientes que enviam o mesmo prompt para o mesmo modelo recebem a mesma chave de cache, fazendo com que um tenant receba a resposta confidencial gerada para outro.
2. **Vazamento de telemetria em tempo real via SSE:** O endpoint de streaming Server-Sent Events (SSE) subscreve todos os usuários conectados a um barramento global de eventos e emite um resumo periódico de métricas sem filtrar pelo identificador do usuário (`user_id`). Consequentemente, qualquer usuário autenticado visualiza métricas de tráfego, custos e chamadas de todos os demais clientes da plataforma.
3. **Cross-Site Scripting (XSS) armazenado no cabeçalho público:** A landing page na raiz interpola o nome de usuário armazenado no navegador diretamente em `innerHTML` sem higienização ou uso de nós textuais seguros, permitindo a execução de scripts maliciosos injetados no cadastro.
4. **Ausência de limitação de taxa em endpoints de autenticação e enumeração de contas:** Endpoints de login, registro, emissão de tickets e setup não possuem limitação de requisições por IP, permitindo ataques de força bruta e sobrecarga. Além disso, mensagens de erro na criação de conta expõem se um nome de usuário ou e-mail já existe, permitindo enumeração de clientes.
5. **Exposição de documentação interativa e brechas no middleware de autenticação:** Rotas de documentação OpenAPI/Swagger permanecem públicas em produção, expondo a superfície de ataque interna. Adicionalmente, mecanismos legados de cabeçalho administrativo ignoram a atribuição de identidade de usuário no estado da requisição.
6. **Lacunas de cabeçalhos de segurança web e desvio de chamadas de API:** O arquivo de configuração de proxy estático não injeta Content-Security-Policy (CSP) nem HSTS para páginas estáticas no Netlify, o cliente HTTP do frontend permite redirecionamento arbitrário de tokens de autenticação via chave de URL não validada, e o endpoint de demonstração pública falha com erro 401 para visitantes anônimos.

## Solution

Implementar um plano cirúrgico de blindagem de segurança para resolver todos os pontos críticos e de hardening da Parte 1 da auditoria:

1. **Particionamento Multi-Tenant do Cache do Gateway:** Vincular chaves virtuais do cliente (`ClientApiKey`) ao identificador único do usuário criador. Reformular a geração da chave de cache do gateway para incorporar obrigatoriamente a identidade do tenant autenticado (usuário ou chave virtual), assegurando que o cache seja estritamente isolado entre contas.
2. **Isolamento de Telemetria e Eventos em Tempo Real:** Vincular a emissão de tickets SSE à sessão do usuário autenticado. Filtrar o resumo periódico de métricas emitido a cada 5 segundos pelo `user_id` do titular da conexão e segregar os eventos do barramento em tempo real para entregar apenas notificações pertencentes ao tenant conectado.
3. **Higienização Segura do DOM na Navbar Pública:** Substituir a injeção via `innerHTML` por manipulação nativa de nós do DOM com `textContent` e APIs seguras de criação de elementos, eliminando vetores de XSS baseados em DOM ou armazenamento local.
4. **Proteção de Força Bruta e Mitigação de Enumeração de Contas:** Aplicar limitador de taxa deslizante em memória (reaproveitando o algoritmo nativo da aplicação) em todos os endpoints públicos de autenticação (`/login`, `/register`, `/setup`, `/ticket`). Unificar as respostas de conflito (409) no registro para uma mensagem genérica que impeça a descoberta direcionada de e-mails ou usuários cadastrados.
5. **Blindagem do Ambiente de Produção e Middleware:** Desativar automaticamente endpoints interativos de documentação Swagger/Redoc e OpenAPI quando em ambiente de produção (`ENVIRONMENT=production`). Restringir acessos administrativos para exigir credenciais rotacionáveis explícitas e garantir que toda requisição autorizada possua contexto de identidade.
6. **Reforço de Políticas Web e Acesso à Demonstração Pública:** Inserir diretivas rigorosas de `Content-Security-Policy` e `Strict-Transport-Security` na configuração do Netlify, validar a URL base do cliente web contra origens permitidas para evitar exfiltração de tokens JWT, e liberar a rota de métricas de demonstração (`/api/metrics/demo`) para acesso anônimo sem credenciais.

## User Stories

1. As a tenant utilizing the AI gateway, I want my cached prompts and model completions to be accessible only by my own account, so that competing tenants never view my private AI queries and responses.
2. As a tenant sending repeated identical prompts through the gateway, I want to experience cache hits and low latency, so that my personal billing and response times are optimized without sacrificing data privacy.
3. As an authenticated user viewing the live dashboard, I want my Server-Sent Events stream to deliver metrics and events exclusively related to my account, so that other tenants' usage, model selections, and spend figures remain hidden from me.
4. As an authenticated user requesting a real-time SSE stream ticket, I want the ticket to be bound to my authenticated user identity, so that unauthenticated actors cannot intercept my telemetry feed.
5. As a visitor browsing the public landing page, I want my stored display username to be rendered safely via secure text nodes, so that malicious markup stored in my browser session cannot execute arbitrary scripts.
6. As a security engineer evaluating user registration, I want username inputs to be validated against dangerous script characters, so that persistent script injections are neutralized at the API boundary.
7. As a platform administrator, I want login, registration, administrative setup, and ticket issuance endpoints to enforce strict rate limits per IP, so that brute-force credential stuffing and denial-of-service spam are mitigated.
8. As a user attempting to register an existing username or email, I want to receive a generic conflict notification, so that malicious reconnaissance actors cannot determine whether a specific email address is enrolled on the platform.
9. As a platform administrator deploying to production, I want interactive API documentation endpoints (Swagger UI, ReDoc, and raw OpenAPI schemas) to be disabled by default, so that internal service topology and endpoints are not publicly exposed to unauthorized crawlers.
10. As an API client providing credentials, I want every authenticated route to establish a concrete user identity in the request lifecycle, so that no backend service operates under an ambiguous or unassigned tenant identity.
11. As a website visitor, I want static pages served from the CDN to carry strict Content-Security-Policy (CSP) and HTTP Strict Transport Security (HSTS) headers, so that clickjacking, inline script execution, and protocol downgrade attacks are prevented.
12. As a dashboard user, I want the frontend HTTP client to reject arbitrary third-party API base URLs from local preferences, so that my session JWT cannot be exfiltrated to an external server.
13. As a prospect visiting the landing page, I want the "Live Demo" experience to load synthetic telemetry immediately without requiring login or throwing authentication errors, so that I can evaluate the interface frictionless.
14. As a developer auditing the codebase, I want all sensitive secret values and production environment flags to be validated upon service startup, so that misconfigured production environments fail fast before accepting traffic.
15. As a compliance officer, I want verification tests to validate tenant boundary enforcement across caching, event streaming, and API authentication, so that isolation compliance is provable and auditable.

## Implementation Decisions

### 1. Multi-Tenant Partitioning of Gateway Cache
- Associate every virtual client API key with an explicit tenant identity upon creation.
- Modify the gateway cache key generation function to require a tenant partition identifier (such as the tenant's user ID or client key hash) as a mandatory component of the semantic hashing payload.
- When an API key is evaluated during gateway inference, propagate the resolved tenant identifier into the cache lookup and cache persistence routines.
- Maintain an emergency feature toggle in settings allowing administrators to immediately disable gateway caching across the board if required.

### 2. Scoped Real-Time Telemetry and Event Stream
- Require authentication on the stream ticket issuance endpoint, persisting both the expiration timestamp and the authenticated tenant identity in the ticket store.
- Upon establishing the SSE connection, validate and consume the ticket, extracting the associated tenant identity and binding it to the request lifecycle.
- Update the periodic metric aggregation routine within the stream loop to provide tenant-scoped metrics summaries matching the user ID attached to the active connection.
- Filter event bus notifications delivered through the SSE generator to discard events that do not match the connected tenant's identity.

### 3. DOM-Safe Navbar Greeting and Input Sanitization
- Refactor the dynamic greeting logic on the public landing page to use DOM text properties (`textContent`) and safe element creation routines instead of HTML template string interpolation into `innerHTML`.
- Add character validation on registration and profile inputs to disallow control characters and dangerous markup patterns before database persistence.

### 4. Authentication Rate Limiting and Enumeration Defense
- Instantiate dedicated sliding-window rate limiters for authentication and ticket issuance routes, restricting requests per client IP within a sixty-second sliding window.
- Respond with HTTP 429 Too Many Requests containing appropriate retry interval headers when rate limits are exceeded.
- Unify registration error responses for duplicated username or duplicated email under a single, generic conflict description that confirms the unavailability of the requested credentials without differentiating between the fields.

### 5. Production Environment Hardening and Route Gating
- Configure the application constructor to inspect the runtime environment setting and explicitly disable OpenAPI JSON, Swagger UI, and ReDoc routes when operating under production mode.
- Audit the global authentication middleware to eliminate anonymous bypass modes and ensure that every successfully routed request establishes an unambiguous tenant context.

### 6. Edge Security Headers, Safe API Client, and Public Demo Access
- Add Content-Security-Policy and Strict-Transport-Security headers to the static hosting edge configuration.
- Restrict custom API base URL configuration in the frontend client to identical origins or verified local addresses, blocking arbitrary external destination targets.
- Include the demonstration metrics endpoint within the public route allowlist in the backend authentication middleware, allowing unauthenticated read-only access to mock data.

## Testing Decisions

### Test Seam: HTTP Application Boundary
All backend security controls will be tested at the highest integration seam: the HTTP application interface via the asynchronous test client. Testing at this seam validates the actual behavior observed by clients (headers, status codes, payload structures, and isolation boundaries) without coupling tests to internal function implementations.

### Good Test Principles
- Tests must assert observable HTTP contract behavior: status codes, response headers (such as `X-TokenPulse-Cache`, `Retry-After`, `WWW-Authenticate`), and response payload data isolation.
- Multi-tenant tests must execute realistic scenarios involving two distinct tenants (Tenant A and Tenant B) and verify that actions taken by Tenant A never leak state or telemetry to Tenant B.
- Tests must avoid mocking internal application services whenever feasible, relying on the test database and ephemeral test state to reflect real operational execution.

### Target Test Suites
1. **Gateway Cache Isolation:** Create test cases where Tenant A executes a model query that is cached; then Tenant B executes the identical query. Assert that Tenant B receives a cache miss and generates an independent cache entry partitioned to Tenant B.
2. **Real-time SSE Stream Scoping:** Connect two simulated clients to the SSE endpoint with separate tickets. Emit a telemetry event for Tenant A and verify that Tenant B's stream receives zero events. Verify that the periodic metrics tick returns only Tenant B's aggregated spend.
3. **Auth Rate Limiting & Account Enumeration:** Execute rapid successive login and registration attempts from a single IP and assert HTTP 429 after the threshold is breached. Test registration with an existing username and an existing email to ensure both return the identical generic error message.
4. **Environment Hardening & Production Routes:** Test API startup under production configuration and verify that `/docs`, `/redoc`, and `/openapi.json` return HTTP 404. Test access to the demo endpoint without a Bearer token and assert HTTP 200 with valid mock metrics.
5. **Static Security Headers & Client Safety:** Verify that edge redirect rules and headers contain CSP and HSTS directives.

## Out of Scope

- Migration of frontend authentication storage from `localStorage` to `HttpOnly` cookies (deferred to post-launch roadmap).
- Distributed rate limiting via Redis or external key-value stores (single-instance in-memory limiter is sufficient for initial launch).
- Deployment and host container verification on Render/Docker infrastructure (evaluated in operational runbooks).
- Security audit Part 2 items (which will be handled in a dedicated subsequent specification).

## Further Notes

- All changes must maintain backward compatibility with existing provider integration and metrics calculation pipelines.
- Existing unit and integration tests (72 tests) must continue passing without regression.
