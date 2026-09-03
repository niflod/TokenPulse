# 01: Expurgo do Histórico Git e Script de Release Limpo

**What to build:** Histórico Git livre de `*.db`, `.env` e `.venv/` usando `git filter-repo`. Script `scripts/build_release.sh` que gera artefato limpo excluindo `.git/`, `.venv/`, `*.db`, `__pycache__/` e `.env`. Validação automatizada do conteúdo do pacote.

**Blocked by:** None (pode começar imediatamente)

**Status:** completed

- [x] Script `scripts/build_release.sh` criado e funcional
- [x] Artefato gerado pelo script não contém `.git/`, `.venv/`, `*.db`, `.env`, `__pycache__/`
- [x] Script interativo `scripts/purge_git_history.sh` preparado para expurgo do histórico Git sob confirmação
- [x] Validação automatizada de conformidade no script de release
