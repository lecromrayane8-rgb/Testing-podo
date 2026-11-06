@echo off
cd /d "%~dp0.."
if not exist .env copy .env.example .env >nul
echo Le choix de tes 15 bots, en ARGENT FICTIF : le bot telecharge l'historique reel des cryptos les
echo plus echangees et les plus agitees, backteste toutes les combinaisons (15 techniques par equipe,
echo a l'achat et a la vente a decouvert, avec ou sans objectif) et garde les 5 meilleures de chaque
echo equipe : long terme, court terme, scalping. Compte 15 a 40 min. Ensuite, lance
echo « 20 - Mes 15 bots » (ou ouvre le site : il les lance tout seul).
echo.
tradingbot\tradingbot.exe flotte --choisir
echo.
pause
