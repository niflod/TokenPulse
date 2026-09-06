# 05: Ingestão Multi-Provedor (Anthropic, Gemini, Groq) e Métricas Consolidadas

**What to build:**
Estender o motor de sincronização direta para coletar métricas e quotas dos demais provedores suportados (Anthropic, Gemini e Groq), integrando todas as fontes em uma visão unificada no dashboard. O usuário visualiza no navegador o consumo consolidado por período (hoje, semana, mês), gráficos de quebra de custo por modelo e projeções de gastos consolidadas entre múltiplos provedores em uma única tela.

**Blocked by:** 04: Motor de Sincronização de Uso (OpenAI & OpenRouter) e Botão "Sincronizar Agora"

**Status:** completed

- [x] Adaptadores de sincronização para Anthropic (Workspaces/Costs), Gemini (Cloud Quota/Tokens) e Groq.
- [x] Agregação unificada multi-provedor na API `/api/metrics/summary` e `/api/metrics/timeseries` ponderando dados de todos os provedores conectados pelo usuário.
- [x] Gráfico de pizza / rosca por provedor e modelo refletindo a distribuição real dos gastos totais.
- [x] Indicador visual de burn rate diário e estimativa de fatura no fim do mês considerando todas as conexões ativas.
- [x] Suíte de testes abrangente cobrindo agregação de múltiplos provedores concorrentes e resiliência quando um dos provedores estiver indisponível.
