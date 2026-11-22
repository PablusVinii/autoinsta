@echo off
title Bot Resumo Reels - Instagram para Telegram
cd /d "%~dp0"

echo ========================================================
echo   Iniciando Bot de Resumo de Reels (Instagram -> Telegram)
echo ========================================================

IF NOT EXIST ".env" (
    echo [AVISO] Arquivo .env nao encontrado!
    echo Copiando .env.example para .env...
    copy .env.example .env
    echo Por favor, edite o arquivo .env com seu TELEGRAM_BOT_TOKEN e GEMINI_API_KEY.
    notepad .env
    pause
    exit /b
)

IF NOT EXIST "venv" (
    echo Criando ambiente virtual venv...
    python -m venv venv
)

echo Ativando ambiente virtual e verificando dependencias...
call venv\Scripts\activate.bat
pip install -r requirements.txt

echo Iniciando o bot...
python bot.py
pause
