# 03: SSRF com Resolução DNS e Bloqueio de Domínio Custom

**What to build:** `validate_provider_base_url` resolve DNS do hostname e rejeita se qualquer IP resolvido cair em rede privada/reservada. Domínio fora da allowlist oficial é bloqueado (não apenas warning). Opção `ALLOW_CUSTOM_PROVIDER_URLS=true` para permitir explicitamente.

**Blocked by:** None (pode começar imediatamente)

**Status:** completed

- [x] Resolução DNS prévia adicionada — hostname que resolve para IP privado é rejeitado
- [x] Domínio fora da allowlist oficial é bloqueado com HTTP 400 (não apenas warning)
- [x] Flag `ALLOW_CUSTOM_PROVIDER_URLS` permite domínios custom quando `true`
- [x] Testes: DNS rebinding para `127.0.0.1`, rede privada, link-local, IPv6 reservado
- [x] Domínios oficiais (`api.openai.com` etc.) continuam funcionando
