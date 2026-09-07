# 02: Pinagem de Versões e Subresource Integrity (SRI) em Dependências Frontend

**What to build:**
Neutralizar o risco crítico de comprometimento da cadeia de suprimentos em dependências externas de frontend carregadas via CDN. As páginas da aplicação (`frontend/index.html`, `frontend/dashboard.html`, `frontend/login.html`, `frontend/signup.html` e `frontend/404.html`) atualmente importam ícones Lucide através da URL flutuante `https://unpkg.com/lucide@latest` sem especificação de versão imutável e sem atributo de integridade criptográfica `integrity`. Adicionalmente, `frontend/dashboard.html` carrega o Chart.js sem atributo `integrity`. Como os tokens de autenticação JWT dos usuários são mantidos em `localStorage` (`tp_token`), qualquer adulteração no pacote remoto unpkg ou injeção maliciosa em trânsito permitiria roubo indiscriminado de credenciais ativas.

Este ticket deve entregar:
1. **Fixação Estrita de Versão das Bibliotecas:**
   - Substituir todas as ocorrências de `https://unpkg.com/lucide@latest` por uma versão estável e imutável (ex: `https://unpkg.com/lucide@0.469.0/dist/umd/lucide.min.js` ou `https://cdn.jsdelivr.net/npm/lucide@0.469.0/dist/umd/lucide.min.js`).
   - Manter Chart.js fixado na versão segura já utilizada (`chart.js@4.4.4`).
2. **Implementação de Subresource Integrity (SRI):**
   - Calcular e adicionar os hashes criptográficos SHA-384 oficiais (`integrity="sha384-..."`) a todas as tags `<script>` de provedores externos em:
     - `frontend/index.html`
     - `frontend/dashboard.html`
     - `frontend/login.html`
     - `frontend/signup.html`
     - `frontend/404.html`
   - Adicionar obrigatoriamente o atributo `crossorigin="anonymous"` a cada tag `<script>` que utilize `integrity`.
3. **Alinhamento e Atualização das Políticas de Segurança (CSP):**
   - Garantir que as diretivas `Content-Security-Policy` em `backend/main.py` e `netlify.toml` autorizem os hosts e formatos exatos dos scripts pinados sem bloquear a renderização de ícones e gráficos.
4. **Testes Automatizados de Conformidade de Integridade:**
   - Criar um teste automatizado que varre todos os arquivos `.html` em `frontend/`, validando que:
     - Nenhuma tag de script referencie tags flutuantes como `@latest`.
     - Toda tag de script com origem externa `http://` ou `https://` contenha obrigatoriamente os atributos `integrity` e `crossorigin="anonymous"`.

**Blocked by:** None (can start immediately)

**Status:** completed

- [x] Todas as referências a `lucide@latest` substituídas por versão fixada imutável.
- [x] Atributos `integrity` (SHA-384) e `crossorigin="anonymous"` adicionados em todas as tags `<script>` externas em todos os HTMLs.
- [x] Atributo `integrity` adicionado à tag de `chart.js` no dashboard.
- [x] Políticas de CSP no backend e Netlify alinhadas com as fontes e integridade dos scripts.
- [x] Teste automatizado auditando todas as páginas HTML quanto à ausência de scripts flutuantes e presença de SRI aprovado.
