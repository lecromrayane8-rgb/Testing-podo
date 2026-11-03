@echo off
cd /d "%~dp0"
if not exist .env copy .env.example .env >nul
echo Tournoi en ARGENT FICTIF : les strategies "a surveiller" du labo court terme (7 ou 10), chacune dans
echo l'unite de temps ou le labo l'a trouvee, avec les memes ordres et les memes frais que dans le labo.
echo Chaque bot a 1000 USDT fictifs. Une strategie qui perd nettement est eliminee toute seule.
echo Le tableau de bord s'ouvre dans ton navigateur. Fermer cette fenetre arrete le tournoi.
echo.
tradingbot\tradingbot.exe tournoi --labo laboratoire-court-terme.json
echo.
pause
