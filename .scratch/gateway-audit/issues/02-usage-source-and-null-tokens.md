# 02: Suporte a usage_source e Semântica de Tokens Nulos

**What to build:**
Adiciona a coluna `usage_source` à tabela `request_logs` (`"reported"` para tokens enviados pelo provedor, `"unknown"` quando omitidos). Quando um modelo ou provedor não reportar usage de tokens, `input_tokens`, `output_tokens` e `total_tokens` são gravados como `None` (nunca `0`), impedindo a criação de médias estatísticas falsas ou custos inventados no dashboard.

**Blocked by:** 01: Request Normal Transparente & Single Log Execution

**Status:** ready-for-agent

- [x] Campo `usage_source: Mapped[Optional[str]]` adicionado ao schema de `RequestLog`
- [x] Provedores que omitem usage gravam `input_tokens = None`, `output_tokens = None`, `total_tokens = None` e `usage_source = "unknown"`
- [x] Provedores com usage gravam os valores inteiros e `usage_source = "reported"`
- [x] Modelos ausentes do catálogo de pricing resultam em `cost_total = None` (sem preço inventado)
- [x] Testes automatizados cobrindo chamadas com e sem usage
