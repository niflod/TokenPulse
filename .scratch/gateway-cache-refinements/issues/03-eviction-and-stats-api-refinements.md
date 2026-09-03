# 03: Evicção Automática e Ajustes da API REST de Estatísticas de Cache

**What to build:**
Adicionar rotina de evicção automática de entradas expiradas em SQLite no `cache_service.py`, incluir a métrica de `misses` no endpoint `GET /api/cache/stats`, e flexibilizar a rota `/stats` para qualquer usuário autenticado (não apenas admin), preservando `POST /api/cache/flush` como exclusivo de admin.

**Blocked by:** 01: Validação Precoce de Autenticação e Chaves Virtuais no Gateway

**Status:** completed

- [x] Métodos de consulta ou rotina periódica em `cache_service.py` removem entradas com `expires_at < now`
- [x] `GET /api/cache/stats` retorna `total_misses` e taxa de acerto consistente
- [x] `GET /api/cache/stats` é acessível com token JWT comum de usuário autenticado
- [x] `POST /api/cache/flush` e `PUT /api/cache/config` permanecem protegidos por `require_admin`
- [x] Testes automatizados validando evicção automática e métricas da API
