@echo off
cd /d "%~dp0.."
if not exist .env copy .env.example .env >nul
echo Les regles de ton trader rejouees sur les derniers mois : des exemples de trades expliques
echo tout de suite. Flatteur par nature (les strategies ont ete choisies sur ce passe) : ce n'est
echo pas une preuve. Compter 1 a 5 minutes.
echo.
tradingbot\tradingbot.exe trader --rejouer
echo.
pause
