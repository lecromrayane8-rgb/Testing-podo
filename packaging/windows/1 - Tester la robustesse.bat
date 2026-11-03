@echo off
cd /d "%~dp0"
if not exist .env copy .env.example .env >nul
echo Test de robustesse : 2 ans de donnees sur 15 marches, compter 5 a 10 minutes.
echo.
tradingbot\tradingbot.exe robustesse
echo.
pause
