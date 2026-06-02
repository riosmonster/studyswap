#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

# Cria o venv se ainda não existir
if [ ! -d ".venv" ]; then
  echo "Criando ambiente virtual..."
  python3 -m venv .venv
fi

# Instala/atualiza dependências
.venv/bin/pip install -q -r requirements.txt

echo "StudySwap iniciando em http://localhost:5000"

# Abre o browser após 1 segundo
(sleep 1 && open http://localhost:5000 2>/dev/null || xdg-open http://localhost:5000 2>/dev/null || true) &

.venv/bin/python app.py
