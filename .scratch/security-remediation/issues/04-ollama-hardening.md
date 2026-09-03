# 04: Hardening do Ollama (Restringir a Localhost)

**What to build:** Ollama restrito a `127.0.0.1`/`::1`/`localhost` por padrão. Flag `OLLAMA_ALLOW_LAN=true` habilita IPs de rede privada. Ollama continua aceitando HTTP. Validação SSRF aplicada ao endereço resolvido mesmo para Ollama.

**Blocked by:** 03: SSRF com Resolução DNS e Bloqueio de Domínio Custom

**Status:** completed

- [x] Ollama restrito a localhost/loopback por padrão
- [x] `OLLAMA_ALLOW_LAN=true` permite IPs da rede privada
- [x] Validação SSRF com resolução DNS aplicada ao Ollama
- [x] `http://192.168.x.x:11434` bloqueado sem flag; permitido com flag
- [x] `http://127.0.0.1:11434` continua funcionando sempre
