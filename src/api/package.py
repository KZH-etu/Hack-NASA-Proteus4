"""Fabrique une archive autonome de HEPHAISTOS, lancée par une seule commande chez le destinataire.

    python -m src.api.package                 # dist/HEPHAISTOS_demo.zip : interface + prédictions
    python -m src.api.package --with-chat     # dist/HEPHAISTOS_chat.zip : + chat (RAG + Gemini)
    python -m src.api.package --with-chat --no-db   # sans la base ChromaDB (téléchargée au 1er lancement, gh requis)

Le destinataire dézippe puis lance lancer.bat (Windows) ou bash lancer.sh (macOS, Linux) : création d'un
environnement Python, installation des dépendances, démarrage, ouverture du navigateur.

Seuls les fichiers suivis par git sont copiés (pas de __pycache__ ni de fichiers locaux). Le fichier .env
(clé Gemini) n'est JAMAIS inclus : le destinataire copie .env.example en .env et y met sa propre clé.
La version avec chat demande aussi, chez le destinataire, LM Studio avec le modèle d'embedding du RAG.
"""

from __future__ import annotations

import argparse
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

PREDICTION_PATHS = [
    "src/__init__.py", "src/common", "src/data", "src/models/__init__.py", "src/models/model_gp", "src/api",
    "app/frontend_hephaistos", "data/processed/families", "data/processed/experiments_all.csv",
]
CHAT_PATHS = ["src/rag/__init__.py", "src/rag/config.py", "src/rag/llm_client.py", "src/rag/server", "src/rag/storage",
              ".env.example"]
EXCLUDED = ("src/api/tests/", "src/api/package.py")
CHROMA_DIR = "data/rag/chroma_db"

REQUIREMENTS = ["fastapi", "uvicorn", "httpx", "python-dotenv", "pydantic", "pandas", "pyarrow", "numpy", "scikit-learn"]
CHAT_REQUIREMENTS = ["chromadb", "openai", "google-genai"]

# ---------- Lanceurs ----------

BAT_HEADER = r"""@echo off
setlocal
cd /d "%~dp0"
if not defined HEPHAISTOS_PORT set HEPHAISTOS_PORT=8000
rem Avertissements de convergence de scikit-learn : attendus pour ces modeles, sans effet
set PYTHONWARNINGS=ignore
set "PY=python"
where py >nul 2>nul && set "PY=py -3"
if not exist ".venv\Scripts\python.exe" (
  echo [1/3] Creation de l'environnement Python...
  %PY% -m venv .venv || goto :erreur
)
echo [2/3] Installation des dependances - la premiere fois, quelques minutes...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt || goto :erreur
"""
BAT_CHAT = r"""if not exist ".env" (
  echo.
  echo ATTENTION : fichier .env absent. Copiez .env.example en .env et renseignez GEMINI_API_KEY pour le chat.
  echo.
)
if not exist "data\rag\chroma_db\chroma.sqlite3" (
  echo [*] Base du chat absente : telechargement depuis GitHub - gh auth login requis...
  ".venv\Scripts\python.exe" -m src.rag.storage.download_chroma_release || echo Base non telechargee : le chat sera indisponible.
)
echo [*] Serveur du chat : port 8001 - LM Studio doit tourner avec le modele d'embedding.
start "HEPHAISTOS - RAG (port 8001)" ".venv\Scripts\python.exe" -m src.rag.server --port 8001 --skip-sync
"""
BAT_FOOTER = r"""echo [3/3] HEPHAISTOS : http://127.0.0.1:%HEPHAISTOS_PORT%/   - Ctrl+C pour arreter
echo       Les modeles se preparent pendant environ 1 minute au demarrage.
if not defined HEPHAISTOS_NO_BROWSER start "" cmd /c "timeout /t 5 >nul & start http://127.0.0.1:%HEPHAISTOS_PORT%/"
".venv\Scripts\python.exe" -m src.api {api_args}--port %HEPHAISTOS_PORT%
goto :eof
:erreur
echo.
echo Echec. Verifiez que Python 3.10 ou plus recent est installe : https://www.python.org/downloads/
pause
"""

