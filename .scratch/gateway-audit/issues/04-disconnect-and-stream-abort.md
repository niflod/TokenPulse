# 04: Tratamento de Client Disconnect e Provider Drop em Streaming

**What to build:**
Quando o cliente desconecta no meio de uma resposta em streaming, o Gateway detecta o cancelamento (`asyncio.CancelledError`), fecha imediatamente a conexão upstream com `await upstream_resp.aclose()`, evita vazamento de tarefas assíncronas no loop e registra telemetria com status `499`, `finish_reason = "cancelled"` e `error_message = "Client disconnected during streaming"`. Se o provedor upstream cair no meio do stream, o Gateway grava status de falha (`502`) e não registra a requisição como sucesso.

**Blocked by:** 03: Streaming Progressivo Real & Medição de TTFT

**Status:** ready-for-agent

- [x] Cancelamento do cliente aciona `upstream_resp.aclose()` imediatamente
- [x] Telemetria de client disconnect registra `status_code = 499` e `finish_reason = "cancelled"`
- [x] Resposta abortada não é salva no cache de respostas
- [x] Queda abrupta do provider registra status `502` com mensagem de erro e não marca sucesso
- [x] Testes automatizados reproduzindo client disconnect e provider disconnect durante streaming
