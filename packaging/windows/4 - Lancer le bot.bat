@echo off
cd /d "%~dp0"
if not exist .env copy .env.example .env >nul
echo Le bot tourne selon le MODE choisi dans les reglages. Fermer cette fenetre l'arrete.
echo.
tradingbot\tradingbot.exe run
echo.
pause
