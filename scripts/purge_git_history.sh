#!/usr/bin/env bash
set -euo pipefail

# scripts/purge_git_history.sh — Permanently removes sensitive files from git history
# REQUIRES USER CONFIRMATION because it rewrites commit SHAs.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

echo "================================================================="
echo "  AVISO CRÍTICO: PURGA PERMANENTE DO HISTÓRICO GIT (REWRITE)     "
echo "================================================================="
echo "Esta operação reescreve todos os hashes de commit do repositório."
echo "Após a execução, será necessário executar 'git push --force origin main'."
echo ""
read -p "Deseja continuar com o expurgo permanente? [s/N]: " -r CONFIRM
if [[ ! "${CONFIRM}" =~ ^[sS]$ ]]; then
    echo "Operação abortada pelo usuário."
    exit 0
fi

# Ensure git-filter-repo is available
if ! command -v git-filter-repo &>/dev/null; then
    echo "Instalando git-filter-repo..."
    pip install git-filter-repo || "${ROOT_DIR}/backend/.venv/bin/pip" install git-filter-repo
fi

echo "==> Executando git filter-repo para expurgar arquivos sensíveis..."
git filter-repo --force \
    --invert-paths \
    --path-glob "*.db" \
    --path-glob "*.sqlite*" \
    --path-glob ".env" \
    --path-glob ".venv*" \
    --path-glob "__pycache__*"

echo "==> Limpando referências e executando garbage collection agressivo..."
git reflog expire --expire=now --all
git gc --prune=now --aggressive

echo "✅ Histórico Git limpo com sucesso!"
echo "Verificação:"
git log --all --oneline -- "*.db" ".env" || echo "Zero ocorrências de arquivos sensíveis no histórico."
