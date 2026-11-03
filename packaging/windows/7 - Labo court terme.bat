@echo off
cd /d "%~dp0"
if not exist .env copy .env.example .env >nul
echo Labo court terme : les 24 variantes en bougies de 1 et 5 minutes, sur BTC, ETH, SOL,
echo les 8 cryptos les plus agitees du moment et les memecoins assez echanges sur Binance.
echo 60 jours d'historique en 1 min, 300 jours en 5 min. Compter 20 a 40 minutes.
echo Il dit si le tres court terme gagne encore une fois les frais payes.
echo.
tradingbot\tradingbot.exe labo --symbols "BTC/USDT,ETH/USDT,SOL/USDT" --timeframes "1m,5m" --scanner 8 --memecoins
echo.
pause