SH_HEADER = """#!/usr/bin/env bash
# HEPHAISTOS. Usage : bash lancer.sh
set -e
cd "$(dirname "$0")"
PORT="${HEPHAISTOS_PORT:-8000}"
# Avertissements de convergence de scikit-learn : attendus pour ces modèles, sans effet
export PYTHONWARNINGS=ignore
PY=python3; command -v python3 >/dev/null 2>&1 || PY=python
if [ ! -x .venv/bin/python ]; then
  echo "[1/3] Création de l'environnement Python..."
  "$PY" -m venv .venv
fi
echo "[2/3] Installation des dépendances (la première fois : quelques minutes)..."
.venv/bin/python -m pip install --disable-pip-version-check -q -r requirements.txt
"""
SH_CHAT = """if [ ! -f .env ]; then
  echo; echo "ATTENTION : fichier .env absent. Copiez .env.example en .env et renseignez GEMINI_API_KEY pour le chat."; echo
fi
if [ ! -f data/rag/chroma_db/chroma.sqlite3 ]; then
  echo "[*] Base du chat absente : téléchargement depuis GitHub (gh auth login requis)..."
  .venv/bin/python -m src.rag.storage.download_chroma_release || echo "Base non téléchargée : le chat sera indisponible."
fi
echo "[*] Serveur du chat : port 8001 (LM Studio doit tourner avec le modèle d'embedding)."
.venv/bin/python -m src.rag.server --port 8001 --skip-sync &
RAG_PID=$!
trap 'kill $RAG_PID 2>/dev/null' EXIT
"""
SH_FOOTER = """echo "[3/3] HEPHAISTOS : http://127.0.0.1:$PORT/   (Ctrl+C pour arrêter)"
echo "      Les modèles se préparent pendant environ 1 minute au démarrage."
if [ -z "$HEPHAISTOS_NO_BROWSER" ]; then
  ( sleep 5; (xdg-open "http://127.0.0.1:$PORT/" || open "http://127.0.0.1:$PORT/") >/dev/null 2>&1 ) &
fi
.venv/bin/python -m src.api {api_args}--port "$PORT"
"""

README = """HEPHAISTOS - {title}
{underline}

Prérequis : Python 3.10 ou plus récent (https://www.python.org/downloads/)
et une connexion internet au premier lancement (installation des dépendances).
{chat_prereq}
Lancer
------
- Windows      : double-cliquer sur lancer.bat
- macOS, Linux : ouvrir un terminal dans ce dossier, puis : bash lancer.sh

Le premier lancement crée un environnement Python (.venv) et installe les
dépendances (quelques minutes). Le navigateur s'ouvre ensuite sur
http://127.0.0.1:8000/ (sinon, ouvrir cette adresse à la main).

Au démarrage, les trois modèles (gouttelette, gaz, solide) se préparent pendant
environ une minute : le menu affiche « chargement… » puis « prêt ».

Pour arrêter : Ctrl+C dans la fenêtre du terminal{stop_rag}.

Ce qui fonctionne
-----------------
- Prédiction : gouttelettes (FLEX), flammes gazeuses (ACME CFI-G), solides (BASS / BASS-II),
  avec fourchette d'incertitude, fiabilité, alertes et essais NASA les plus proches.
{chat_line}
En cas de problème
------------------
- « Python introuvable » : installer Python et cocher « Add Python to PATH ».
- Port 8000 déjà utilisé : définir la variable HEPHAISTOS_PORT (ex. 8010) avant de lancer.
- État des modèles{chat_status} : http://127.0.0.1:8000/models/status
- Documentation de l'API : http://127.0.0.1:8000/docs

Données : NASA Physical Sciences Informatics (PSI) et NASA Technical Reports Server (NTRS).
"""
CHAT_PREREQ = """
Pour le chat, en plus :
- un fichier .env : copier .env.example en .env et y mettre sa clé GEMINI_API_KEY
  (ne jamais partager ce fichier) ;
- LM Studio lancé (http://localhost:1234) avec le modèle d'embedding
  text-embedding-qwen3-embedding-0.6b chargé ;
{db_line}
"""


def tracked(path):
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "--", path], capture_output=True, text=True,
                         check=True).stdout
    return [p for p in out.splitlines() if p and not p.startswith(EXCLUDED) and "__pycache__" not in p
            and Path(p).name != ".env"]


