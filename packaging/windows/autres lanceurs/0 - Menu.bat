@echo off
cd /d "%~dp0.."
if not exist .env copy .env.example .env >nul
:menu
cls
echo ==========================================================================
echo   BOT DE TRADING - MENU          (argent fictif tant que tu ne changes rien)
echo ==========================================================================
echo   Le plus simple : ferme ce menu et ouvre "Ouvrir le bot" (le site du bot).
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
echo    15  Labo portefeuille : la regle de la recherche (momentum croise), 2 a 5 min
echo    17  Labo scalping avec les frais des futures (environ 1 h)
echo    14  Recherche de nuit : les 5 labos a la suite, puis le tableau de bord (2 a 4 h)
echo.
echo   FAIRE TOURNER EN ARGENT FICTIF (prix reels)
echo    18  Mon trader : les strategies du labo sur 20 cryptos, chaque trade explique
echo    19  Rejouer mon trader sur l'historique (exemples de trades expliques)
echo     8  Tournoi court terme : les strategies retenues par le labo court terme
echo     9  Tournoi long terme : les strategies retenues par le labo long terme
echo    16  Portefeuille momentum : les variantes retenues par le labo portefeuille
echo    10  Mes bots : ceux definis dans les reglages (BOTS)
echo.
echo   REGLAGES
echo    11  Verifier la connexion a la plateforme
echo    12  Modifier les reglages (fichier .env)
echo    13  Alertes Telegram sur ton telephone : verifier le lien
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
if "%choix%"=="13" goto choix13
if "%choix%"=="14" goto choix14
if "%choix%"=="15" goto choix15
if "%choix%"=="16" goto choix16
if "%choix%"=="17" goto choix17
if "%choix%"=="18" goto choix18
if "%choix%"=="19" goto choix19
if "%choix%"=="0" exit /b
goto menu
:choix1
call "%~dp011 - Prix en direct.bat"
goto menu
:choix2
call "%~dp05 - Tableau de bord.bat"
goto menu
:choix3
call "%~dp07 - Labo court terme.bat"
goto menu
:choix4
call "%~dp010 - Labo court terme ordres limites.bat"
goto menu
:choix5
call "%~dp06 - Laboratoire de strategies.bat"
goto menu
:choix6
call "%~dp01 - Tester la robustesse.bat"
goto menu
:choix7
call "%~dp02 - Backtest.bat"
goto menu
:choix8
call "%~dp08 - Tournoi court terme.bat"
goto menu
:choix9
call "%~dp09 - Tournoi long terme.bat"
goto menu
:choix10
call "%~dp04 - Lancer le bot.bat"
goto menu
:choix11
call "%~dp03 - Verifier la connexion.bat"
goto menu
:choix12
call "%~dp0Modifier les reglages.bat"
goto menu
:choix13
call "%~dp012 - Tester les alertes Telegram.bat"
goto menu
:choix14
call "%~dp013 - Recherche de nuit.bat"
goto menu
:choix15
call "%~dp014 - Labo portefeuille.bat"
goto menu
:choix16
call "%~dp015 - Portefeuille momentum.bat"
goto menu
:choix17
call "%~dp016 - Labo scalping futures.bat"
goto menu
:choix18
call "%~dp017 - Mon trader.bat"
goto menu
:choix19
call "%~dp018 - Rejouer mon trader.bat"
goto menu
