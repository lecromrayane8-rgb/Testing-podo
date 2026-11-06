@echo off
cd /d "%~dp0.."
if not exist .env copy .env.example .env >nul
echo Labo court terme : 32 variantes, 17 combinaisons (filtres) et 4 impulsions, en bougies
echo de 1, 5 et 15 minutes, sur BTC, ETH, SOL, les 8 cryptos les plus agitees et les memecoins assez echanges.
echo Compter environ 1 heure (moins la fois suivante : les donnees sont gardees en cache).
echo La colonne "Avant frais" montre ce que chaque strategie capte sur le prix, avant frais.
echo.
tradingbot\tradingbot.exe labo --symbols "BTC/USDT,ETH/USDT,SOL/USDT" --timeframes "1m,5m,15m" --scanner 8 --memecoins --combinaisons --resultats laboratoire-court-terme.json
echo.
pause
