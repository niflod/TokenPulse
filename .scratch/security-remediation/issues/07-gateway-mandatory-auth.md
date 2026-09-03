# 07: Gateway Exige Autenticação (Rejeitar Requests Anônimos)

**What to build:** Toda request ao Gateway sem `Authorization`/`x-api-key` header é rejeitada com HTTP 401. Requests com `tp_live_` válida usam provider key do DB. BYOK continua funcionando mas pode ser desabilitado com `GATEWAY_ALLOW_BYOK=false`. Provider key nunca é retornada, logada ou cacheada.

**Blocked by:** 02: SECRET_KEY Obrigatória em Produção

**Status:** completed

- [x] Request sem header de autenticação → HTTP 401
- [x] `tp_live_` válida → proxy funciona normalmente
- [x] `tp_live_` revogada → HTTP 401
- [x] `GATEWAY_ALLOW_BYOK=false` → key real do provider rejeitada
- [x] Provider key nunca retornada, logada ou cacheada
- [x] Testes automatizados para todos os cenários
