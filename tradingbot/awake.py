"""Empêche Windows de se mettre en veille tant qu'un bot, un tournoi ou un labo tourne.

Windows prévoit cet appel pour les programmes qui travaillent longtemps (lecteurs vidéo, téléchargements) :
l'écran peut s'éteindre, mais l'ordinateur ne s'endort pas. Rien n'est changé dans les réglages : la mise en
veille normale revient dès que la fenêtre du bot est fermée. Sans effet sur les autres systèmes.
"""
from __future__ import annotations

import ctypes
import sys

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


def keep_awake(kernel32=None) -> bool:
    """True si la mise en veille est suspendue pour ce programme."""
    if kernel32 is None:
        if sys.platform != "win32":
            return False
        kernel32 = ctypes.windll.kernel32
    try:
        return bool(kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED))
    except (AttributeError, OSError):
        return False
