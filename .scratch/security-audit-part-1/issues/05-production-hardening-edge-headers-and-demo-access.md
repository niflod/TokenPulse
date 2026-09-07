# 05: Supressão de Docs em Produção, Headers no Edge, Client Seguro e Acesso Demo

**What to build:**
Concluir o hardening de produção, a proteção de transporte no edge e a usabilidade do modo demonstração. Atualmente, endpoints interativos de documentação da API (`/docs`, `/redoc`, `/openapi.json`) permanecem acessíveis publicamente em produção, revelando toda a topologia de rotas internas. No edge (`netlify.toml`), faltam os cabeçalhos de segurança `Content-Security-Policy` (CSP) e `Strict-Transport-Security` (HSTS). No cliente HTTP (`frontend/js/api.js`), a leitura arbitrária de `tp_api_url` em `localStorage` permite desviar o token JWT para servidores externos. E o endpoint `/api/metrics/demo` exige autenticação JWT, quebrando a experiência de tour anônimo sem cadastro promovida na Landing Page.

Este ticket deve entregar:
1. **Supressão de Documentação Swagger/OpenAPI em Produção:**
   - Na inicialização da aplicação FastAPI (`backend/main.py`), verificar se `settings.environment == "production"`.
   - Em produção, definir `docs_url=None`, `redoc_url=None` e `openapi_url=None`, removendo a exposição pública dos esquemas e endpoints interativos.
2. **Remoção de Bypass Anônimo no Middleware JWT:**
   - Remover o tratamento de `X-Admin-Key` do middleware genérico para rotas sem identidade definida, garantindo que endpoints protegidos exijam explicitamente contexto de usuário.
3. **Injeção de Cabeçalhos de Segurança no Netlify (`netlify.toml`):**
   - Adicionar regras `Content-Security-Policy` e `Strict-Transport-Security` na seção `[[headers]]` de `/*`.
   - HSTS com `max-age=31536000; includeSubDomains`.
   - CSP configurado com fontes permitidas para scripts (`'self'`, `cdn.jsdelivr.net`, `unpkg.com`), estilos (`'self'`, `'unsafe-inline'`, Google Fonts) e conexões (`connect-src 'self'` e a URL da API backend).
4. **Validação de Origem Segura para `tp_api_url` no Frontend:**
   - Em `frontend/js/api.js`, validar o valor recuperado de `localStorage.getItem('tp_api_url')`.
   - Permitir apenas URLs com a mesma origem do navegador (`window.location.origin`) ou endereços locais confiáveis (`127.0.0.1`, `localhost`). Se apontar para um domínio externo não reconhecido, ignorar e utilizar o caminho padrão relativo, prevenindo roubo de token.
5. **Liberação Pública do Endpoint de Demonstração:**
   - Incluir `/api/metrics/demo` na tupla `_PUBLIC_PREFIXES` em `backend/main.py`, permitindo que visitantes anônimos cliquem em "Ver Demonstração" e recebam dados simulados sem receber erro HTTP 401.
6. **Cobertura de Testes Automatizados:**
   - Adicionar testes verificando que `/docs` e `/openapi.json` retornam 404 quando o ambiente é configurado como `production`.
   - Adicionar teste verificando que `/api/metrics/demo` responde com status 200 para requisições sem cabeçalho `Authorization`.
   - Validar sintaxe e integridade do arquivo `netlify.toml`.

**Blocked by:** None (can start immediately)

**Status:** completed

- [x] Endpoints `/docs`, `/redoc` e `/openapi.json` são desativados quando `ENVIRONMENT=production`.
- [x] O middleware de autenticação não permite bypass desprovido de contexto de usuário.
- [x] `netlify.toml` inclui cabeçalhos `Content-Security-Policy` e `Strict-Transport-Security`.
- [x] `frontend/js/api.js` valida e restringe `tp_api_url` para evitar exfiltração de tokens JWT.
- [x] Endpoint `/api/metrics/demo` é acessível sem credenciais e responde com 200.
- [x] Testes automatizados cobrindo o acesso público à demo e supressão de docs aprovados.
