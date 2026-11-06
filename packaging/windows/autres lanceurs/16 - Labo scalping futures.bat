@echo off
cd /d "%~dp0.."
if not exist .env copy .env.example .env >nul
echo Labo scalping avec les frais des contrats a terme (futures) : 0,05 %% par ordre au marche,
echo 0,02 %% en limite, financement toutes les 8 heures. Deux fois moins cher qu'au comptant.
echo Bougies de 1, 5 et 15 minutes. Compter environ 1 heure. Argent fictif seulement.
echo.
tradingbot\tradingbot.exe labo --symbols "BTC/USDT,ETH/USDT,SOL/USDT" --timeframes "1m,5m,15m" --scanner 8 --memecoins --combinaisons --futures --resultats laboratoire-futures.json
echo.
pause
