@echo off
cd /d "%~dp0"
if not exist .env copy .env.example .env >nul
echo Labo court terme : 24 variantes + 12 combinaisons (filtres de volatilite et de volume), en bougies
echo de 1 et 5 minutes, sur BTC, ETH, SOL, les 8 cryptos les plus agitees et les memecoins assez echanges.
echo 60 jours d'historique en 1 min, 300 jours en 5 min. Compter 30 a 50 minutes.
echo La colonne "Avant frais" montre ce que chaque strategie capte sur le prix, avant frais.
echo.
tradingbot\tradingbot.exe labo --symbols "BTC/USDT,ETH/USDT,SOL/USDT" --timeframes "1m,5m" --scanner 8 --memecoins --combinaisons --resultats laboratoire-court-terme.json
echo.
pause
