"""Famille « aérosols » : SAME (PSI-102) et SAME-R (PSI-101).

Fumées produites en chauffant des matériaux de vaisseau (pas de flamme) : pour la détection de fumée,
pas pour le modèle de combustion. Ces essais vont dans families/aerosols.parquet mais pas dans la table
catalogue unified.parquet (dont fuel_type ne prévoit que solid / droplet / gas).

- SAME : les échantillons 5 à 8 disent « same conditions as 1-4 » -> une ligne par condition des essais 1 à 4 (recopie).
- SAME-R : les essais « 61a » sont la mesure vieillie du même échantillon que « 61 » : durée et temps de
  vieillissement / mélange primaires recopiés de la ligne parente. Dates sans année dans la source.
"""

import re

import pandas as pd

from src.data.common import Flags, experimental_table, parse_number, read_raw_csv

FAMILY_COLUMNS = {
    "experiment": ("string", "", "SAME ou SAME-R"),
    "psi_id": ("string", "", "Investigation PSI"),
    "test_id": ("string", "", "SAME : n° d'échantillon (+ « -c<k> » pour les conditions recopiées) ; SAME-R : n° d'essai (« 61a » = mesure vieillie de 61)"),
    "parent_test": ("string", "", "SAME-R : essai parent d'une mesure vieillie"),
    "session": ("string", "", "Groupe pour la validation croisée : date (SAME-R) ou expérience (SAME)"),
    "date_raw": ("string", "", "Date telle qu'écrite (sans année pour SAME-R)"),
    "material": ("string", "", "Matériau chauffé (kapton, silicone, lampwick, teflon, pyrell, dibutyl phthalate)"),
    "description": ("string", "", "Description de l'essai (SAME-R)"),
    "flow_cm_s": ("Float64", "cm/s", "Vitesse d'air (SAME : « Air Flow » ; SAME-R : « Inlet velocity », 0 = essai sans écoulement)"),
    "weight_loss_mg_min": ("Float64", "mg/min", "Perte de masse de l'échantillon (SAME)"),
    "aging_s": ("Float64", "s", "Durée de vieillissement de la fumée (SAME : minutes × 60)"),
    "rt_r0": ("Float64", "", "Rapport de résistance du chauffage Rt/R0 (SAME-R, lié à la température)"),
    "duration_s": ("Float64", "s", "Durée de chauffage (SAME-R)"),
    "primary_aging_s": ("Float64", "s", "Temps de vieillissement primaire (SAME-R)"),
    "primary_mixing_s": ("Float64", "s", "Temps de mélange primaire (SAME-R)"),
    "net_aging_s": ("Float64", "s", "Temps de vieillissement net (SAME-R)"),
    "gravity": ("string", "", "micro (ISS)"),
    "source_file": ("string", "", "Fichier PSI d'origine"),
    "source_line": ("Int64", "", "Ligne dans le fichier d'origine (en-tête = 1)"),
    "qc_flags": ("string", "", "Marques qualité « colonne:motif;... »"),
}


def _num(flags, column, text, scale=1.0):
    value, reason = parse_number(text)
    if reason == "approx":
        flags.add(column, "approx")
    elif reason == "non_numerique":
        flags.add(column, "qualitatif")
    return round(value * scale, 6) if value is not None else None


def build_same():
    path = experimental_table("PSI-102")
    raw = read_raw_csv(path)
    material_col = [c for c in raw.columns if c.startswith("Sample Material")][0]
    base = []  # conditions des échantillons 1 à 4
    rows = []
    for _, r in raw.iterrows():
        label = r[material_col]
        material = label.split(":")[0].strip().lower()
        if "same conditions as" in label.lower():
            for k, cond in enumerate(base, start=1):
                flags = Flags()
                for col in ("flow_cm_s", "weight_loss_mg_min", "aging_s"):
                    if cond[col] is not None:
                        flags.add(col, "recopie")
                rows.append({**cond, "test_id": f"{r['Sample #']}-c{k}", "material": material,
                             "source_line": r["source_line"], "qc_flags": flags.to_str(keep_columns=FAMILY_COLUMNS)})
            continue
        flags = Flags()
        row = {
            "experiment": "SAME", "psi_id": "PSI-102", "test_id": r["Sample #"], "parent_test": None,
            "session": "SAME", "date_raw": None, "material": material, "description": None,
            "flow_cm_s": _num(flags, "flow_cm_s", r["Air Flow (cm/s)"]),
            "weight_loss_mg_min": _num(flags, "weight_loss_mg_min", r["Weight loss rate (mg/min)"]),
            "aging_s": _num(flags, "aging_s", r["Aging Duration (minutes)"], scale=60),
            "rt_r0": None, "duration_s": None, "primary_aging_s": None, "primary_mixing_s": None, "net_aging_s": None,
            "gravity": "micro", "source_file": path.name, "source_line": r["source_line"],
            "qc_flags": flags.to_str(keep_columns=FAMILY_COLUMNS),
        }
        base.append(row)
        rows.append(row)
    return rows


def build_same_r():
    path = experimental_table("PSI-101")
    raw = read_raw_csv(path)
    rows, by_test = [], {}
    for _, r in raw.iterrows():
        flags = Flags()
        test = r["SAME Test #"]
        material = r["Sample Type"].lower()
        row = {
            "experiment": "SAME-R", "psi_id": "PSI-101", "test_id": test, "parent_test": None,
            "session": r["Date"] or None, "date_raw": r["Date"] or None, "material": material,
            "description": r["Description"] or None,
            "flow_cm_s": _num(flags, "flow_cm_s", r["Inlet velocity (cm/s)"]),
            "weight_loss_mg_min": None, "aging_s": None,
            "rt_r0": _num(flags, "rt_r0", r["Rt/R0"]),
            "duration_s": _num(flags, "duration_s", r["Duration (sec)"]),
            "primary_aging_s": _num(flags, "primary_aging_s", r["Primary aging time (sec)"]),
            "primary_mixing_s": _num(flags, "primary_mixing_s", r["Primary mixing time (sec)"]),
            "net_aging_s": _num(flags, "net_aging_s", r["Net aging time (sec)"]),
            "gravity": "micro", "source_file": path.name, "source_line": r["source_line"],
        }
        parent = by_test.get((material, test[:-1])) if re.fullmatch(r"\d+a", test) else None
        if parent is not None:  # mesure vieillie du même échantillon : conditions de chauffage de la ligne parente
            row["parent_test"] = parent["test_id"]
            for col in ("duration_s", "primary_aging_s", "primary_mixing_s"):
                if row[col] is None and parent[col] is not None:
                    row[col] = parent[col]
                    flags.add(col, "recopie")
        row["qc_flags"] = flags.to_str(keep_columns=FAMILY_COLUMNS)
        by_test[(material, test)] = row
        rows.append(row)
    return rows


def build():
    """Renvoie (table famille, lignes unifiées : aucune, lignes écartées : aucune)."""
    rows = build_same() + build_same_r()
    family_df = pd.DataFrame(rows)[list(FAMILY_COLUMNS)].astype({k: v[0] for k, v in FAMILY_COLUMNS.items()})
    return family_df, pd.DataFrame(columns=list(FAMILY_COLUMNS)[:0]), []
