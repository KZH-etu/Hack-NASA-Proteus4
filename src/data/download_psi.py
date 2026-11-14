"""Téléchargement des données brutes NASA PSI (Physical Sciences Informatics) dans data/raw/psi/.

Pour chaque investigation de INVESTIGATIONS :
- investigation.json      : métadonnées brutes renvoyées par l'API PSI ;
- files_manifest.csv      : tous les fichiers de l'investigation, téléchargés ou non ;
- experimental_table/     : les CSV « Experimental table », tels quels ;
- documents/              : quelques fichiers utiles (matrices d'essais, calibration), tels quels.
Puis data/raw/psi/psi_index.csv (une ligne par investigation) et data/raw/download_log.csv.

Les fichiers déjà présents ne sont pas retéléchargés. Données PSI sous licence CC0, sans compte.

Usage :
    python -m src.data.download_psi                  # toutes les investigations
    python -m src.data.download_psi PSI-69 PSI-25    # seulement celles-ci
    python -m src.data.download_psi --no-docs        # sans le dossier documents/
"""

import argparse
import csv
import datetime
import json
import re
from pathlib import Path

import requests

API = "https://psi.nasa.gov/geode-py/ws"
ROOT = Path(__file__).resolve().parents[2]
RAW_PSI = ROOT / "data" / "raw" / "psi"
DOWNLOAD_LOG = ROOT / "data" / "raw" / "download_log.csv"

# psi_id -> (nom du dossier, famille physique, noms exacts des fichiers « documents » à récupérer)
INVESTIGATIONS = {
    "PSI-69": ("FLEX", "droplet", []),
    "PSI-39": ("CFI", "droplet", []),
    "PSI-159": ("ACME_CFI-G", "gas", []),
    "PSI-10": ("ACME_Flame_Design", "gas", []),
    "PSI-107": ("SPICE", "gas", []),
    "PSI-26": ("BASS", "solid", ["PSI-26_Science Documents_As Run_Test Matrix.xlsx",
                                  "PSI-26_Science Documents_Planned_Test Matrix.xlsx"]),
    "PSI-25": ("BASS-II", "solid", ["PSI-25_Science Documents_BASS-II_Test.Matrices.xlsx",
                                     "PSI-25_Reference Data_Fan calibration data.xlsx"]),
    "PSI-98": ("SAFFIRE-I", "solid", []),
    "PSI-99": ("SAFFIRE-II", "solid", []),
    "PSI-100": ("SAFFIRE-III", "solid", []),
    "PSI-101": ("SAME-R", "aerosol", []),
    "PSI-102": ("SAME", "aerosol", []),
}

MANIFEST_COLUMNS = ["file_name", "folder", "subcategory", "size_bytes", "version",
                    "restricted", "psi_legacy", "s3_path", "local_path"]
INDEX_COLUMNS = ["psi_id", "acronym", "family", "title", "doi", "license",
                 "n_files", "total_size_mb", "n_downloaded", "downloaded_at"]
LOG_COLUMNS = ["date", "psi_id", "file_name", "status", "size_bytes", "local_path"]

session = requests.Session()
# Le serveur PSI coupe parfois la connexion : on réessaie automatiquement
_retry = requests.adapters.Retry(total=4, backoff_factor=2, status_forcelist=(429, 500, 502, 503, 504),
                                 allowed_methods=("GET",), raise_on_status=False)
session.mount("https://", requests.adapters.HTTPAdapter(max_retries=_retry))


def get_investigation(psi_id):
    """Métadonnées complètes d'une investigation (dict JSON de l'API PSI)."""
    r = session.get(f"{API}/repo/investigations/{psi_id}", timeout=60)
    r.raise_for_status()
    return r.json()


def get_all_files(psi_id):
    """Liste actuelle des fichiers d'une investigation.

    Le champ `added` de get_investigation() ne contient que les fichiers de la DERNIÈRE version :
    on rejoue donc tout l'historique (ajouts, modifications, suppressions).
    """
    r = session.get(f"{API}/repo/investigations/{psi_id}/versions", timeout=120)
    r.raise_for_status()
    files = {}
    for v in sorted(r.json()["versions"], key=lambda v: v["version"]):
        for f in v.get("added", []) + v.get("modified", []):
            files[f.get("remote_path") or f["file_name"]] = f
        for f in v.get("removed", []):
            files.pop(f.get("remote_path") or f["file_name"], None)
    return list(files.values())


def folder_of(file_info):
    """Dossier PSI du fichier (« Raw Data », « Experimental table »…), lu dans remote_path."""
    parts = file_info.get("remote_path", "").split("/")
    return parts[4] if len(parts) > 5 else ""


def safe_name(name):
    """Nom de fichier utilisable sous Windows (les noms PSI peuvent contenir : ? etc.)."""
    return re.sub(r'[<>:"/\\|?*]', "_", name).strip()


