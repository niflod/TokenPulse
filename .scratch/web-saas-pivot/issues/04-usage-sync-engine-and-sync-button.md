# 04: Motor de Sincronização de Uso (OpenAI & OpenRouter) e Botão "Sincronizar Agora"

**What to build:**
Criar um motor de sincronização direta que consulta periodicamente as APIs oficiais de faturamento da OpenAI (Organization Usage & Costs) e da OpenRouter (Key/Generation stats) usando as credenciais do usuário. Adicionar no topo do dashboard um botão "Sincronizar Agora" com feedback visual de carregamento e timestamp de "Última sincronização", persistindo os consumos de tokens e custos de forma agregada para alimentar os gráficos do dashboard sem exigir terminal ou IDE.

**Blocked by:** 03: Conexão Web de Provedores com Validação Instantânea

**Status:** completed

- [x] Serviço assíncrono de sincronização para a API de Organização da OpenAI (consumo diário/horário de tokens de input/output e custo por modelo).
- [x] Serviço assíncrono de sincronização para a API da OpenRouter (leitura de saldo consumido e histórico de uso por chave).
- [x] Endpoint `POST /api/sync/now` e rotina de polling em background que grava/atualiza os registros de consumo associados ao `user_id`.
- [x] Ingestão idempotente: rodar a sincronização repetidas vezes não duplica métricas nem distorce os totais do dashboard.
- [x] Botão "Sincronizar Agora" no header do dashboard com estado desabilitado durante execução e atualização reativa dos gráficos.
- [x] Testes automatizados com `httpx.MockTransport` simulando payloads de uso da OpenAI e OpenRouter e verificando integridade das métricas no banco.
