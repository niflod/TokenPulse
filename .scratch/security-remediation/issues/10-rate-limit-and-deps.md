# 10: Rate Limit por Chave Autenticada + Auditoria de Dependências

**What to build:** Rate limiter usa o prefixo ou identificador da chave virtual `tp_live_` como chave primária de rate limiting quando a requisição for autenticada (com fallback para IP do cliente). Documentação da limitação single-instance/single-worker. Execução de auditoria de dependências com `pip-audit`.

**Blocked by:** 07: Gateway Exige Autenticação (Rejeitar Requests Anônimos)

**Status:** completed

- [x] Rate limiter no Gateway prioriza identidade autenticada (`tp_live_` key prefix) sobre IP
- [x] Fallback para IP mantido quando aplicável
- [x] Chaves virtuais distintas possuem cotas de RPM independentes mesmo originadas do mesmo IP
- [x] Documentação arquitetural da limitação in-memory para nós únicos
- [x] Execução e relatório de `pip-audit` documentando vulnerabilidades conhecidas em dependências
