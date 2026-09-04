# 01: Request Normal Transparente & Single Log Execution

**What to build:**
Chamadas normais não-streaming passam de forma 100% transparente pelo Gateway. O cliente recebe exatamente a mesma estrutura de JSON (choices, tool calls, status, finish_reason) gerada pelo provedor upstream. O Gateway registra estritamente um registro em `RequestLog` com correlation ID único (`tp_req_...`), calcula latência e custo via catálogo centralizado, e emite um único evento `request.completed` para o SSE sem nenhuma duplicação.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [x] Request não-streaming preserva fielmente o body e status HTTP retornado pelo provider
- [x] Correlation ID `tp_req_...` injetado no header `X-TokenPulse-Request-Id` e correlacionado no log
- [x] Provider request ID nativo armazenado separadamente em `provider_request_id`
- [x] Estritamente um registro criado em `RequestLog` (sem registros duplicados)
- [x] Teste automatizado cobrindo equivalência de resposta direta vs via Gateway
