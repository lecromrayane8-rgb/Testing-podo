import shlex
from pathlib import Path

from tradingbot.webapp import ACTIONS, steps_for

WINDOWS = Path(__file__).resolve().parent.parent / "packaging" / "windows"
OTHERS = WINDOWS / "autres lanceurs"


def commands(name: str) -> list[tuple[str, ...]]:
    """Les commandes du bot qu'un lanceur .bat exécute (sans le nom du programme)."""
    lines = (OTHERS / name).read_text(encoding="utf-8").splitlines()
    return [tuple(shlex.split(line.strip())[1:]) for line in lines if line.strip().startswith("tradingbot\\")]


def test_every_launcher_keeps_windows_line_endings():
    launchers = sorted(WINDOWS.rglob("*.bat"))
    assert len(launchers) == 23
    for bat in launchers:
        data = bat.read_bytes()
        assert data.count(b"\n") == data.count(b"\r\n") > 0, bat.name


def test_the_site_runs_exactly_the_commands_of_the_launchers(tmp_path):
    assert commands("19 - Mes bots en direct.bat") == steps_for("flotte", tmp_path)
    assert commands("3 - Verifier la connexion.bat") == steps_for("check", tmp_path)
    assert commands("12 - Tester les alertes Telegram.bat") == steps_for("telegram", tmp_path)
    assert set(ACTIONS) == {"flotte", "check", "telegram"}


def test_the_instructions_for_claude_on_the_pc_give_the_commands_of_the_launchers(tmp_path):
    text = (WINDOWS / "CLAUDE.md").read_text(encoding="utf-8")
    launched = {c for bat in OTHERS.glob("*.bat") for c in commands(bat.name)}
    shown = {}
    for line in text.splitlines():
        if line.startswith("| ") and "`tradingbot\\tradingbot.exe" in line:
            label, command = line.split("|")[1].strip(), line.split("`")[1]
            shown[label] = tuple(shlex.split(command)[1:])
    assert shown["les bots en direct (argent fictif)"] == steps_for("flotte", tmp_path)[0]
    assert all(command in launched for command in shown.values()), set(shown.values()) - launched
    assert "CONFIRM_LIVE_TRADING" in text and "Ne promets jamais de gains" in text and "15 bots" not in text


def test_the_main_launchers_open_the_site_and_the_others_start_from_the_bot_folder():
    assert "tradingbot\\tradingbot.exe site\r\n" in (WINDOWS / "Ouvrir le bot.bat").read_text(encoding="utf-8", newline="")
    assert "tradingbot.exe site --ipad" in (WINDOWS / "Ouvrir le bot sur iPad ou telephone.bat").read_text(encoding="utf-8")
    for bat in OTHERS.glob("*.bat"):
        assert 'cd /d "%~dp0.."' in bat.read_text(encoding="utf-8"), bat.name  # .env et data sont un dossier plus haut
        assert "--choisir" not in bat.read_text(encoding="utf-8"), bat.name
    calls = [line for line in (OTHERS / "0 - Menu.bat").read_text(encoding="utf-8").splitlines() if line.startswith("call")]
    assert len(calls) == 20 and all(line.startswith('call "%~dp0') for line in calls)
    for line in calls:
        assert (OTHERS / line.removeprefix('call "%~dp0').rstrip('"')).exists(), line
    menu = (OTHERS / "0 - Menu.bat").read_text(encoding="utf-8")
    assert "15 bots" not in menu and "Mes bots en direct" in menu
