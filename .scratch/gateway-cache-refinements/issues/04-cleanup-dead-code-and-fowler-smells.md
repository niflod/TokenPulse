# 04: Refatoração Limpa de Caching e Remoção de Código Morto

**What to build:**
Eliminar os code smells identificados na auditoria de padrões:
1. Remover o campo especulativo `response_headers_json` em `backend/models.py` e assinaturas associadas.
2. Unificar a lógica duplicada de salvamento de cache em streaming e non-streaming em um helper assíncrono único `_dispatch_cache_persistence`.
3. Renomear variáveis crípticas em `gateway.py` para nomes explícitos e semânticos.

**Blocked by:** 02: Robustez de Streaming Multi-provedor e Restrição de Erros no Cache, 03: Evicção Automática e Ajustes da API REST de Estatísticas de Cache

**Status:** completed

- [x] Campo morto `response_headers_json` removido cirurgicamente
- [x] Helpers duplicados de persistência unificados em `_dispatch_cache_persistence`
- [x] Variáveis crípticas renomeadas
- [x] 100% dos testes da suíte (`pytest tests/ -v`) continuam passando sem regressão
