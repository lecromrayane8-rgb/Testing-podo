@echo off
cd /d "%~dp0"
if not exist .env copy .env.example .env >nul
title Bot de trading (iPad et telephone)
echo Le meme site, ouvert aussi aux appareils du Wi-Fi de la maison (iPad, telephone).
echo Sur l'iPad, tape l'adresse affichee ci-dessous, avec son code. Si Windows demande l'autorisation
echo du pare-feu, accepte pour les reseaux PRIVES seulement. A n'utiliser que sur ton Wi-Fi de maison.
echo Garde cette fenetre ouverte : la fermer arrete le site et tout ce qu'il a lance.
echo.
tradingbot\tradingbot.exe site --ipad
echo.
pause
