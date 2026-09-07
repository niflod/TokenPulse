# 02: Higiene de Indexação, Noindex em Rotas de App e Diretivas de Crawler

**What to build:**
Implementar o isolamento estrito de indexação entre a vitrine pública de aquisição (Landing Page) e as páginas privadas ou operacionais da aplicação (`/dashboard`, `/dashboard.html`, `/login.html`, `/signup.html`). Atualmente, sem diretivas de controle de robôs, os motores de busca e crawlers de IA podem indexar a casca da aplicação (`dashboard.html` ou `dashboard.html?demo=true`), fazendo com que usuários que busquem por "TokenPulse" aterrissem diretamente em uma tela com dados simulados em vez da Landing Page de conversão.

Este ticket deve entregar:
1. **Blindagem com Tag Meta Robots nas Páginas do App:**
   - Inserir no `<head>` de `frontend/dashboard.html`:
     `<meta name="robots" content="noindex, nofollow" />`
   - Inserir no `<head>` de `frontend/login.html`:
     `<meta name="robots" content="noindex, nofollow" />`
   - Inserir no `<head>` de `frontend/signup.html`:
     `<meta name="robots" content="noindex, nofollow" />`
   - Justificativa técnica: a aplicação autenticada depende de tokens JWT para carregar métricas via API; suas telas são meros contêineres e formulários que não devem disputar relevância ou poluir o índice de pesquisa com páginas de utilidade restrita.
2. **Criação do Arquivo de Diretivas de Crawlers (`frontend/robots.txt`):**
   - Estruturar diretivas declarativas para todos os agentes (`User-agent: *`):
     - `Allow: /` (garantindo livre rastreamento da Landing Page e assets estáticos).
     - `Disallow: /dashboard`
     - `Disallow: /dashboard.html`
     - `Disallow: /app`
     - `Disallow: /login`
     - `Disallow: /login.html`
     - `Disallow: /signup`
     - `Disallow: /signup.html`
     - `Disallow: /api/`
     - `Sitemap: https://tokenpulse.netlify.app/sitemap.xml`
   - Garantir que o `robots.txt` seja servido na raiz do domínio com `Content-Type: text/plain`.
3. **Criação do Mapa do Site Canônico (`frontend/sitemap.xml`):**
   - Construir arquivo XML válido conforme a especificação do consórcio `sitemaps.org/schemas/sitemap/0.9`.
   - Incluir a entrada única canônica da página inicial:
     - `<loc>https://tokenpulse.netlify.app/</loc>`
     - `<lastmod>` atualizado com data ISO 8601.
     - `<changefreq>weekly</changefreq>`
     - `<priority>1.0</priority>`
   - Omitir deliberadamente URLs de login, cadastro ou dashboard, consolidando 100% da força de indexação (PageRank e citation footprint) na Landing Page.

**Blocked by:** None (can start immediately)

**Status:** completed

- [x] `<meta name="robots" content="noindex, nofollow">` inserido no `<head>` de `dashboard.html`.
- [x] `<meta name="robots" content="noindex, nofollow">` inserido no `<head>` de `login.html` e `signup.html`.
- [x] `frontend/robots.txt` criado com permissão exclusiva para a raiz e assets, e bloqueio de rotas privadas e de autenticação.
- [x] Diretiva canônica `Sitemap:` declarada no final do `robots.txt`.
- [x] `frontend/sitemap.xml` estruturado no padrão XML padrão 0.9 apontando para a URL canônica da Landing Page.
- [x] Servidor FastAPI e Netlify validados para entregar `robots.txt` e `sitemap.xml` com código HTTP 200.
