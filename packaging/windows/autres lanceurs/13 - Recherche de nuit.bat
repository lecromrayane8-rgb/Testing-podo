@echo off
cd /d "%~dp0.."
if not exist .env copy .env.example .env >nul
echo Recherche de nuit : le labo portefeuille, le labo court terme, le meme en ordres limites,
echo le scalping avec les frais des futures, puis le labo long terme.
echo Compter 2 a 4 heures selon le PC. L'ordinateur ne se met pas en veille tant que ca tourne.
echo A la fin, le tableau de bord s'ouvre ; avec les alertes Telegram, chaque verdict arrive aussi
echo sur ton telephone. Fermer cette fenetre arrete la recherche.
echo.
tradingbot\tradingbot.exe labo-portefeuille
tradingbot\tradingbot.exe labo --symbols "BTC/USDT,ETH/USDT,SOL/USDT" --timeframes "1m,5m,15m" --scanner 8 --memecoins --combinaisons --resultats laboratoire-court-terme.json
tradingbot\tradingbot.exe labo --symbols "BTC/USDT,ETH/USDT,SOL/USDT" --timeframes "1m,5m,15m" --scanner 8 --memecoins --combinaisons --ordres-limites --resultats laboratoire-court-terme-limites.json
tradingbot\tradingbot.exe labo --symbols "BTC/USDT,ETH/USDT,SOL/USDT" --timeframes "1m,5m,15m" --scanner 8 --memecoins --combinaisons --futures --resultats laboratoire-futures.json
tradingbot\tradingbot.exe labo
tradingbot\tradingbot.exe tableau
echo.
pause
