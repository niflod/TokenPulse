# 01: Particionamento Multi-Tenant do Cache do Gateway e Vinculação de Chaves Virtuais

**What to build:**
Eliminar a vulnerabilidade crítica de vazamento de dados entre clientes (*cross-tenant data leak*) no cache de respostas de inferência do gateway. Atualmente, a função de cálculo de chave de cache gera um hash SHA-256 baseado exclusivamente em provedor, modelo e corpo da requisição (mensagens, temperatura, tools), ignorando completamente a identidade do usuário ou da chave virtual que realizou a chamada. Como resultado, requisições com prompts idênticos enviadas por tenants distintos compartilham a mesma entrada em cache, fazendo com que um cliente receba respostas confidenciais de outro (`X-TokenPulse-Cache: HIT`).

Este ticket deve entregar:
1. **Vinculação de Chaves Virtuais ao Usuário:**
   - Garantir que a emissão de `ClientApiKey` através da rota de criação registre obrigatoriamente o `user_id` do usuário autenticado na sessão.
   - Atualizar listagens e consultas de chaves de API para filtrar pelo `user_id` da conta.
2. **Particionamento Obrigatório da Chave de Cache:**
   - Atualizar `compute_gateway_cache_key` para exigir o identificador de particionamento do tenant (`user_id` ou identificador canônico do cliente).
   - Incorporar o identificador de partição no payload canônico do hash SHA-256 antes da geração da chave final.
3. **Propagação de Contexto no Gateway:**
   - Na resolução de autenticação do gateway (`tp_live_` ou BYOK), extrair e vincular o tenant identificado.
   - Passar a identidade do tenant na verificação de cache (`db_cached = await get_cached_response(db, cache_key)`) e na gravação de novas entradas (`save_gateway_cache`).
4. **Kill-Switch de Emergência:**
   - Garantir que a configuração `gateway_cache_enabled` (ou flag booleana de ambiente) permita desativar imediatamente o cache sem reiniciar a aplicação ou causar falha nas chamadas proxy.
5. **Cobertura de Testes de Isolamento:**
   - Adicionar casos de teste no backend onde dois tenants distintos enviam prompts idênticos através do gateway. Validar que o primeiro gera cache (`MISS`), mas o segundo NÃO consome a resposta do primeiro, gerando um novo `MISS` e armazenando entrada segregada.

**Blocked by:** None (can start immediately)

**Status:** completed

- [x] Criação de `ClientApiKey` vincula obrigatoriamente o `user_id` do tenant autenticado.
- [x] `compute_gateway_cache_key` incorpora o identificador do tenant no payload canônico do hash SHA-256.
- [x] O gateway recupera e grava cache utilizando a chave particionada por tenant.
- [x] Dois tenants com prompts idênticos não compartilham dados em cache.
- [x] Chave de configuração ou flag permite desativação imediata do cache do gateway.
- [x] Testes automatizados de isolamento de cache aprovados sem regressão.
