# 03: Roteamento Web no Netlify e FastAPI

**What to build:**
Atualizar as configurações de roteamento no `netlify.toml` e no `backend/main.py` para suportar as URLs limpas do site e do aplicativo:
1. Netlify:
   - `/dashboard` e `/app` -> `dashboard.html`
   - `/login` -> `login.html`
   - `/signup` -> `signup.html`
   - `/` -> `index.html` (Landing Page)
   - `/api/*` -> proxy reverso para backend na nuvem
2. FastAPI (`backend/main.py`):
   - Rota `/dashboard` e `/app` servindo diretamente `frontend/dashboard.html`
   - Manter fallback de arquivos estáticos apontando para `frontend`

**Blocked by:** 01, 02

**Status:** completed

- [x] Atualizar `netlify.toml` com as regras de reescrita limpas para o dashboard.
- [x] Adicionar rotas GET `/dashboard` e `/app` no FastAPI retornando `FileResponse`.
- [x] Testar resolução de rotas HTTP localmente.
