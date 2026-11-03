@echo off
cd /d "%~dp0"
if not exist .env copy .env.example .env >nul
echo Tournoi en ARGENT FICTIF, bougies d'1 minute : les strategies "a surveiller" du dernier labo,
echo sur les cryptos les plus agitees du moment et les memecoins assez echanges sur Binance.
echo Chaque bot a 1000 USDT fictifs. Une strategie qui perd nettement est eliminee toute seule.
echo Le tableau de bord s'ouvre dans ton navigateur. Fermer cette fenetre arrete le tournoi.
echo.
tradingbot\tradingbot.exe tournoi --unite 1m
echo.
pause
