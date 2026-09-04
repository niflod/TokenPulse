# 05: Preservação Fiel de Erros Upstream e Headers de Rate Limit

**What to build:**
Repassar transparentemente os códigos e mensagens de erro do provedor upstream (400 Bad Request, 401/403 Auth Error, 429 Rate Limit, 502/503/504 Service Errors), sem achatá-los em erros 500 genéricos do TokenPulse. Preservar explicitamente headers de controle operacional como `Retry-After` em 429 e categorizar timeouts de rede como `provider_timeout`. Garantir sanitização estrita de credenciais em todos os corpos de erro retornados e persistidos.

**Blocked by:** 01: Request Normal Transparente & Single Log Execution

**Status:** ready-for-agent

- [x] Status 400 repassa corpo de erro original para depuração do cliente
- [x] Status 429 preserva header `Retry-After` retornado pelo provider
- [x] Status 502/503/504 mantidos e não convertidos em 500 interno
- [x] Timeouts de conexão e leitura categorizados como `provider_timeout` em `RequestLog`
- [x] Testes automatizados cobrindo cada classe de erro e sanitização de secrets em responses de erro
