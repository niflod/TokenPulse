# Especificação: Auditoria de Segurança Pré-Lançamento (Parte 2 - Isolamento de Dados, Integridade de Scripts & Blindagem de Produção)

## Problem Statement

O TokenPulse passou com êxito pela primeira bateria de mitigação da Auditoria de Segurança Pré-Lançamento (isolamento do cache do gateway, proteção do stream SSE, eliminação de XSS na landing page, rate limiting em autenticação e supressão de docs em produção). No entanto, a segunda etapa da auditoria revelou vulnerabilidades críticas remanescentes e oportunidades adicionais de hardening:

1. **Vazamento total de telemetria nos endpoints de exportação:** As rotas `/api/export/csv` e `/api/export/json` são protegidas apenas por uma verificação genérica de token administrativo, que qualquer JWT válido de qualquer tenant satisfaz. A consulta SQL ao banco de dados não filtra pelo identificador do usuário (`user_id`), permitindo que qualquer cliente registrado baixe em massa todos os registros de requisições, modelos utilizados, custos e prompts de todos os demais clientes da plataforma.
2. **Dependências frontend em CDN sem versão e sem integridade (SRI):** O script `lucide@latest` é carregado de forma flutuante e sem hash de integridade via `unpkg.com` nas páginas do sistema (`index.html`, `dashboard.html`, `login.html`, `signup.html`, `404.html`), e o script do `chart.js` no dashboard carece do atributo `integrity`. Como os tokens JWT residem no `localStorage`, qualquer adulteração maliciosa ou ataque à cadeia de suprimentos desses CDNs viabiliza roubo instantâneo de credenciais e sessões de usuários.
3. **CORS incompleto para o domínio de produção:** A configuração padrão de CORS no backend permite apenas origens locais (`localhost`, `127.0.0.1`), deixando de fora o domínio de produção oficial no Netlify (`https://tknpulse.netlify.app` / `https://tokenpulse.netlify.app`). Em produção, chamadas diretas falham ou induzem operadores a usar coringas perigosos (`*`).
4. **Ignorância do limite de taxa individual das chaves virtuais no Gateway:** A entidade `ClientApiKey` possui o atributo `rate_limit_rpm` customizável por chave virtual, porém o gateway ignora esse valor e aplica exclusivamente o limite global fixo, impedindo que desenvolvedores imponham limites mais restritivos a chaves específicas de clientes ou testes.
5. **Truncamento silencioso do algoritmo bcrypt (72 bytes):** A função de hash de senhas aceita entradas de até 128 caracteres, mas a especificação do bcrypt trunca silenciosamente senhas maiores que 72 bytes. Isso cria falsas expectativas de entropia e discrepâncias de segurança para senhas longas.
6. **Hardening de produção e exposição do endpoint de setup pós-inicialização:** A rota `/api/auth/setup` permanece listada como pública no middleware mesmo após o sistema já ter o administrador inicial cadastrado, e a política de CSP do backend permite conexões para `localhost` independentemente de estar em desenvolvimento ou produção.

---

## Solution

Implementar uma intervenção cirúrgica e rigorosa para sanar todas as vulnerabilidades e lacunas da Parte 2 da auditoria:

1. **Isolamento Multi-Tenant Estrito em Exportações:**
   - Alterar a dependência dos endpoints `/api/export/csv` e `/api/export/json` para resolver o usuário autenticado via `get_current_user`.
   - Adicionar obrigatoriamente a cláusula `where(RequestLog.user_id == current_user.id)` em todas as consultas e streams de exportação, garantindo que nenhum tenant visualize ou exporte dados alheios.
2. **Pinagem Estrita de Versões e Subresource Integrity (SRI) no Frontend:**
   - Fixar o Lucide Icons em versão imutável específica e adicionar os atributos `integrity="sha384-..."` e `crossorigin="anonymous"` a todas as inclusões de scripts externos nos arquivos HTML.
   - Adicionar o hash de integridade SRI correspondente ao carregamento de `chart.js`.
3. **Inclusão da Origem de Produção Netlify no CORS e Configuração Robusta:**
   - Adicionar os domínios oficiais de produção do Netlify aos `cors_origins` padrão em `backend/config.py` e garantir que o carregamento da variável de ambiente `CORS_ORIGINS` continue suportando separação por vírgula.
4. **Respeito ao Limite de Taxa por Chave Virtual no Gateway:**
   - No fluxo de roteamento do gateway, quando a chamada for autenticada via chave virtual (`tp_live_...`), extrair o valor de `rate_limit_rpm` configurado no objeto da chave e aplicá-lo como `custom_rpm` no limitador de taxa deslizante do cliente.
5. **Mitigação do Truncamento bcrypt:**
   - Limitar o comprimento máximo permitido de senhas nos schemas Pydantic (`RegisterRequest`, `SetupRequest`, `ChangePasswordRequest`) estritamente ao teto de 72 caracteres, rejeitando senhas mais longas com validação HTTP 422 clara e informativa.
6. **Desativação Dinâmica do Endpoint de Setup e CSP Especializado por Ambiente:**
   - Remover `/api/auth/setup` da lista de prefixos públicos do middleware assim que o setup inicial estiver concluído (`setup_completed == True`), fechando o endpoint para varreduras públicas.
   - Ajustar a diretiva `connect-src` no CSP do backend para omitir `http://localhost:*` e `ws:` quando `ENVIRONMENT=production`.

