@echo off
cd /d "%~dp0"
if not exist .env copy .env.example .env >nul
echo Laboratoire : 7 strategies x 4 unites de temps sur 7 marches (cryptos, or, euro).
echo Compter 5 a 15 minutes. Les fichiers CSV du dossier actions sont ajoutes en 1 jour.
echo.
if exist "actions\*.csv" (
  tradingbot\tradingbot.exe labo --csv-dir actions
) else (
  tradingbot\tradingbot.exe labo
)
echo.
pause