def download_file(psi_id, file_name, dest):
    """Télécharge un fichier PSI via une URL S3 signée. Renvoie (statut, taille)."""
    if dest.exists():
        return "already_present", dest.stat().st_size
    signed = session.get(f"{API}/studies/{psi_id}/download",
                         params={"file": file_name, "redirect": "false"}, timeout=60)
    url = signed.text.strip()
    if not signed.ok or not url.startswith("https://"):
        return f"no_url ({signed.status_code})", 0
    r = session.get(url, timeout=300)
    if not r.ok:
        return f"http_{r.status_code}", 0
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(r.content)
    return "ok", len(r.content)


def write_csv(path, columns, rows, append=False):
    new_file = not path.exists() or not append
    with open(path, "a" if append else "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        if new_file:
            writer.writeheader()
        writer.writerows(rows)


def fetch_investigation(psi_id, with_docs=True):
    """Télécharge une investigation. Renvoie (ligne pour psi_index.csv, lignes pour le log)."""
    acronym, family, doc_files = INVESTIGATIONS[psi_id]
    out_dir = RAW_PSI / f"{psi_id}_{acronym}"
    out_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.date.today().isoformat()

    meta = get_investigation(psi_id)
    (out_dir / "investigation.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8")
    files = get_all_files(psi_id)

    # Fichiers à télécharger : tables expérimentales + documents choisis
    wanted = {f["file_name"]: "experimental_table" for f in meta.get("experimentalTable") or []}
    if with_docs:
        for f in files:
            if f["file_name"] in doc_files:
                wanted.setdefault(f["file_name"], "documents")

    log, local = [], {}
    for file_name, sub in wanted.items():
        dest = out_dir / sub / safe_name(file_name)
        status, size = download_file(psi_id, file_name, dest)
        print(f"  {status:16} {size:>9} o  {sub}/{file_name}")
        if status in ("ok", "already_present"):
            local[file_name] = dest.relative_to(ROOT).as_posix()
        log.append({"date": today, "psi_id": psi_id, "file_name": file_name, "status": status,
                    "size_bytes": size, "local_path": local.get(file_name, "")})

    # Manifeste de TOUS les fichiers de l'investigation (PSI pèse plusieurs To : on ne télécharge pas tout)
    manifest = [{
        "file_name": f["file_name"],
        "folder": folder_of(f),
        "subcategory": f.get("subcategory", ""),
        "size_bytes": int(f.get("file_size") or 0),
        "version": f.get("version", ""),
        "restricted": f.get("restricted", ""),
        "psi_legacy": f.get("psi_legacy", False),
        "s3_path": f.get("s3_path", ""),
        "local_path": local.get(f["file_name"], ""),
    } for f in files]
    write_csv(out_dir / "files_manifest.csv", MANIFEST_COLUMNS, manifest)

    index_row = {
        "psi_id": psi_id,
        "acronym": acronym,
        "family": family,
        "title": meta.get("title", ""),
        "doi": meta.get("doi", ""),
        "license": meta.get("licenseIdentifier", ""),
        "n_files": len(files),
        "total_size_mb": round(sum(int(f.get("file_size") or 0) for f in files) / 1e6, 1),
        "n_downloaded": len(local),
        "downloaded_at": today,
    }
    return index_row, log


def main():
    parser = argparse.ArgumentParser(description="Télécharge les données brutes NASA PSI.")
    parser.add_argument("psi_ids", nargs="*", help="ex. PSI-69 PSI-25 (défaut : toutes)")
    parser.add_argument("--no-docs", action="store_true", help="ne pas télécharger documents/")
    args = parser.parse_args()

    ids = args.psi_ids or list(INVESTIGATIONS)
    unknown = [i for i in ids if i not in INVESTIGATIONS]
    if unknown:
        parser.error(f"investigations inconnues : {unknown} (à ajouter dans INVESTIGATIONS)")

    RAW_PSI.mkdir(parents=True, exist_ok=True)
    index_path = RAW_PSI / "psi_index.csv"
    index = {}
    if index_path.exists():
        with open(index_path, encoding="utf-8") as f:
            index = {row["psi_id"]: row for row in csv.DictReader(f)}

    for psi_id in ids:
        print(f"{psi_id} ({INVESTIGATIONS[psi_id][0]})")
        try:
            row, log = fetch_investigation(psi_id, with_docs=not args.no_docs)
        except requests.RequestException as e:
            print(f"  ERREUR : {e}")
            continue
        index[psi_id] = row
        write_csv(DOWNLOAD_LOG, LOG_COLUMNS, log, append=True)

    ordered = [index[i] for i in INVESTIGATIONS if i in index]
    write_csv(index_path, INDEX_COLUMNS, ordered)
    print(f"\nIndex : {index_path.relative_to(ROOT)}  |  Log : {DOWNLOAD_LOG.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
