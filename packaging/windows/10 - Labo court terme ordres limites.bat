@echo off
cd /d "%~dp0"
if not exist .env copy .env.example .env >nul
echo Le meme labo court terme que le 7, mais avec des ordres limites : le bot attend son prix au lieu
echo de payer l'ecart et le glissement. Ses resultats remplacent ceux du 7 pour le tournoi 8.
echo Compter environ 1 heure.
echo.
tradingbot\tradingbot.exe labo --symbols "BTC/USDT,ETH/USDT,SOL/USDT" --timeframes "1m,5m,15m" --scanner 8 --memecoins --combinaisons --resultats laboratoire-court-terme.json --ordres-limites
echo.
pause