def build(with_chat=False, include_db=True, out=None):
    top = "HEPHAISTOS_chat" if with_chat else "HEPHAISTOS_demo"
    out = Path(out) if out else ROOT / "dist" / f"{top}.zip"
    paths = PREDICTION_PATHS + (CHAT_PATHS if with_chat else [])
    missing = [p for p in paths if not tracked(p)]
    if missing:
        raise SystemExit(f"fichiers absents de git : {missing}")
    files = sorted({f for p in paths for f in tracked(p)})

    db_files = []
    chroma = ROOT / CHROMA_DIR
    if with_chat and include_db:
        if (chroma / "chroma.sqlite3").exists():
            db_files = sorted(p for p in chroma.rglob("*") if p.is_file())
        else:
            print(f"Base ChromaDB absente ({CHROMA_DIR}) : elle sera téléchargée au 1er lancement (gh requis). "
                  "Pour l'inclure : python -m src.rag.storage.download_chroma_release, puis relancer.")

    api_args = "" if with_chat else "--no-rag "
    bat = BAT_HEADER + (BAT_CHAT if with_chat else "") + BAT_FOOTER.format(api_args=api_args)
    sh = SH_HEADER + (SH_CHAT if with_chat else "") + SH_FOOTER.format(api_args=api_args)
    requirements = "\n".join(REQUIREMENTS + (CHAT_REQUIREMENTS if with_chat else [])) + "\n"
    if with_chat:
        db_line = ("- la base du chat est incluse (data/rag/chroma_db)." if db_files else
                   "- la base du chat (ChromaDB) est téléchargée au 1er lancement : installer le CLI GitHub (gh)\n"
                   "  et faire « gh auth login » avec un compte qui a accès au dépôt.")
        readme = README.format(
            title="interface, prédictions et chat", underline="=" * 42,
            chat_prereq=CHAT_PREREQ.format(db_line=db_line),
            stop_rag=" (et fermer la fenêtre « HEPHAISTOS - RAG » sous Windows)",
            chat_line="- Chat : questions sur les documents NASA, réponses rédigées par Gemini avec leurs sources.\n",
            chat_status=" et du chat")
    else:
        readme = README.format(
            title="démonstration (interface + prédictions)", underline="=" * 52, chat_prereq="", stop_rag="",
            chat_line="- Le chat n'est pas inclus dans cette version (il demande une clé Gemini, LM Studio et la\n"
                      "  base documentaire) : il affiche un message d'indisponibilité.\n",
            chat_status="")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.unlink(missing_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in files:
            z.write(ROOT / f, f"{top}/{f}")
        for p in db_files:
            z.write(p, f"{top}/{p.relative_to(ROOT).as_posix()}")
        z.writestr(f"{top}/requirements.txt", requirements)
        z.writestr(f"{top}/lancer.bat", bat.replace("\n", "\r\n"))
        info = zipfile.ZipInfo(f"{top}/lancer.sh")
        info.external_attr = 0o100755 << 16  # exécutable sous macOS / Linux
        info.compress_type = zipfile.ZIP_DEFLATED
        z.writestr(info, sh)
        z.writestr(f"{top}/LISEZMOI.txt", readme.replace("\n", "\r\n"))
    n = len(files) + len(db_files) + 4
    print(f"{out} : {n} fichiers, {out.stat().st_size / 1e6:.1f} Mo"
          + (f" (dont la base du chat : {len(db_files)} fichiers)" if db_files else ""))
    if with_chat:
        print("Rappel : le .env (clé Gemini) n'est pas inclus ; le destinataire met sa propre clé.")
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description="Fabrique une archive autonome de HEPHAISTOS.")
    parser.add_argument("--with-chat", action="store_true", help="inclure le chat (RAG + Gemini)")
    parser.add_argument("--no-db", action="store_true", help="avec --with-chat : ne pas inclure la base ChromaDB")
    parser.add_argument("--out", help="chemin du zip (défaut : dist/HEPHAISTOS_demo.zip ou dist/HEPHAISTOS_chat.zip)")
    args = parser.parse_args(argv)
    build(with_chat=args.with_chat, include_db=not args.no_db, out=args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
