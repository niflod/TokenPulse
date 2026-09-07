# 02: Segregação de Sessão e Filtro de Métricas Multi-Tenant no Streaming SSE

**What to build:**
Corrigir o vazamento global de telemetria e métricas em tempo real no endpoint de Server-Sent Events (SSE). Atualmente, a emissão de tickets descartáveis (`/api/realtime/ticket`) é pública e não exige autenticação nem associa um `user_id`. Ao conectar em `/api/realtime/stream`, todos os clientes são inscritos no mesmo barramento (`event_bus`) global e recebem a cada 5 segundos um resumo periódico de métricas calculado por `aggregator.get_metrics_summary(db)` sem filtro de `user_id`, permitindo que qualquer usuário visualize o gasto, modelos e volume de chamadas de todos os outros clientes.

Este ticket deve entregar:
1. **Autenticação e Associação de Identidade no Ticket:**
   - Exigir autenticação válida (Bearer token JWT) na rota de solicitação de ticket descartável `/api/realtime/ticket`.
   - Armazenar o `user_id` do titular junto com o timestamp de expiração no repositório de tickets (`_REALTIME_TICKETS`).
2. **Resolução de Identidade na Conexão do Stream:**
   - Na validação do ticket em `/api/realtime/stream`, retornar o `user_id` associado ao ticket consumido.
   - Atribuir o `user_id` validado ao estado da requisição (`request.state.user_id`).
3. **Escopo Tenant no Resumo de Métricas Periódicas:**
   - Atualizar o gerador de eventos (`event_generator`) para receber o `user_id` do cliente conectado.
   - Invocar `aggregator.get_metrics_summary(db, user_id=user_id)` no disparo periódico a cada 5 segundos, garantindo que o resumo (`summary`), projeção (`projection`) e custo reflitam apenas as chamadas do tenant proprietário.
4. **Isolamento de Eventos em Tempo Real no Barramento:**
   - Filtrar os eventos de telemetria despachados pelo `event_bus` para que o gerador de SSE emita apenas eventos pertencentes ao `user_id` da conexão ativa, descartando eventos de outros tenants.
5. **Cobertura de Testes de Isolamento de Streaming:**
   - Adicionar testes de integração simulando dois clientes SSE conectados (Tenant 1 e Tenant 2).
   - Verificar que a execução de uma requisição pelo Tenant 1 não gera evento nem altera o resumo de métricas transmitido na conexão SSE do Tenant 2.

**Blocked by:** None (can start immediately)

**Status:** completed

- [x] Rota `/api/realtime/ticket` exige autenticação JWT e persiste o `user_id` no ticket descartável.
- [x] Conexão `/api/realtime/stream` valida o ticket e associa a conexão ao `user_id` do titular.
- [x] O disparo periódico de métricas (5s) filtra estritamente pelo `user_id` do cliente conectado.
- [x] Eventos em tempo real transmitidos pelo stream SSE são filtrados para o tenant proprietário.
- [x] Tentativas não autenticadas de obter ticket ou abrir stream são rejeitadas com 401.
- [x] Testes automatizados de segregação de SSE aprovados com sucesso.
