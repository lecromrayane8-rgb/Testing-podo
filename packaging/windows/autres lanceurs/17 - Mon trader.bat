@echo off
cd /d "%~dp0.."
if not exist .env copy .env.example .env >nul
echo Ton trader en ARGENT FICTIF : il joue les strategies retenues par le labo sur les 20
echo cryptos les plus echangees, avec un stop a chaque trade, et explique chaque achat et vente
echo (le site les montre dans « Accueil »). Fermer cette fenetre l'arrete ; il reprend la ou il en
echo etait. Reglages (levier, risque, capital) : section « Mon trader » des reglages du site.
echo.
tradingbot\tradingbot.exe trader
echo.
pause
