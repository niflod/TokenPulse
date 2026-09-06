# 02: Configuração Netlify e Proxy Reverso Anti-CORS

**What to build:**
Disponibilizar toda a infraestrutura declarativa necessária para que a pasta `frontend/` seja implantada e servida diretamente como site estático no Netlify, configurando regras de redirecionamento transparente para que todas as requisições para `/api/*` sejam encaminhadas em nível de rede para o backend de API em nuvem (`API_URL`), eliminando completamente restrições de CORS e requisições bloqueadas pelo navegador.

**Blocked by:** None (can start immediately)

**Status:** completed

- [x] Arquivo `netlify.toml` na raiz do projeto com publicação da pasta `frontend/` e regras de build limpas.
- [x] Regras de proxy reverso (`[[redirects]]`) no `netlify.toml` mapeando `/api/*` para a URL do backend com status 200 e force=true.
- [x] Suporte a SPA routing no Netlify redirecionando rotas desconhecidas para `index.html`.
- [x] Ajuste no cliente HTTP do frontend (`frontend/js/api.js`) para usar caminhos relativos `/api` por padrão quando hospedado no Netlify, garantindo que o proxy reverso funcione sem configurações adicionais no cliente.
- [x] Documentação concisa de 1 passo em `docs/deployment/netlify.md` explicando como conectar o repositório Git ao Netlify.
