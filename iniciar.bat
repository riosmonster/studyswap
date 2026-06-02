@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv" (
    echo Criando ambiente virtual...
    python -m venv .venv
)

echo Instalando dependencias...
.venv\Scripts\pip install -q -r requirements.txt

echo StudySwap iniciando em http://localhost:5000
start "" http://localhost:5000
.venv\Scripts\python app.py
