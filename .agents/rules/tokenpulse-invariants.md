---
description: Invariantes arquiteturais, de segurança e de testes do projeto TokenPulse
alwaysApply: true
---

# Invariantes do TokenPulse

Ao desenvolver ou refatorar componentes no TokenPulse, siga estritamente estas diretrizes:

## 1. Frontend HTTP Client (`frontend/js/api.js`)
- Todas as requisições para a API do backend devem utilizar exclusivamente `this._request(path, options)`.
- NUNCA utilize `this._fetch`, `fetch` direto ou métodos não definidos.
- Sempre retorne o padrão `{ data, error }`.

## 2. Segurança e Proteção Anti-SSRF
- Qualquer URL externa configurável por usuário (ex: Webhooks, URLs base de provedores) DEVE ser validada contra redes privadas.
- Importe e reutilize `BLOCKED_IP_NETWORKS` de `backend/security.py` (bloqueando `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `169.254.169.254` e loopback).
- Esquemas permitidos: `http` e `https` apenas (sem esquemas locais como `file://`).

## 3. Idempotência em Consultas e Prevenção de Spam
- Endpoints HTTP `GET` consultados em loops de polling do dashboard NUNCA devem disparar efeitos colaterais externos (ex: envio de webhook) sem controle de frequência.
- Use um mapa de cooldown em memória (ex: 15 minutos) ou desacople a avaliação em background tasks dedicadas.

## 4. Gateway e Sanitização de Headers Upstream
- O Gateway deve remover o cabeçalho `Authorization` se este contiver a chave virtual do TokenPulse (`tp_live_...`) antes de retransmitir a chamada ao upstream.
- Se a requisição usar chave virtual mas o provedor não tiver chave real configurada, aborte imediatamente com `HTTP 502 Bad Gateway`.

## 5. Testes Automatizados e Fixtures
- Para fixtures assíncronas no pytest, importe `pytest_asyncio` e utilize `@pytest_asyncio.fixture` (NUNCA `@pytest.fixture` assíncrono).
- Testes devem utilizar `httpx.MockTransport` para garantir 100% de isolamento de rede externa.
