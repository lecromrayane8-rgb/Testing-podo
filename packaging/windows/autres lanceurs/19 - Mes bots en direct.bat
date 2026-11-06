@echo off
cd /d "%~dp0.."
if not exist .env copy .env.example .env >nul
echo Tes bots en ARGENT FICTIF, en continu : ils suivent les cryptos qui bougent le plus (relues toutes
echo les 10 minutes), retestent toutes leurs strategies sur chacune toutes les 3 heures, et lancent un bot
echo pour chaque combinaison gagnante (des centaines au plus). Une crypto trop calme passe en veille.
echo Le site les montre en direct (ecran Direct). Fermer cette fenetre les arrete ; ils reprennent la ou
echo ils en etaient. Reglages (nombre de cryptos, de bots, leviers) : site, Plus, Reglages.
echo.
tradingbot\tradingbot.exe flotte
echo.
pause
