<div align="center">

# ⚡ TokenPulse
### *Observe your AI.*
**Telemetria, Observabilidade e Proteção em Tempo Real para APIs de Inteligência Artificial**

![Python](https://img.shields.io/badge/Python-3.12-blue?style=for-the-badge&logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=for-the-badge&logo=fastapi)
![SQLite WAL](https://img.shields.io/badge/SQLite-Async%20WAL-003B57?style=for-the-badge&logo=sqlite)
![SSE](https://img.shields.io/badge/Realtime-SSE-orange?style=for-the-badge)
![Security](https://img.shields.io/badge/Security-HKDF%20%2B%20SSRF%20Guard-success?style=for-the-badge)
![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)

</div>

---

## 🖥️ Visão Geral

O **TokenPulse** monitora, audita e analisa consumo de APIs de IA (OpenAI, Anthropic, Google Gemini) em tempo real, fornecendo telemetria de latência, projeções de limite (*burn rate* / ETA), detecção de anomalias e segurança de ponta a ponta sem vazamento de segredos.

```text
┌────────────────────────────────────────────────────────────────────────┐
│  TOKENPULSE  ● BACKEND CONECTADO                  [ LIVE SSE STREAM ]  │
├────────────────────────────────────────────────────────────────────────┤
│  HOJE (68.4%)           ESTA SEMANA (42.1%)     ESTE MÊS (31.7%)       │
│  ████████████░░░░░░     ████████░░░░░░░░░░░     ██████░░░░░░░░░░░░     │
│  6.840 / 10.000 req     42.100 / 100.000 req    158.400 / 500.000 req  │
├────────────────────────────────────────────────────────────────────────┤
│  BURN RATE & PROJEÇÃO:                                                 │
│  Velocidade: 380 req/h  │  ETA para Limite: ~ 6h 45m  │  Projeção: 91% │
├────────────────────────────────────────────────────────────────────────┤
│  GRÁFICOS AO VIVO:                                                     │
│  [ Timeline 24h ] [ Provedores ] [ Input vs Output ] [ Horário ]       │
├────────────────────────────────────────────────────────────────────────┤
│  TELEMETRIA DE MODELOS:                                                │
│  • gpt-4o             3.420 req   4.3M tok   810ms latência   $19.00   │
│  • claude-3-5-sonnet  2.100 req   3.1M tok   920ms latência   $19.95   │
│  • gemini-2.0-flash   1.150 req   1.6M tok   340ms latência   $0.32    │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 🔒 Arquitetura de Segurança Implementada

- 🛡️ **Derivação de Chave Criptográfica HKDF:** Derivação segura via HKDF (SHA-256) com salt específico para criptografia simétrica Fernet de API Keys.
- 🚫 **Proteção Avançada contra SSRF:** Validação restrita de `base_url` de provedores. Bloqueio automático de loopback (`localhost`, `127.0.0.1`), endereços locais e IPs privados (RFC 1918).
- 🔑 **Autenticação Administrativa (`X-Admin-Key`):** Endpoints de mutação (`/api/providers`, `/api/logs`, `/api/alerts`, `/api/export`) protegidos por chave administrativa em tempo constante.
- 🌐 **CORS Restrito:** Origens permitidas restritas por padrão para `http://localhost:8000` e `http://127.0.0.1:8000`. Sem wildcards permissivos.
- 💉 **Imunidade contra DOM XSS:** Frontend sem uso de `innerHTML` interpolado com dados da API e sem `onclick` inline. Manipulação estrita via DOM API e `textContent`.
- 📋 **Content Security Policy (CSP):** Cabeçalho CSP ativo com restrição para scripts, conexões, fontes e estilos autorizados.
- 📦 **Higiene de Repositório e Containers:** `.gitignore` e `.dockerignore` ativos garantindo zero vazamentos de `.env`, bases de dados locais ou arquivos temporários.

---

## ⚡ Real-Time & Telemetria do Gateway

### 1. Server-Sent Events (SSE)
O frontend conecta-se via `GET /api/realtime/stream` recebendo atualizações instantâneas de telemetria conforme requisições ocorrem, com fallback automático para polling inteligente.

### 2. Ingestão de Telemetria via SDK / Gateway
Qualquer backend, proxy ou interceptor pode registrar chamadas no TokenPulse através do endpoint unificado:

```bash
POST /api/v1/telemetry
Content-Type: application/json
X-Admin-Key: <sua-chave-se-configurada>

{
  "provider": "openai",
  "model": "gpt-4o",
  "input_tokens": 1500,
  "output_tokens": 600,
  "latency_ms": 780.2,
  "status_code": 200
}
```

*O custo financeiro é calculado automaticamente via catálogo centralizado em `pricing.py`.*

---

## 🌐 TokenPulse Gateway (Reverse Proxy Transparente)

O Gateway intercepta chamadas para OpenAI, Anthropic e Gemini, repassando requisições e respostas de forma transparente enquanto captura telemetria (tokens, latência, TTFT, custo estimado e logs de erro).

### 1. Integração com OpenAI Python SDK

Basta configurar o `base_url` para apontar para o TokenPulse Gateway:

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:8000/gateway/openai/v1",
    api_key="sua-chave-openai",  # Se configurada no TokenPulse, qualquer valor funciona
)

response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Olá!"}],
    stream=True,  # O TokenPulse mede Time-to-First-Token (TTFT) automaticamente
)

for chunk in response:
    print(chunk.choices[0].delta.content or "", end="")
```

### 2. Integração com cURL (OpenAI & Anthropic)

```bash
# OpenAI via Gateway
curl -X POST http://127.0.0.1:8000/gateway/openai/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -d '{"model": "gpt-4o", "messages": [{"role": "user", "content": "Hello"}]}'

# Anthropic via Gateway
curl -X POST http://127.0.0.1:8000/gateway/anthropic/v1/messages \
  -H "Content-Type: application/json" \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -d '{"model": "claude-3-5-sonnet-20241022", "max_tokens": 256, "messages": [{"role": "user", "content": "Hello"}]}'
```

### 3. Integração com JavaScript / TypeScript

```typescript
import OpenAI from "openai";

const openai = new OpenAI({
  baseURL: "http://127.0.0.1:8000/gateway/openai/v1",
  apiKey: process.env.OPENAI_API_KEY || "dummy-key",
});

const res = await openai.chat.completions.create({
  model: "gpt-4o",
  messages: [{ role: "user", content: "Qual a capital da França?" }],
});
console.log(res.choices[0].message.content);
```

---

## 🚀 Como Iniciar

### 1. Inicialização Rápida (Local)

```bash
# Iniciar o servidor
./start.sh
```

Acesse no seu navegador: **`http://127.0.0.1:8000`**

### 2. Executando os Testes Automatizados

```bash
backend/.venv/bin/python -m pytest tests/
```

### 3. Executando com Docker

```bash
docker compose up -d
```

---

## 📄 Licença

Distribuído sob a licença MIT. Veja `LICENSE` para mais detalhes.
