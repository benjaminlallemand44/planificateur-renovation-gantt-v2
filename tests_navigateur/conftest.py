"""Tests de bout en bout dans un vrai navigateur (Playwright + Chromium).

Ils couvrent ce que le banc de test de Streamlit ne sait pas piloter, notamment les tableaux modifiables.
Lancement : ``pytest tests_navigateur`` (nécessite ``playwright install chromium`` ou la variable
d'environnement CHROMIUM_PATH vers un Chromium déjà installé).
"""

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

RACINE = Path(__file__).resolve().parents[1]


def _port_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def url_app():
    port = _port_libre()
    processus = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(RACINE / "app.py"),
            "--server.headless=true",
            f"--server.port={port}",
            "--browser.gatherUsageStats=false",
        ],
        cwd=RACINE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    for _ in range(60):
        try:
            urllib.request.urlopen(f"{url}/_stcore/health", timeout=1)
            break
        except OSError:
            time.sleep(0.5)
    else:
        processus.terminate()
        pytest.fail("L'application Streamlit n'a pas démarré.")
    yield url
    processus.terminate()
    processus.wait(timeout=10)


@pytest.fixture(scope="session")
def navigateur():
    with sync_playwright() as p:
        options = {"executable_path": os.environ["CHROMIUM_PATH"]} if os.environ.get("CHROMIUM_PATH") else {}
        navigateur = p.chromium.launch(**options)
        yield navigateur
        navigateur.close()


@pytest.fixture
def page(navigateur, url_app):
    contexte = navigateur.new_context(viewport={"width": 1500, "height": 1200}, locale="fr-FR", accept_downloads=True)
    page = contexte.new_page()
    page.goto(url_app)
    page.wait_for_selector('[data-testid="stSelectbox"]', timeout=30_000)
    yield page
    contexte.close()
