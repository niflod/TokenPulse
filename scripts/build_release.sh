#!/usr/bin/env bash
set -euo pipefail

# scripts/build_release.sh — Secure release packaging for TokenPulse
# Packages clean artifacts (.zip and .tar.gz) excluding sensitive local data (.git, .venv, *.db, .env, caches)

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="${ROOT_DIR}/dist"
VERSION="$(git -C "${ROOT_DIR}" describe --tags --always 2>/dev/null || echo "v1.0.0")"
TAR_ARCHIVE="${DIST_DIR}/tokenpulse-${VERSION}.tar.gz"
ZIP_ARCHIVE="${DIST_DIR}/tokenpulse-${VERSION}.zip"
LEGACY_ZIP="${ROOT_DIR}/../TokenPulse-v1.zip"

mkdir -p "${DIST_DIR}"
rm -f "${TAR_ARCHIVE}" "${ZIP_ARCHIVE}"

STAGE_DIR="$(mktemp -d /tmp/tokenpulse_release_XXXXXX)"
trap 'rm -rf "${STAGE_DIR}"' EXIT

echo "==> Preparando staging de release limpo (${VERSION})..."
mkdir -p "${STAGE_DIR}/tokenpulse"

# Copy project files using rsync or tar excluding all sensitive patterns
tar -cf - \
    -C "${ROOT_DIR}" \
    --exclude=".git" \
    --exclude=".git/*" \
    --exclude=".venv" \
    --exclude="*.venv*" \
    --exclude="backend/.venv" \
    --exclude="backend/data/*.db*" \
    --exclude="*.db" \
    --exclude="*.sqlite*" \
    --exclude=".env" \
    --exclude="backend/.env" \
    --exclude="__pycache__" \
    --exclude="*.pytest_cache*" \
    --exclude=".scratch" \
    --exclude="dist" \
    backend frontend tests scripts README.md LICENSE docker-compose.yml Dockerfile .dockerignore 2>/dev/null | \
tar -xf - -C "${STAGE_DIR}/tokenpulse" 2>/dev/null || \
tar -cf - \
    -C "${ROOT_DIR}" \
    --exclude=".git" \
    --exclude=".git/*" \
    --exclude=".venv" \
    --exclude="*.venv*" \
    --exclude="backend/.venv" \
    --exclude="backend/data/*.db*" \
    --exclude="*.db" \
    --exclude="*.sqlite*" \
    --exclude=".env" \
    --exclude="backend/.env" \
    --exclude="__pycache__" \
    --exclude="*.pytest_cache*" \
    --exclude=".scratch" \
    --exclude="dist" \
    backend frontend tests scripts README.md | \
tar -xf - -C "${STAGE_DIR}/tokenpulse"

# Double check that no rogue db, .env or pycache entered the stage
find "${STAGE_DIR}" -type f -name "*.db" -delete
find "${STAGE_DIR}" -type f -name "*.sqlite*" -delete
find "${STAGE_DIR}" -type f -name ".env" -delete
find "${STAGE_DIR}" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "${STAGE_DIR}" -type d -name ".venv" -exec rm -rf {} + 2>/dev/null || true

echo "==> Gerando ${TAR_ARCHIVE}..."
tar -czf "${TAR_ARCHIVE}" -C "${STAGE_DIR}" tokenpulse

echo "==> Gerando ${ZIP_ARCHIVE}..."
(cd "${STAGE_DIR}" && zip -rq "${ZIP_ARCHIVE}" tokenpulse)

# Also update legacy/parent zip location if present
if [ -f "${LEGACY_ZIP}" ] || [ -d "$(dirname "${LEGACY_ZIP}")" ]; then
    cp -f "${ZIP_ARCHIVE}" "${LEGACY_ZIP}"
    echo "==> Sincronizado pacote limpo em: ${LEGACY_ZIP}"
fi

echo "==> Verificando conformidade estrita dos pacotes..."

# 1. Verify tar.gz
FORBIDDEN_TAR=$(tar -tzf "${TAR_ARCHIVE}" | grep -E "(\.git/|\.venv/|\.db$|\.sqlite|\.env$|__pycache__)" || true)
if [ -n "${FORBIDDEN_TAR}" ]; then
    echo "ERRO CRÍTICO DE SEGURANÇA: Arquivos proibidos no TAR:"
    echo "${FORBIDDEN_TAR}"
    rm -f "${TAR_ARCHIVE}" "${ZIP_ARCHIVE}"
    exit 1
fi

# 2. Verify zip
FORBIDDEN_ZIP=$(unzip -l "${ZIP_ARCHIVE}" | grep -E "(\.git/|\.venv/|\.db$|\.sqlite|\.env$|__pycache__)" || true)
if [ -n "${FORBIDDEN_ZIP}" ]; then
    echo "ERRO CRÍTICO DE SEGURANÇA: Arquivos proibidos no ZIP:"
    echo "${FORBIDDEN_ZIP}"
    rm -f "${TAR_ARCHIVE}" "${ZIP_ARCHIVE}"
    exit 1
fi

TOTAL_FILES=$(unzip -l "${ZIP_ARCHIVE}" | tail -n 1 | awk '{print $2}')
ZIP_CHECKSUM=$(sha256sum "${ZIP_ARCHIVE}" | awk '{print $1}')
TAR_CHECKSUM=$(sha256sum "${TAR_ARCHIVE}" | awk '{print $1}')

echo "================================================================"
echo "✅ PACOTES DE RELEASE GERADOS COM SUCESSO (0 ARQUIVOS PROIBIDOS)"
echo "================================================================"
echo "Total de arquivos no pacote: ${TOTAL_FILES} (esperado: ~100 limpos)"
echo "ZIP:    ${ZIP_ARCHIVE} (SHA256: ${ZIP_CHECKSUM})"
echo "TAR.GZ: ${TAR_ARCHIVE} (SHA256: ${TAR_CHECKSUM})"
