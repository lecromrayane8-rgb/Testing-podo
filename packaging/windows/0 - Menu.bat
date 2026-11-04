@echo off
cd /d "%~dp0"
if not exist .env copy .env.example .env >nul
:menu
cls
echo ==========================================================================
echo   BOT DE TRADING - MENU          (argent fictif tant que tu ne changes rien)
echo ==========================================================================
echo.
echo   VOIR
echo     1  Prix en direct : Binance, OKX, Kraken, Coinbase, Bybit cote a cote
echo     2  Tableau de bord : tes bots, tes tournois, le labo
echo.
echo   CHERCHER UNE STRATEGIE (sur l'historique reel)
echo     3  Labo court terme : 1, 5 et 15 min, avec les combinaisons (environ 1 h)
echo     4  Labo court terme en ordres limites, pour moins de frais (environ 1 h)
echo     5  Labo long terme : 15 min a 1 jour, cryptos, or, euro (10 a 20 min)
echo     6  Test de robustesse de la strategie choisie dans les reglages
echo     7  Backtest detaille de la strategie choisie
echo.
echo   FAIRE TOURNER EN ARGENT FICTIF (prix reels)
echo     8  Tournoi court terme : les strategies retenues par le labo court terme
echo     9  Tournoi long terme : les strategies retenues par le labo long terme
echo    10  Mes bots : ceux definis dans les reglages (BOTS)
echo.
echo   REGLAGES
echo    11  Verifier la connexion a la plateforme
echo    12  Modifier les reglages (fichier .env)
echo.
echo     0  Quitter
echo.
echo   Pour arreter une action en cours : Ctrl+C, puis N pour revenir ici.
echo.
set "choix="
set /p "choix=Ton choix, puis Entree : "
if "%choix%"=="1" goto choix1
if "%choix%"=="2" goto choix2
if "%choix%"=="3" goto choix3
if "%choix%"=="4" goto choix4
if "%choix%"=="5" goto choix5
if "%choix%"=="6" goto choix6
if "%choix%"=="7" goto choix7
if "%choix%"=="8" goto choix8
if "%choix%"=="9" goto choix9
if "%choix%"=="10" goto choix10
if "%choix%"=="11" goto choix11
if "%choix%"=="12" goto choix12
if "%choix%"=="0" exit /b
goto menu
:choix1
call "11 - Prix en direct.bat"
goto menu
:choix2
call "5 - Tableau de bord.bat"
goto menu
:choix3
call "7 - Labo court terme.bat"
goto menu
:choix4
call "10 - Labo court terme ordres limites.bat"
goto menu
:choix5
call "6 - Laboratoire de strategies.bat"
goto menu
:choix6
call "1 - Tester la robustesse.bat"
goto menu
:choix7
call "2 - Backtest.bat"
goto menu
:choix8
call "8 - Tournoi court terme.bat"
goto menu
:choix9
call "9 - Tournoi long terme.bat"
goto menu
:choix10
call "4 - Lancer le bot.bat"
goto menu
:choix11
call "3 - Verifier la connexion.bat"
goto menu
:choix12
call "Modifier les reglages.bat"
goto menu
