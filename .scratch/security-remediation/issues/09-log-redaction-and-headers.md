# 09: Log Redaction Completo e Security Headers

**What to build:** `redact_sensitive_text` expandido para cobrir `cookie`, `set-cookie`, `proxy-authorization` e query params sensíveis. Headers `Permissions-Policy` e `Strict-Transport-Security` (condicional a HTTPS) adicionados. Teste automatizado injeta secret fake e verifica que não aparece nos logs.

**Blocked by:** None (pode começar imediatamente)

**Status:** completed

- [x] `redact_sensitive_text` sanitiza `cookie`, `set-cookie`, `proxy-authorization` e query strings sensíveis
- [x] Header `Permissions-Policy` adicionado a todas as respostas
- [x] Header `Strict-Transport-Security` adicionado condicionalmente quando a requisição for HTTPS
- [x] Teste automatizado validando que erros e logs com secrets falsos são devidamente mascarados como `[REDACTED]`
