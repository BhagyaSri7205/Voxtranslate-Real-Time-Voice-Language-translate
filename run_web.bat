@echo off
cd /d "%~dp0"
if not exist venv (
    python -m venv venv
    call venv\Scripts\activate
    python -m pip install --upgrade pip
    pip install -r requirements-web.txt
) else (
    call venv\Scripts\activate
)
if not exist .env if exist .env.example copy .env.example .env >nul
start "" http://127.0.0.1:5000
python web\server.py
pause