---

## User Stories

1. As an authenticated SaaS tenant downloading my usage reports, I want the exported CSV and JSON files to contain only the logs generated by my own account, so that no competitors' data or prompts are leaked to me.
2. As a security compliance auditor, I want all external third-party CDN scripts loaded by the application to include valid cryptographic Subresource Integrity (SRI) hashes and pinned versions, so that upstream CDN compromises cannot execute arbitrary JavaScript in user browsers.
3. As a browser client communicating with the production backend from the Netlify frontend domain, I want CORS headers to authorize cross-origin requests securely without resorting to insecure wildcard origins, so that browser calls succeed cleanly.
4. As an API client using a virtual key with a custom rate limit of 30 RPM, I want the gateway to enforce my specific rate limit rather than the global default, so that my applications are throttled according to their defined tier.
5. As a user registering a new account or changing my password, I want password length validation to prevent silently truncated passwords over 72 bytes, so that my credential security matches expected cryptographic guarantees.
6. As a system administrator, I want the initial administrative setup route to be blocked from public unauthenticated access once an administrator has been configured, so that unnecessary attack surface is closed.
7. As a platform operator running in production, I want backend security headers (CSP) to restrict connections strictly to authorized production endpoints, so that local development exceptions do not linger in production environments.
8. As a QA engineer, I want automated integration tests verifying that tenant A cannot export tenant B's logs, so that data confidentiality regressions are immediately flagged in CI.

---

## Implementation Decisions

### 1. Multi-Tenant Scoping for Data Exports
- Replace the authorization dependency on `/api/export/csv` and `/api/export/json` with the standard tenant-resolving dependency (`get_current_user`).
- Update both streaming generator routines and JSON array builders to accept `user_id: int` and append `where(RequestLog.user_id == user_id)` to the SQLAlchemy select statements.
- Return empty exports (with valid header structures) when a user has no request logs, rather than allowing unbound database scans.

### 2. Pinned CDN Dependencies & Subresource Integrity (SRI)
- Pin all references to Lucide Icons in HTML files (`index.html`, `dashboard.html`, `login.html`, `signup.html`, `404.html`) from `unpkg.com/lucide@latest` to a fixed version `lucide@0.469.0` with its official SHA-384 integrity hash and `crossorigin="anonymous"`.
- Add the corresponding official SHA-384 integrity hash and `crossorigin="anonymous"` to Chart.js in `dashboard.html`.

### 3. Production CORS Allowlist
- Add `https://tknpulse.netlify.app` and `https://tokenpulse.netlify.app` to the default `cors_origins` array in `backend/config.py`.
- Ensure environment variable overrides via `CORS_ORIGINS` continue to take precedence.

### 4. Per-Key Rate Limiting in Gateway
- In `backend/routers/gateway.py`, upon validating a virtual `ClientApiKey`, pass the key's configured `rate_limit_rpm` (when set and greater than 0) to `gateway_rate_limiter.is_allowed(client_key, custom_rpm=...)`.
- If no custom rate limit is set on the key, fall back to the system default `settings.gateway_rate_limit_rpm`.

### 5. Bcrypt 72-Byte Truncation Guard
- In `backend/routers/auth.py`, adjust `max_length` in `RegisterRequest`, `SetupRequest`, and `ChangePasswordRequest` from `128` to `72`.
- Retain minimum length of 8 characters.

### 6. Dynamic Setup Endpoint Protection & Production CSP Splitting
- In `backend/main.py`, evaluate whether initial setup is completed; if completed, exclude `/api/auth/setup` from unauthenticated public bypass.
- In `backend/main.py:add_security_headers`, generate `connect-src` dynamically: omit `http://localhost:*` and `ws:` when `is_production` is true.

---

## Testing Decisions

- **Multi-Tenant Export Isolation:** Automated test creating two separate users, seeding request logs for both, and verifying that user 1 exporting CSV and JSON only receives their own records, with 0 records from user 2.
- **Per-Key Gateway Rate Limit:** Automated test creating a virtual key with a tight custom rate limit (e.g. 5 RPM), issuing 6 requests, and confirming that the 6th returns HTTP 429 while global default limits remain untouched.
- **Bcrypt 72-Byte Validation:** Automated test submitting a 73-character password to `/api/auth/register`, verifying HTTP 422 Unprocessable Entity, while a 72-character password succeeds.
- **Frontend SRI Integrity Audit:** Automated static test reading all HTML files in `frontend/` and asserting that no script tag uses `@latest` and all external script tags include `integrity` and `crossorigin="anonymous"`.
- **Production CSP & CORS Tests:** Automated test asserting that production mode emits tightened CSP headers and that the default CORS list includes Netlify production origins.

---

## Out of Scope

- Migrating SQLite to managed PostgreSQL (flagged for post-launch infrastructure evolution).
- Re-architecting token storage from `localStorage` to HttpOnly cookies (since frontend is fully static on Netlify proxying cross-origin to Render).
- Introducing third-party CAPTCHA widgets (in-memory rate limiting meets launch security criteria).

---

## Further Notes

- All changes maintain 100% backward compatibility with existing tests and preserve current UI design.
- Verification must pass all 84 existing tests plus new isolation and hardening suites with 0 regressions.
