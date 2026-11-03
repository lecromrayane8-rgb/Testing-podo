@echo off
cd /d "%~dp0"
if not exist .env copy .env.example .env >nul
echo Tournoi long terme en ARGENT FICTIF : les strategies "a surveiller" du labo (6), chacune dans
echo son unite de temps (4 h, 1 jour...), sur les marches du labo, les cryptos agitees et les memecoins.
echo Plus il y a de cryptos, plus les trades arrivent vite. Fermer cette fenetre arrete le tournoi.
echo.
tradingbot\tradingbot.exe tournoi --avec-marches-du-labo
echo.
pause
