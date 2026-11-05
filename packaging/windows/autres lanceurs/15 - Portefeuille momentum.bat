@echo off
cd /d "%~dp0.."
if not exist .env copy .env.example .env >nul
echo Portefeuille momentum en ARGENT FICTIF : les variantes retenues par le labo portefeuille,
echo 1000 USDT fictifs chacune, une rotation par semaine aux prix reels, frais compris.
echo Si le labo n'a rien retenu, rien ne demarre (c'est voulu). Fermer cette fenetre l'arrete ;
echo il reprend ou il en etait au prochain lancement.
echo.
tradingbot\tradingbot.exe portefeuille
echo.
pause
