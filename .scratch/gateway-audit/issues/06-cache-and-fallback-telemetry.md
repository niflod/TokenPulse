# 06: Telemetria de Cache Hits e Fallback sem Duplicação

**What to build:**
Assegurar que chamadas atendidas por cache (seja payload JSON ou streaming SSE reconstruído) persistam exatamente uma linha em `RequestLog` com `cache_hit = true`, `cost_total = 0.0` e os tokens correspondentes, sem contabilizar custo upstream inexistente. Quando ocorrer fallback entre provedores/modelos, registrar os dados operacionais (`original_provider`, `original_model`, `fallback_reason`) em um único registro final consolidado, sem duplicar logs intermediários.

**Blocked by:** 02: Suporte a usage_source e Semântica de Tokens Nulos

**Status:** ready-for-agent

- [x] Cache hit gera exatamente 1 linha em `RequestLog` com `cache_hit = true` e `cost_total = 0.0`
- [x] Fallback gera 1 único `RequestLog` final com os metadados do provedor original e de destino
- [x] Resposta com fallback injeta headers `X-TokenPulse-Fallback` e `X-TokenPulse-Actual-Provider`
- [x] Zero duplicação de métricas e custos em cenários de retry/failover
- [x] Testes automatizados validando contagem exata de linhas persistidas em cache e fallback
