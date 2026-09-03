#!/usr/bin/env bash
# ==============================================================================
# Script de Inicialização Automática — AI Usage Dashboard
# ==============================================================================

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR/backend" || exit 1

# 1. Cria virtualenv se não existir
if [ ! -d ".venv" ]; then
    echo "📦 Criando ambiente virtual Python (.venv)..."
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt
fi

# 2. Inicia o servidor FastAPI
echo "🚀 Iniciando AI Usage Dashboard em http://localhost:8000 ..."
exec .venv/bin/python main.py
