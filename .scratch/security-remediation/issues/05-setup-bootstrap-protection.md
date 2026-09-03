# 05: Proteção do Bootstrap (`/api/auth/setup`)

**What to build:** `/api/auth/setup` aceita chamadas apenas de `127.0.0.1`/`::1` ou mediante `ADMIN_BOOTSTRAP_TOKEN` no header. Instalação remota sem token recebe HTTP 403.

**Blocked by:** None (pode começar imediatamente)

**Status:** completed

- [x] Setup restrito a localhost por padrão
- [x] `ADMIN_BOOTSTRAP_TOKEN` permite setup remoto quando presente no header
- [x] Request de IP externo sem token recebe HTTP 403
- [x] Request local ou com token correto cria admin normalmente
- [x] Teste automatizado validando a restrição
