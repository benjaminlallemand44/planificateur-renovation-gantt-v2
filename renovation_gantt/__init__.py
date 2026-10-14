"""Planificateur de projet de rénovation énergétique (diagramme de Gantt)."""

import hashlib
from pathlib import Path

__version__ = "2.5.1"


def empreinte_sources(dossier: Path = Path(__file__).parent) -> str:
    """Empreinte du code du package, pour détecter une mise à jour pendant que l'application tourne."""
    return hashlib.sha1(b"".join(f.read_bytes() for f in sorted(dossier.glob("*.py")))).hexdigest()


# Empreinte du code effectivement chargé en mémoire.
_empreinte = empreinte_sources()
