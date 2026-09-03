# 11: Suíte de Testes de Segurança Consolidada

**What to build:** Arquivo dedicado `tests/test_security_remediation.py` cobrindo ponta a ponta todas as vulnerabilidades remediadas: SECRET_KEY ausente em produção, bloqueio SSRF por DNS rebinding, restrição do Ollama, proteção contra takeover no bootstrap, recusa de JWT em query string, rejeição de requests anônimos no Gateway, log redaction e validação de CSP sem scripts inline.

**Blocked by:** 03: SSRF com Resolução DNS e Bloqueio de Domínio Custom, 04: Hardening do Ollama (Restringir a Localhost), 05: Proteção do Bootstrap (`/api/auth/setup`), 06: Remover JWT da Query String (Ticket Descartável para SSE), 07: Gateway Exige Autenticação (Rejeitar Requests Anônimos)

**Status:** completed

- [x] Testes automatizados para todos os cenários P1 implementados
- [x] Teste de rejeição de inicialização sem `SECRET_KEY` em produção
- [x] Teste de bloqueio SSRF com domínios resolvendo para IPs locais/privados
- [x] Teste de bloqueio de setup remoto não autenticado
- [x] Teste de bloqueio de JWT em query string para SSE/export
- [x] 100% dos testes de segurança passando via `pytest tests/test_security_remediation.py -v`
