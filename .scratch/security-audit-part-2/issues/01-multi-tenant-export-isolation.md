# 01: Isolamento Multi-Tenant Estrito em Exportações de Dados (CSV e JSON)

**What to build:**
Eliminar a vulnerabilidade crítica de vazamento de dados confidenciais entre múltiplos clientes nos endpoints de exportação de métricas e histórico de chamadas. Atualmente, os endpoints `/api/export/csv` e `/api/export/json` utilizam a dependência genérica `require_admin`, que é satisfeita por qualquer token JWT assinado válido de qualquer usuário registrado. Além disso, as rotas executam `select(RequestLog)` sem qualquer cláusula de restrição por identificador de usuário (`user_id`). Com isso, qualquer cliente autenticado tem acesso para baixar o histórico completo de inferências, provedores, modelos, custos e metadados de todas as outras contas do SaaS.

Este ticket deve entregar:
1. **Migração de Dependência de Autenticação em Exportação:**
   - Em `backend/routers/export.py`, substituir a dependência `require_admin` nos endpoints `GET /api/export/csv` e `GET /api/export/json` pela dependência padrão `get_current_user` (`current_user: User = Depends(get_current_user)`).
   - Garantir que a identidade do tenant seja resolvida e validada explicitamente a partir do token JWT Bearer da requisição.
2. **Filtragem Obrigatória por `user_id` nas Consultas e Streams:**
   - Atualizar a função geradora `generate_csv_stream` para receber `user_id: int` obrigatório.
   - Adicionar a condição `RequestLog.user_id == user_id` na query SQLAlchemy (`select(RequestLog)`), mantendo a ordenação decrescente por timestamp e os filtros opcionais de `provider` e `model`.
   - Atualizar o endpoint `GET /api/export/json` para injetar a mesma cláusula `where(RequestLog.user_id == current_user.id)`.
   - Assegurar que caso o usuário não possua registros no banco, a resposta entregue um arquivo CSV contendo apenas a linha de cabeçalho ou um JSON com lista vazia `[]`, sem escanear a tabela global.
3. **Cobertura Abrangente de Testes Automatizados:**
   - Criar testes automatizados simulando dois usuários distintos (Tenant Alice e Tenant Bob).
   - Inserir registros de `RequestLog` associados individualmente a Alice (`user_id=1`) e Bob (`user_id=2`).
   - Autenticar Alice e solicitar exportação via `/api/export/csv` e `/api/export/json`.
   - Validar estritamente que as exportações de Alice contêm apenas os logs de Alice e 0 ocorrências dos dados de Bob.
   - Autenticar Bob e realizar a mesma validação recíproca.
   - Validar que tentativas não autenticadas em `/api/export/csv` e `/api/export/json` continuam retornando HTTP 401 Unauthorized.

**Blocked by:** None (can start immediately)

**Status:** completed

- [x] Dependência de autorização em `/api/export/csv` e `/api/export/json` migrada para `get_current_user`.
- [x] Cláusula `RequestLog.user_id == current_user.id` aplicada em todas as consultas e streams de exportação.
- [x] Usuários sem registros recebem exportações vazias estruturadas sem acesso a dados de outros tenants.
- [x] Testes de isolamento entre múltiplos tenants para CSV e JSON aprovados sem regressões.
