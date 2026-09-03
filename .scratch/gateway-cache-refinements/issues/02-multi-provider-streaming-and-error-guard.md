# 02: Robustez de Streaming Multi-provedor e Restrição de Erros no Cache

**What to build:**
Ajustar o pipeline de streaming e cache do Gateway para:
1. Reconstruir chunks SSE compatíveis tanto com OpenAI quanto com Anthropic (`content[0].text`).
2. Condicionar o salvamento em cache estritamente a requisições HTTP `POST` bem-sucedidas (`status_code == 200` e sem erros de conexão).
3. Incluir o `subpath` na chave hash para evitar colisões entre rotas distintas.
4. Emitir evento com `cache_hit: True` no SSE de telemetria em tempo real (`event_bus`).

**Blocked by:** 01: Validação Precoce de Autenticação e Chaves Virtuais no Gateway

**Status:** completed

- [x] Chave hash de cache inclui o subpath e só processa requisições HTTP POST
- [x] Streams cacheados nunca são salvos em caso de erro HTTP (status >= 400) ou desconexão prematura
- [x] Reconstrução SSE suporta formato Anthropic e OpenAI
- [x] Notificação de telemetria realtime (`/api/realtime/stream`) contém `cache_hit: True`
- [x] Testes automatizados cobrindo streaming com erro (não cacheado) e cache_hit no SSE
