# 03: Respeito ao Limite de Taxa Individual de Chaves Virtuais no Gateway

**What to build:**
Permitir a imposição de limites de taxa (Rate Limiting) diferenciados por chave de API virtual no Gateway de Inteligência Artificial. Atualmente, o modelo de dados `ClientApiKey` possui a coluna `rate_limit_rpm` configurável (ex: 60, 30 ou 10 requisições por minuto), porém o roteador do gateway (`backend/routers/gateway.py`) ignora completamente essa configuração e repassa unicamente o limite global `settings.gateway_rate_limit_rpm` (padrão de 120 RPM) para todos os clientes. Com isso, clientes com limites restritivos ou planos de teste conseguem emitir requisições até o teto global da infraestrutura.

Este ticket deve entregar:
1. **Extração e Propagação do RPM da Chave Virtual:**
   - Em `backend/routers/gateway.py`, durante a etapa de autenticação de chaves de cliente virtuais (`tp_live_...`), armazenar o objeto da chave validada (`key_obj: ClientApiKey`) no contexto da requisição.
   - Extrair o valor de `key_obj.rate_limit_rpm`. Se o valor for válido e positivo (> 0), utilizá-lo como o limite efetivo para a chamada.
   - Se for uma requisição BYOK ou se a chave não tiver `rate_limit_rpm` específico, utilizar o limite global padrão do sistema (`settings.gateway_rate_limit_rpm`).
2. **Aplicação do Limite Dinâmico no Rate Limiter Deslizante:**
   - Ao invocar `gateway_rate_limiter.is_allowed(client_key, custom_rpm=effective_rpm)`, repassar o RPM específico da chave virtual.
   - Em caso de estouro do limite, retornar HTTP 429 Too Many Requests com cabeçalho `Retry-After: <segundos>` e mensagem explicativa.
3. **Cobertura de Testes de Limite Diferenciado:**
   - Criar teste automatizado onde uma `ClientApiKey` é emitida com `rate_limit_rpm=5`.
   - Disparar 5 requisições com sucesso via gateway (HTTP 200).
   - Confirmar que a 6ª requisição no mesmo minuto é barrada com HTTP 429 e cabeçalho `Retry-After`.
   - Verificar que outra chave com limite padrão ou mais alto não é afetada pelo bloqueio da primeira.

**Blocked by:** None (can start immediately)

**Status:** completed

- [x] Gateway extrai e respeita `key_obj.rate_limit_rpm` quando a autenticação utiliza chave virtual `tp_live_...`.
- [x] Requisições com limite customizado são bloqueadas com 429 e `Retry-After` ao ultrapassar o teto da respectiva chave.
- [x] Requisições sem limite customizado ou via BYOK utilizam o teto global configurado.
- [x] Testes automatizados validando o throttling por chave aprovados sem falhas.
