# 08: CSP sem `unsafe-inline` e Remoção de `innerHTML`

**What to build:** Scripts inline movidos para arquivos JS. `innerHTML` em `app.js` substituído por DOM API. CSP atualizado para `script-src 'self'` sem `unsafe-inline`. `Permissions-Policy` header adicionado.

**Blocked by:** 06: Remover JWT da Query String

**Status:** completed

- [x] `innerHTML` substituído por `textContent`/`createElement`/`replaceChildren` em `app.js`
- [x] CSP atualizado: `script-src 'self' https://cdn.jsdelivr.net https://unpkg.com` (sem `unsafe-inline`)
- [x] `Permissions-Policy` header adicionado
- [x] Dashboard renderiza corretamente sem erros no console
- [x] Nenhum script inline remanescente no HTML
