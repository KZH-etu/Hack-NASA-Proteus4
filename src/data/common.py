"""Outils partagés par les modules de nettoyage (un module par famille physique).

Règles appliquées partout (détail dans docs/regles_valeurs_manquantes.md) :
- une valeur absente de la source reste vide, jamais inventée ;
- toute valeur interprétée (approchée, recopiée, nominale, faux zéro vidé...) laisse une marque dans qc_flags ;
- chaque ligne garde son fichier PSI et son numéro de ligne d'origine.
"""

import csv
import math
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW_PSI = ROOT / "data" / "raw" / "psi"
PROCESSED = ROOT / "data" / "processed"

MMHG_TO_KPA = 0.133322
ATM_TO_KPA = 101.325
DASHES = {"-", "–", "—", "--"}


def psi_index():
    """Métadonnées des investigations téléchargées (data/raw/psi/psi_index.csv), indexées par psi_id."""
    path = RAW_PSI / "psi_index.csv"
    if not path.exists():
        raise FileNotFoundError(f"{path} absent : lancer d'abord `python -m src.data.download_psi`")
    with open(path, encoding="utf-8") as f:
        return {row["psi_id"]: row for row in csv.DictReader(f)}


def experimental_table(psi_id, name_contains=""):
    """Chemin de la table expérimentale d'une investigation (data/raw/psi/<psi_id>_*/experimental_table/)."""
    matches = sorted(RAW_PSI.glob(f"{psi_id}_*/experimental_table/*{name_contains}*.csv"))
    if len(matches) != 1:
        raise FileNotFoundError(f"{psi_id} / '{name_contains}' : {len(matches)} fichier(s) trouvé(s)")
    return matches[0]


def read_raw_csv(path):
    """Lit une table PSI en texte brut (aucune conversion), en gérant les encodages utf-8 et cp1252.

    Ajoute `source_line` (numéro de ligne dans le fichier, en-tête = ligne 1) et retire les lignes vides.
    """
    for encoding in ("utf-8", "cp1252"):
        try:
            df = pd.read_csv(path, encoding=encoding, dtype=str, keep_default_na=False)
            break
        except UnicodeDecodeError:
            continue
    df.columns = [c.strip() for c in df.columns]
    df = df.apply(lambda col: col.str.strip())
    df["source_line"] = range(2, len(df) + 2)
    data_cols = [c for c in df.columns if c != "source_line"]
    return df[(df[data_cols] != "").any(axis=1)].reset_index(drop=True)


def parse_number(raw):
    """Convertit une cellule en nombre. Renvoie (valeur ou None, motif ou None).

    - "" -> (None, None) : vide dans la source
    - "–" -> (None, "tiret") : tiret de la source (le sens dépend de l'expérience)
    - "~6" -> (6.0, "approx")
    - texte non numérique -> (None, "non_numerique")
    """
    s = (raw or "").strip()
    if s == "":
        return None, None
    if s in DASHES:
        return None, "tiret"
    reason = None
    if s.startswith("~"):
        s, reason = s.lstrip("~ ").strip(), "approx"
    try:
        value = float(s)
    except ValueError:
        return None, "non_numerique"
    if math.isnan(value):
        return None, None
    return value, reason


class Flags:
    """Accumule les marques qc d'une ligne : flags.add("pressure_kpa", "zero_fictif")."""

    def __init__(self):
        self.items = []

    def add(self, column, reason):
        item = f"{column}:{reason}"
        if item not in self.items:
            self.items.append(item)

    def to_str(self, keep_columns=None, rename=None):
        """Chaîne "col:motif;..." ; `rename` traduit des colonnes, `keep_columns` filtre (pour la table unifiée)."""
        out = []
        for item in self.items:
            col, reason = item.split(":")
            col = (rename or {}).get(col, col)
            if keep_columns is None or col in keep_columns:
                out.append(f"{col}:{reason}")
        return ";".join(dict.fromkeys(out)) or None


def us_date_to_iso(raw):
    """'3/5/2009' ou '10/24/09' (mois/jour/année) -> 'AAAA-MM-JJ' ; None si vide ou illisible."""
    text = str(raw or "").replace("`", "").strip()  # « 6/29/`12 » dans BASS
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return pd.to_datetime(text, format=fmt).date().isoformat()
        except (ValueError, TypeError):
            continue
    return None



class Row:
    """Une ligne en cours de nettoyage : valeurs de la table famille (`columns`) + marques qualité."""

    def __init__(self, raw, columns, experiment, psi_id, path):
        self.raw, self.columns, self.flags, self.qualitative = raw, columns, Flags(), []
        self.values = {c: None for c in columns}
        self.values.update(experiment=experiment, psi_id=psi_id, gravity="micro",
                           source_file=path.name, source_line=raw["source_line"])

    def num(self, source_col, target, scale=1.0, offset=0.0, text=None):
        """Lit un nombre de la source dans `target` ; marque rampe / approx / qualitatif / erreur Excel."""
        text = self.raw.get(source_col, "") if text is None else str(text).strip()
        if text.upper() in ("RAMP", "RAMPED"):
            self.flags.add(target, "rampe")
            return None
        value, reason = parse_number(text)
        if reason == "approx":
            self.flags.add(target, reason)
        elif reason == "non_numerique":
            if text.startswith("#"):  # « #DIV/0! », « #VALUE! »
                self.flags.add(target, "erreur_excel")
            else:  # « LOW O2 », « Insignificant » : texte gardé dans les commentaires
                self.flags.add(target, "qualitatif")
                self.qualitative.append(f"{source_col} = {text}")
        if value is not None:
            value = round(value * scale + offset, 6)
        self.values[target] = value
        return value

    def flag(self, column, reason):
        self.flags.add(column, reason)

    def finish(self, comments_column):
        """Recopie les textes qualitatifs dans `comments_column` et écrit qc_flags."""
        if self.qualitative:
            texts = "; ".join(dict.fromkeys(self.qualitative))
            current = self.values[comments_column]
            self.values[comments_column] = f"{current} | {texts}" if current else texts
        self.values["qc_flags"] = self.flags.to_str(keep_columns=self.columns)
        return self.values
