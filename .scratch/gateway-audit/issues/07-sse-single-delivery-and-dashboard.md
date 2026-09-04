# 07: SSE Single Delivery e Reconexão Reativa do Dashboard

**What to build:**
Garantir que a finalização de uma requisição emita estritamente um evento `request.completed` pelo `EventBus` e que ele seja entregue pelo stream SSE (`/api/realtime/stream`) sem duplicações acidentais. Validar a reconexão automática do frontend em caso de interrupção e garantir que os gráficos Chart.js e métricas de tela sejam atualizados reativamente sem recriar os objetos de gráfico nem provocar memory leaks.

**Blocked by:** 01: Request Normal Transparente & Single Log Execution

**Status:** ready-for-agent

- [x] Uma requisição ao Gateway gera estritamente 1 evento `request.completed` entregue pelo SSE
- [x] SSE entrega evento rapidamente (< 100ms após persistência no banco)
- [x] Frontend gerencia reconexão sem disparar conexões múltiplas concorrentes
- [x] Chart.js é atualizado via mutação in-place de datasets (`chart.update()`) sem destruição
- [x] Testes automatizados validando entrega única e ausência de múltiplos eventos repetidos
