# 02: Segregação do Dashboard e Modo Demonstração Desacoplado

**What to build:**
Mover o painel de métricas e gráficos para `frontend/dashboard.html`. Atualizar os controladores e páginas de autenticação:
1. `frontend/js/app.js`: Suportar parâmetro `?demo=true` na URL para permitir visualização imediata do dashboard com dados simulados sem login prévio.
2. `frontend/login.html` e `frontend/signup.html`: Redirecionar para `dashboard.html` após autenticação bem-sucedida e incluir botão para voltar à Landing Page (`index.html`).
3. Ajustar logout para limpar credenciais e redirecionar para a Landing Page ou tela de login.

**Blocked by:** 01 (deve preservar o layout original do dashboard)

**Status:** completed

- [x] Renomear/migrar dashboard para `frontend/dashboard.html`.
- [x] Atualizar `frontend/js/app.js` para checar `new URLSearchParams(window.location.search).get('demo') === 'true'`.
- [x] Atualizar redirecionamento pós-login em `login.js` e `signup.js` para `dashboard.html`.
- [x] Adicionar link "Voltar ao Início" nas páginas de login e signup.
