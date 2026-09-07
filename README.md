<div align="center">

# ⚡ TokenPulse
### *Observe your AI.*
**Plataforma Web SaaS de Telemetria, Observabilidade e Faturamento para APIs de Inteligência Artificial**

[![Web SaaS](https://img.shields.io/badge/Platform-Web%20SaaS-4D8DFF?style=for-the-badge&logo=googlechrome)](https://app.tokenpulse.com)
[![Netlify](https://img.shields.io/badge/Frontend-Netlify%20Ready-00C7B7?style=for-the-badge&logo=netlify)](netlify.toml)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI%200.115-009688?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com)
[![Multi-Tenant](https://img.shields.io/badge/Security-Multi--Tenant%20%2B%20Fernet-8B7CFF?style=for-the-badge)](docs/specs/web-saas-pivot-and-direct-sync.md)
[![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)

<br />

**Monitore seus gastos com OpenAI, Claude, Gemini e Groq diretamente pelo navegador.**  
Sem necessidade de terminal, sem Docker e sem alterar as chamadas no seu código.

[Explorar o Site](#-visão-geral-do-site) • [Demonstração ao Vivo](#-demonstração-ao-vivo) • [Deploy em Nuvem](#-deploy-em-nuvem) • [Desenvolvimento Local](#-desenvolvimento-local--self-hosting)

</div>

---

## 🖥️ Visão Geral do Site

O **TokenPulse** é uma solução completa acessível via navegador para desenvolvedores, líderes técnicos e equipes de produto que consom APIs de inteligência artificial.

| Área | Rota | Descrição |
| :--- | :--- | :--- |
| **Landing Page** | `/` (`index.html`) | Apresentação pública do produto, proposta de valor, recursos e chamada para cadastro. |
| **Dashboard** | `/dashboard` (`dashboard.html`) | Painel interativo com gráficos de consumo, telemetria em tempo real (SSE) e projeções. |
| **Autenticação** | `/login` e `/signup` | Cadastro aberto com isolamento estrito de tenants e criptografia de credenciais. |
| **Demonstração** | `/dashboard?demo=true` | Tour interativo imediato com métricas e telemetria simuladas (sem cadastro). |

---

## ⚡ Como Usar (100% no Navegador)

O fluxo principal do TokenPulse foi projetado para zero fricção:

1. **Crie sua Conta Web:**  
   Acesse a página de cadastro (`/signup.html`) e registre seu usuário com email e senha. Cada conta possui isolamento criptográfico completo.
2. **Conecte seus Provedores de IA:**  
   No painel web, adicione suas chaves oficiais de uso/admin (OpenAI, Anthropic, Google Gemini, Groq, OpenRouter). O sistema valida a conexão na hora.
3. **Acompanhe o Consumo em Tempo Real:**  
   Monitore o consumo consolidado, histórico diário/mensal, divisão de custos por modelo, velocidade de gastos (*burn rate*) e projeção da fatura estimada para o fim do mês.

---

## 🎮 Demonstração ao Vivo

Deseja experimentar a interface antes de cadastrar chaves reais?

- Inicie o servidor localmente ou acesse o site e clique em **"Ver Demonstração ao Vivo"**.
- A URL `/dashboard.html?demo=true` ativa imediatamente o modo de demonstração, exibindo telemetria simulada de modelos (`gpt-4o`, `claude-3-5-sonnet`, `gemini-2.0-flash`), gráficos de latência e consumo em tempo real.

---

## ☁️ Deploy em Nuvem

### 1. Frontend no Netlify (Estático + Proxy Reverso)

O frontend é 100% estático e inclui o arquivo [`netlify.toml`](netlify.toml) pré-configurado:

1. Acesse [app.netlify.com](https://app.netlify.com) e clique em **"Add new site"** > **"Import an existing project"**.
2. Selecione o repositório. O Netlify detectará automaticamente:
   - **Publish directory:** `frontend`
   - **Build command:** *(deixar em branco)*
3. As rotas `/api/*` serão redirecionadas de forma transparente para o backend na nuvem sem qualquer problema de CORS.
4. Clique em **"Deploy Site"**.

### 2. Backend na Nuvem (Render / Railway / Fly.io)

O backend FastAPI pode ser implantado diretamente em qualquer serviço gerenciado compatível com Python 3.12 ou Docker:

- **Build Command:** `pip install -r backend/requirements.txt`
- **Start Command:** `python backend/main.py`
- **Variáveis de Ambiente Recomendadas:**
  - `SECRET_KEY`: Chave aleatória forte para geração dos tokens JWT.
  - `ADMIN_API_KEY`: Chave mestra administrativa do sistema.
  - `DATABASE_URL`: URL SQLite ou PostgreSQL gerenciado.

---

## 💻 Desenvolvimento Local & Self-Hosting

### Com npm (Padrão Web)

```bash
# Iniciar o servidor de desenvolvimento
npm run dev

# Executar a suíte de testes
npm test
```

### Com Shell Script

```bash
# Inicialização direta do servidor web local
./start.sh
```

Acesse no seu navegador:
- **Site Institucional:** `http://localhost:8000`
- **Painel de Telemetria:** `http://localhost:8000/dashboard`
- **Área de Acesso:** `http://localhost:8000/login.html`

### Com Docker

```bash
docker compose up -d
```

---

## 🔒 Arquitetura de Segurança & Privacidade

- 🛡️ **Criptografia Simétrica Fernet + HKDF:** Chaves de API armazenadas em repouso são criptografadas com derivação HKDF (SHA-256) e salt exclusivo por usuário.
- 🏢 **Isolamento Multi-Tenant:** Todas as consultas, logs de auditoria e conexões de provedores são estritamente particionadas pelo `user_id` autenticado via JWT.
- 🚫 **Proteção Ativa Anti-SSRF:** Bloqueio rígido de endereços privados (RFC 1918), loopbacks (`127.0.0.1`, `localhost`) e metadados de nuvem (`169.254.169.254`).
- 🔐 **Mascaração de Segredos:** Chaves de provedor nunca são devolvidas em texto claro nas respostas da API ou no estado do cliente.
- 💉 **Imunidade contra DOM XSS:** Frontend sem uso de `innerHTML` interpolado com dados da API e sem eventos inline, operando estritamente via DOM API e `textContent`.
- 📋 **Headers de Proteção:** `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff` e política rigorosa de Content-Security-Policy (CSP).

---

## 🔌 Recursos Avançados: Gateway Transparente (Opcional)

Para desenvolvedores que desejam medição de latência em nível de streaming (*Time-to-First-Token — TTFT*), o TokenPulse mantém seu Gateway Proxy reverso como recurso avançado opcional:

```python
from openai import OpenAI

# Apenas altere a base_url para apontar para o seu TokenPulse
client = OpenAI(
    base_url="https://seu-tokenpulse.com/gateway/openai/v1",
    api_key="tp_live_sua_chave_virtual_aqui",
)

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Olá, TokenPulse!"}],
    stream=True,
)
```

Consulte os guias detalhados em [`docs/specs/`](docs/specs/) para configurações de cache, fallback entre provedores e auditoria funcional.

---

## 📄 Licença

Distribuído sob a licença **MIT**. Consulte `LICENSE` para mais detalhes.
