# Deploy do TokenPulse no Netlify

O frontend do **TokenPulse** é 100% estático e preparado para hospedagem direta no Netlify com proxy reverso transparente para o backend (eliminando qualquer bloqueio de CORS).

## Passo Único de Implantação

1. Acesse o painel do **Netlify** ([app.netlify.com](https://app.netlify.com)).
2. Clique em **"Add new site"** > **"Import an existing project"** e selecione o repositório do TokenPulse no GitHub / GitLab.
3. O Netlify detectará automaticamente o arquivo [`netlify.toml`](file:///mnt/852f644b-0319-4717-8a52-295a71971040/projetos/ai-usage-dashboard/netlify.toml):
   - **Publish directory:** `frontend`
   - **Build command:** *(deixe em branco)*
4. Em **Site Configuration** > **Environment variables**, se você já tiver o backend implantado no Render/Railway, adicione:
   - `BACKEND_URL`: `https://seu-backend.onrender.com`
   *(Ou altere diretamente a URL em `netlify.toml` na linha `to = "https://seu-backend.onrender.com/api/:splat"`)*.
5. Clique em **"Deploy Site"**.

Seu painel estará online e qualquer requisição para `/api/*` será roteada de ponta a ponta para a API na nuvem!
