#!/usr/bin/env bash
set -euo pipefail

# scripts/build_release.sh — Secure release packaging for TokenPulse
# Packages clean artifact excluding sensitive local data (.git, .venv, *.db, .env, caches)

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="${ROOT_DIR}/dist"
VERSION="$(git -C "${ROOT_DIR}" describe --tags --always 2>/dev/null || echo "v1.0.0")"
ARCHIVE_NAME="tokenpulse-${VERSION}.tar.gz"
TARGET_ARCHIVE="${DIST_DIR}/${ARCHIVE_NAME}"

mkdir -p "${DIST_DIR}"
rm -f "${TARGET_ARCHIVE}"

echo "==> Empacotando TokenPulse Release (${VERSION})..."

tar -czf "${TARGET_ARCHIVE}" \
    -C "${ROOT_DIR}" \
    --exclude=".git" \
    --exclude=".venv" \
    --exclude="*.venv" \
    --exclude="*.db" \
    --exclude="*.sqlite" \
    --exclude="*.sqlite3" \
    --exclude=".env" \
    --exclude="__pycache__" \
    --exclude=".pytest_cache" \
    --exclude=".scratch" \
    --exclude="dist" \
    backend frontend tests scripts README.md LICENSE 2>/dev/null || \
tar -czf "${TARGET_ARCHIVE}" \
    -C "${ROOT_DIR}" \
    --exclude=".git" \
    --exclude=".venv" \
    --exclude="*.db" \
    --exclude="*.sqlite*" \
    --exclude=".env" \
    --exclude="__pycache__" \
    --exclude=".pytest_cache" \
    --exclude=".scratch" \
    --exclude="dist" \
    backend frontend tests scripts README.md

echo "==> Verificando conformidade do pacote de release..."

# Verify no forbidden paths leaked into the archive
FORBIDDEN_FOUND=$(tar -tzf "${TARGET_ARCHIVE}" | grep -E "(\.git/|\.venv/|\.db$|\.sqlite|\.env$|__pycache__)" || true)

if [ -n "${FORBIDDEN_FOUND}" ]; then
    echo "ERRO DE SEGURANÇA: Arquivos proibidos detectados no pacote gerado:"
    echo "${FORBIDDEN_FOUND}"
    rm -f "${TARGET_ARCHIVE}"
    exit 1
fi

CHECKSUM=$(sha256sum "${TARGET_ARCHIVE}" | awk '{print $1}')
echo "✅ Pacote de release gerado com sucesso:"
echo "   Arquivo: ${TARGET_ARCHIVE}"
echo "   SHA256:  ${CHECKSUM}"
