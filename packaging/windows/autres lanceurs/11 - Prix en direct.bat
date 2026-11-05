@echo off
cd /d "%~dp0.."
if not exist .env copy .env.example .env >nul
echo Prix en direct : les vrais prix de Binance, OKX, Kraken, Coinbase et Bybit cote a cote, mis a jour
echo toutes les 10 secondes, et les cryptos les plus agitees du moment. Aucun compte necessaire.
echo Fermer cette fenetre (ou Ctrl+C) l'arrete.
echo.
tradingbot\tradingbot.exe prix
echo.
pause
