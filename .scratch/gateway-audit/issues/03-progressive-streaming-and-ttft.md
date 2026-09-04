# 03: Streaming Progressivo Real & Medição de TTFT

**What to build:**
Garantir que requisições com `stream=true` entreguem chunks de forma estritamente progressiva e imediata ao cliente, sem acumular nem bufferizar o stream em memória intermediária. Medir com precisão sub-milissegundo o Time-To-First-Token (`time_to_first_token_ms`) no primeiro chunk útil utilizando `time.perf_counter()`, bem como a duração total do stream (`stream_duration_ms`).

**Blocked by:** 01: Request Normal Transparente & Single Log Execution

**Status:** ready-for-agent

- [x] Chunks SSE repassados ao cliente imediatamente conforme chegam do upstream (zero bufferização)
- [x] `time_to_first_token_ms` medido exclusivamente no primeiro chunk de conteúdo via `time.perf_counter()`
- [x] `stream_duration_ms` gravado com precisão do início do stream ao último chunk
- [x] Extração em tempo real de `usage` e `finish_reason` sem atrasar a entrega dos chunks
- [x] Teste automatizado com simulação temporal progressiva validando TTFT estritamente positivo
