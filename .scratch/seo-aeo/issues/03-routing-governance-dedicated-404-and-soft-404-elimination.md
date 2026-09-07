# 03: Governança de Roteamento, Página 404 e Eliminação de Soft-404

**What to build:**
Corrigir o comportamento do roteamento de fallback no Netlify e no servidor local, eliminando a ocorrência de "soft-404" (quando uma página inexistente retorna o conteúdo da Landing Page com código de status HTTP 200). Atualmente, a regra catch-all `[[redirects]] from = "/*" to = "/index.html" status = 200` faz com que qualquer caminho inválido (como `/qualquer-coisa`, `/old-page` ou erros de digitação) sirva a página inicial fingindo sucesso, o que confunde motores de busca, contamina estatísticas de rastreamento do Google Search Console e enfraquece a integridade canônica do domínio.

Este ticket deve entregar:
1. **Design e Construção da Página de Erro Dedicada (`frontend/404.html`):**
   - Construir uma página estática sem dependência de JavaScript para renderização, estilizada no mesmo tema escuro premium da plataforma:
     - Header com a marca TokenPulse clicável para retorno.
     - Destaque visual: código `404` em tipografia mono com gradiente da marca (`#4D8DFF` a `#8B7CFF`).
     - Título e mensagem clara em PT-BR: *"Página não encontrada"*, *"O link que você tentou acessar não existe ou foi movido."*.
     - Botão de ação evidente: *"Voltar para a Página Inicial"* apontando para `/`.
     - Tag `<meta name="robots" content="noindex, nofollow">` no `<head>` para garantir que páginas de erro jamais sejam indexadas.
2. **Reconfiguração das Regras de Redirecionamento no `netlify.toml`:**
   - Manter as regras explícitas prioritárias para:
     - `/api/*` -> proxy para backend
     - `/dashboard` e `/app` -> `/dashboard.html` (status 200)
     - `/login` -> `/login.html` (status 200)
     - `/signup` -> `/signup.html` (status 200)
   - Substituir a regra catch-all final de status 200 por uma regra formal de fallback com status HTTP 404:
     ```toml
     [[redirects]]
       from = "/*"
       to = "/404.html"
       status = 404
     ```
   - Justificativa técnica: o Netlify serve o arquivo `/404.html` com cabeçalho de resposta `HTTP/1.1 404 Not Found`, informando aos crawlers que o recurso não existe de forma imediata e definitiva.
3. **Tratamento de Rota 404 no Servidor FastAPI Local:**
   - Adicionar manipulador de exceção para HTTP 404 no `backend/main.py` para requisições HTML que não combinem com nenhuma rota ou arquivo estático, servindo `FileResponse("frontend/404.html", status_code=404)` quando o cabeçalho `Accept` incluir `text/html`.
4. **Testes de Regressão e Verificação Automatizada:**
   - Implementar testes assíncronos no pytest validando que:
     - Rotas existentes continuam retornando HTTP 200 (`/`, `/dashboard`, `/login.html`, `/signup.html`).
     - Rotas inexistentes retornam estritamente HTTP 404 com o HTML da página 404.

**Blocked by:** None (can start immediately)

**Status:** completed

- [x] `frontend/404.html` criada com design escuro profissional, mensagem clara de recurso não encontrado e CTA de retorno.
- [x] Tag `<meta name="robots" content="noindex, nofollow">` incluída na página 404.
- [x] Regra de catch-all do `netlify.toml` configurada para redirecionar para `/404.html` com status HTTP 404.
- [x] Servidor FastAPI configurado para responder 404 com o HTML correto em rotas inválidas.
- [x] Testes automatizados incluídos na suíte verificando que requisições a caminhos inexistentes retornam status 404.
