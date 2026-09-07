#!/usr/bin/env bash
# ==============================================================================
# TokenPulse — Servidor Web Local
# ==============================================================================

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR/backend" || exit 1

# 1. Configura ambiente virtual Python se necessário
if [ ! -d ".venv" ]; then
    echo "📦 Configurando ambiente do servidor web..."
    python3 -m venv .venv
    .venv/bin/pip install -q -r requirements.txt
fi

# 2. Exibe URLs de acesso web
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "⚡ TokenPulse Web Server Online"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🌐 Site / Landing Page:   http://localhost:8000"
echo "📊 Painel / Dashboard:    http://localhost:8000/dashboard"
echo "🔑 Acesso / Login:        http://localhost:8000/login.html"
echo "⚡ Status da API:         http://localhost:8000/api/ping"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Pressione Ctrl+C para encerrar o servidor."
echo ""

# 3. Inicia o servidor FastAPI / Uvicorn
exec .venv/bin/python main.py
