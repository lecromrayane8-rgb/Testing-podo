@echo off
cd /d "%~dp0"
if not exist .env copy .env.example .env >nul
tradingbot\tradingbot.exe backtest
echo.
pause
