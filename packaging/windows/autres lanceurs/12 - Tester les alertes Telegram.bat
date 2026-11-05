@echo off
cd /d "%~dp0.."
if not exist .env copy .env.example .env >nul
echo Alertes Telegram : verifie le lien entre le bot et ton telephone (voir les etapes dans les reglages).
echo.
tradingbot\tradingbot.exe telegram
echo.
pause
