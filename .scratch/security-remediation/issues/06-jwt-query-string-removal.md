# 06: Remover JWT da Query String (Ticket Descartável para SSE)

**What to build:** Endpoint `POST /api/realtime/ticket` gera ticket de uso único com TTL de 30s. Frontend usa ticket no `EventSource` em vez do JWT completo. Middleware aceita ticket descartável para SSE. JWT removido de `?token=` no frontend e no middleware.

**Blocked by:** None (pode começar imediatamente)

**Status:** completed

- [x] `POST /api/realtime/ticket` criado — retorna ticket de uso único
- [x] Frontend usa ticket descartável para SSE em vez de JWT
- [x] Middleware aceita ticket descartável para rotas SSE
- [x] JWT em `?token=` removido do middleware e do frontend
- [x] Ticket expirado ou reutilizado é rejeitado
- [x] Teste automatizado validando fluxo completo
