@echo off
cd /d "%~dp0"
if not exist .env copy .env.example .env >nul
title Bot de trading
echo Le site du bot s'ouvre dans ton navigateur. Garde cette fenetre ouverte (tu peux la reduire) :
echo la fermer arrete le site et tout ce qu'il a lance (labos, tournois, bots).
echo.
tradingbot\tradingbot.exe site
echo.
pause
