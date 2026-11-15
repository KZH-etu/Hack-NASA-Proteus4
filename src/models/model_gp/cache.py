"""Modèles entraînés sauvegardés sur disque (data/models/) : rechargés en ~0,1 s au lieu de ~45 s d'entraînement.

Un fichier n'est rechargé que s'il a été produit avec les mêmes données, le même code et la même version de
scikit-learn (empreinte dans <nom>.key) ; sinon le modèle est réentraîné puis sauvegardé. Si la sauvegarde ou
le chargement échoue, on retombe sur l'entraînement : le cache ne fait que gagner du temps.
joblib, comme pickle, exécute du code au chargement : ne charger que des fichiers produits par ce module.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import joblib
import sklearn

LOGGER = logging.getLogger("hephaistos.models")
ROOT = Path(__file__).resolve().parents[3]
CACHE_DIR = ROOT / "data" / "models"
# Tout ce dont dépend l'entraînement : code des modèles, préparation des données, tables d'essais.
SOURCES = ("src/models/model_gp/**/*.py", "src/data/*.py", "src/common/*.py", "data/processed/families/*.parquet")


def fingerprint(root=ROOT, sources=SOURCES):
    """Empreinte des sources et de la version de scikit-learn (fins de ligne normalisées : Windows = Linux)."""
    h = hashlib.sha256(f"scikit-learn {sklearn.__version__}\n".encode())
    for path in sorted({p for pattern in sources for p in Path(root).glob(pattern) if "__pycache__" not in p.parts}):
        data = path.read_bytes()
        if path.suffix == ".py":
            data = data.replace(b"\r\n", b"\n")
        h.update(path.relative_to(root).as_posix().encode() + b"\0" + data)
    return h.hexdigest()


def load_or_train(name, train, cache_dir=CACHE_DIR, key=None):
    """Modèle `name` rechargé depuis cache_dir si son empreinte est à jour, sinon train() puis sauvegarde."""
    key = key or fingerprint()
    model_path, key_path = Path(cache_dir) / f"{name}.joblib", Path(cache_dir) / f"{name}.key"
    try:
        if key_path.read_text(encoding="utf-8").strip() == key:
            model = joblib.load(model_path)
            LOGGER.info("Modèle %s rechargé depuis %s", name, model_path)
            return model
    except FileNotFoundError:
        pass
    except Exception:  # noqa: BLE001 - fichier abîmé ou illisible : on réentraîne
        LOGGER.warning("Modèle %s illisible dans %s : réentraînement", name, model_path, exc_info=True)

    model = train()
    try:
        model_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = model_path.with_suffix(".tmp")
        joblib.dump(model, tmp, compress=3)
        tmp.replace(model_path)
        key_path.write_text(key, encoding="utf-8")  # écrit après le modèle : jamais de clé sans son fichier
    except OSError:
        LOGGER.warning("Sauvegarde du modèle %s impossible : il sera réentraîné au prochain lancement", name,
                       exc_info=True)
    return model
