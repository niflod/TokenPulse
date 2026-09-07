# 04: Limitador de Taxa em Endpoints de Autenticação e Resposta Unificada Anti-Enumeração

**What to build:**
Blindar os endpoints públicos de autenticação contra ataques de força bruta, tentativas de adivinhação de senhas, criação massiva de contas e enumeração de usuários cadastrados. Atualmente, `/api/auth/login`, `/api/auth/register`, `/api/auth/setup` e `/api/realtime/ticket` não possuem qualquer limitação de taxa por IP. Além disso, a rota de cadastro retorna mensagens de erro diferenciadas para "Nome de usuário já em uso" e "E-mail já cadastrado" com status 409, permitindo que atacantes descubram e-mails registrados na plataforma.

Este ticket deve entregar:
1. **Rate Limiting em Endpoints de Autenticação:**
   - Instanciar um limitador de taxa deslizante dedicado (`auth_rate_limiter = InMemoryRateLimiter(rpm=...)`) com limites apropriados para proteção contra ataques automatizados (ex: 15 req/min para login, 10 req/min para cadastro e setup).
   - Aplicar a verificação de rate limit baseada no IP do cliente (`request.client.host` ou cabeçalhos confiáveis) nos endpoints:
     - `POST /api/auth/login`
     - `POST /api/auth/register`
     - `POST /api/auth/setup`
     - `POST /api/realtime/ticket`
   - Retornar status HTTP 429 Too Many Requests com cabeçalho `Retry-After: <segundos>` e detalhe amigável quando o limiar for atingido.
2. **Defesa Contra Enumeração de Contas no Cadastro:**
   - No endpoint `POST /api/auth/register`, unificar as mensagens de erro quando houver conflito de username ou email.
   - Retornar uma mensagem genérica de conflito HTTP 409:
     `"As informações de cadastro informadas já estão em uso. Tente outro nome de usuário ou e-mail, ou faça login."`
   - Evitar indicar especificamente se o identificador que colidiu foi o e-mail ou o nome de usuário.
3. **Respostas Constantes no Login:**
   - Assegurar que falhas de autenticação em `POST /api/auth/login` continuem retornando a mensagem genérica `"Credenciais inválidas."` com tempo de resposta consistente, sem expor se o usuário existe ou não.
4. **Cobertura de Testes de Força Bruta e Enumeração:**
   - Escrever testes automatizados que realizam múltiplas requisições sequenciais de login e cadastro a partir do mesmo IP, confirmando o bloqueio com status 429 e cabeçalho `Retry-After`.
   - Validar que o cadastro de usuário com username duplicado ou e-mail duplicado retorna a mesma mensagem genérica 409.

**Blocked by:** None (can start immediately)

**Status:** completed

- [x] Rate limiter deslizante em memória ativado em `/api/auth/login`, `/api/auth/register`, `/api/auth/setup` e `/api/realtime/ticket`.
- [x] Excesso de requisições retorna HTTP 429 com cabeçalho `Retry-After`.
- [x] O endpoint de registro retorna mensagem genérica de conflito (409) sem distinguir se username ou email colidiu.
- [x] O endpoint de login preserva mensagem genérica de credenciais inválidas (401).
- [x] Testes automatizados cobrindo rate limit e anti-enumeração aprovados sem regressões.
