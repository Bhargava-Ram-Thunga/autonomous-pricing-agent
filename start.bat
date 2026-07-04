@echo off
:: Pricing Agent — auto-restart loop
:: Use this if PM2 is not installed
:: Double-click to start, close window to stop

title Pricing Agent
cd /d "C:\Users\Vasanth\Desktop\Pricing Agent LG"

:loop
echo [%date% %time%] Starting Pricing Agent...
call .venv\Scripts\activate.bat
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --no-access-log
echo [%date% %time%] Agent stopped (exit code %errorlevel%). Restarting in 5s...
timeout /t 5 /nobreak >nul
goto loop
