# 01: Validação Precoce de Autenticação e Chaves Virtuais no Gateway

**What to build:**
Garantir que toda requisição ao Gateway valide a autenticação do cliente e a integridade da chave virtual (`tp_live_...`) antes de qualquer consulta ao cache de respostas. Chaves inexistentes, revogadas ou desabilitadas devem receber HTTP 401 Unauthorized imediatamente, impedindo acesso indevido a dados cacheados.

**Blocked by:** None (can start immediately)

**Status:** completed

- [x] A validação de credenciais upstream e verificação de chaves virtuais ocorrem antes do lookup da chave de cache
- [x] Requisições com `tp_live_` inválido ou desativado recebem HTTP 401 mesmo se o prompt já existir no cache
- [x] Chaves válidas continuam recebendo Cache HIT normalmente em <5ms
- [x] Teste automatizado validando a rejeição 401 de chave inválida em prompt cacheado
