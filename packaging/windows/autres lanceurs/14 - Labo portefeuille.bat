@echo off
cd /d "%~dp0.."
if not exist .env copy .env.example .env >nul
echo Labo portefeuille : une regle issue de la recherche (momentum croise). Chaque semaine, garder
echo les 3 ou 5 cryptos qui ont le plus monte parmi les 30 plus echangees, a parts egales.
echo Teste sur des annees de bougies d'un jour, hors echantillon, frais compris, contre le panier
echo de toutes les cryptos. Compter 2 a 5 minutes. Aucun ordre n'est passe.
echo.
tradingbot\tradingbot.exe labo-portefeuille
echo.
pause
