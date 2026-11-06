@echo off
cd /d "%~dp0.."
if not exist .env copy .env.example .env >nul
echo Tes 15 bots en ARGENT FICTIF : chacun sur sa crypto, avec tout son capital et le levier de son
echo equipe, un stop et souvent un objectif. Le site les montre en direct (ecran « Direct »).
echo La premiere fois, ils sont d'abord choisis par backtest (15 a 40 min). Fermer cette fenetre
echo les arrete ; ils reprennent la ou ils en etaient. Reglages (capital, leviers) : site, Reglages.
echo.
tradingbot\tradingbot.exe flotte
echo.
pause
