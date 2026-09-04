# 08: Teste de Carga Concorrente e Resiliência SQLite WAL

**What to build:**
Executar uma bateria de teste de concorrência disparando entre 30 e 50 requisições simultâneas via `asyncio.gather()` contra o TokenPulse Gateway. Comprovar que o SQLite configurado em modo WAL processa todas as gravações concorrentes de telemetria sem erros de `database is locked`, que todas as requisições geram seus respectivos `RequestLog` sem perdas nem deadlocks, e medir o overhead médio introduzido pelo Gateway (< 10ms).

**Blocked by:** 04: Tratamento de Client Disconnect e Provider Drop em Streaming, 05: Preservação Fiel de Erros Upstream e Headers de Rate Limit, 06: Telemetria de Cache Hits e Fallback sem Duplicação, 07: SSE Single Delivery e Reconexão Reativa do Dashboard

**Status:** ready-for-agent

- [x] Execução de 30 a 50 requisições simultâneas via `asyncio.gather()` sem falhas de conexão
- [x] 100% de sucesso sem nenhum erro de `sqlite3.OperationalError: database is locked`
- [x] Contagem exata de `RequestLog` gravados no banco equivalente ao número de requisições disparadas
- [x] Medição de overhead de proxy do Gateway reportada (média < 10ms adicionais sobre o upstream)
- [x] Zero vazamentos de conexões em `app.state.http_client`
