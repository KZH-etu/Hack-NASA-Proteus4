"""Famille « gouttelettes » : FLEX (PSI-69). CFI (PSI-39) à ajouter.

Sortie : une table par famille (data/processed/families/droplets.parquet) + les lignes de la table unifiée.
Référence des colonnes FLEX : NASA/TP-2015-216046 (NTRS 20150023456), annexe A.2, Table IX, p. 19.
"""

import pandas as pd

from src.common.schema import COLUMNS
from src.data.common import MMHG_TO_KPA, Flags, experimental_table, parse_number, psi_index, read_raw_csv, us_date_to_iso

FLEX_REPORT = "NASA/TP-2015-216046"

# Colonnes de data/processed/families/droplets.parquet : nom -> (type pandas, unité, description)
FAMILY_COLUMNS = {
    "experiment": ("string", "", "Nom de l'expérience (FLEX)"),
    "psi_id": ("string", "", "Investigation PSI"),
    "test_id": ("string", "", "Numéro d'essai de l'équipe scientifique (« FLEX Test # »)"),
    "cir_identifier": ("string", "", "Identifiant de l'équipe ingénierie CIR (« FLEX Identifier »), pas toujours unique"),
    "test_date": ("string", "AAAA-MM-JJ", "Date de l'essai"),
    "test_time_gmt": ("string", "HH:MM:SS", "Heure de l'essai (GMT)"),
    "session": ("string", "", "Groupe pour la validation croisée : jour d'essai (les essais d'un même jour partagent l'atmosphère de la chambre)"),
    "fuel": ("string", "", "Combustible (heptane, methanol)"),
    "pressure_kpa": ("Float64", "kPa", "Pression ambiante (source en mmHg, × 0.133322)"),
    "x_o2": ("Float64", "fraction molaire", "O2 initial"),
    "x_n2": ("Float64", "fraction molaire", "N2 initial"),
    "x_co2": ("Float64", "fraction molaire", "CO2 initial (0 = pas de CO2, vrai zéro)"),
    "x_he": ("Float64", "fraction molaire", "He initial (0 = pas d'hélium, vrai zéro)"),
    "diluent": ("string", "", "Gaz inertes présents, calculé depuis x_n2, x_co2, x_he (ex. « N2+CO2 »)"),
    "d0_mm": ("Float64", "mm", "Diamètre initial de la gouttelette"),
    "d_ext_mm": ("Float64", "mm", "Diamètre à l'extinction de la flamme visible ; vide si pas d'extinction (qc: sans_objet)"),
    "burning_rate_mm2_s": ("Float64", "mm²/s", "Constante de combustion K (pente de d² en fonction du temps) ; l'en-tête PSI dit « mm », le rapport NASA dit mm²/s"),
    "burn_time_s": ("Float64", "s", "Durée de combustion"),
    "test_end_raw": ("string", "", "Issue telle qu'écrite dans la source (Extinction, Disruption, Completion)"),
    "outcome": ("string", "", "Issue normalisée (valeurs OUTCOMES du schéma)"),
    "gravity": ("string", "", "micro : investigation de type « Microgravity Investigation » (ISS)"),
    "source_file": ("string", "", "Fichier PSI d'origine"),
    "source_line": ("Int64", "", "Ligne dans le fichier d'origine (en-tête = 1)"),
    "qc_flags": ("string", "", "Marques qualité « colonne:motif;... » (motifs : QC_REASONS du schéma)"),
}

FLEX_OUTCOMES = {"Extinction": "extinguished", "Disruption": "disruption", "Completion": "completion"}

# Colonnes de la table familiale -> colonnes de la table unifiée (pour traduire les qc_flags)
TO_UNIFIED = {"burning_rate_mm2_s": "burning_rate", "test_end_raw": "outcome", "x_o2": "o2_percent"}


def _col(df, start):
    """Colonne dont le nom commence par `start` (les en-têtes FLEX ont perdu leurs indices : « O initial... » = O2)."""
    found = [c for c in df.columns if c.startswith(start)]
    if len(found) != 1:
        raise KeyError(f"FLEX : colonne « {start}... » introuvable ou ambiguë : {found}")
    return found[0]


def _diluent(x_n2, x_co2, x_he):
    gases = [name for name, x in (("N2", x_n2), ("CO2", x_co2), ("He", x_he)) if x]
    return "+".join(gases) or None


def build_flex():
    """Nettoie la table FLEX. Renvoie (table famille, lignes unifiées, lignes écartées)."""
    meta = psi_index()["PSI-69"]
    path = experimental_table("PSI-69")
    raw = read_raw_csv(path)
    col = {
        "o2": _col(raw, "O initial"), "n2": _col(raw, "N initial"),
        "co2": _col(raw, "CO initial"), "he": _col(raw, "He initial"),
        "p": _col(raw, "Ambient pressure"), "d0": _col(raw, "Droplet initial diameter"),
        "dext": _col(raw, "Visible flame extinction"), "k": _col(raw, "Burning rate"), "bt": _col(raw, "Burn time"),
    }
    duplicated_ids = set(raw.loc[raw["FLEX Identifier"].duplicated(keep=False), "FLEX Identifier"])

    family, unified, skipped = [], [], []
    for _, r in raw.iterrows():
        flags = Flags()
        end_raw = r["Test end"]
        outcome = FLEX_OUTCOMES.get(end_raw)
        if outcome is None:
            flags.add("test_end_raw", "a_verifier")

        def num(column, name):
            value, reason = parse_number(r[column])
            if reason == "approx":
                flags.add(name, "approx")
            elif reason == "non_numerique":
                flags.add(name, "incoherent")
            return value, reason

        p_mmhg, _ = num(col["p"], "pressure_kpa")
        if p_mmhg == 0:  # pression nulle impossible : 0 utilisé pour « pas de donnée »
            p_mmhg = None
            flags.add("pressure_kpa", "zero_fictif")
        x = {k: num(col[k], f"x_{k}")[0] for k in ("o2", "n2", "co2", "he")}
        d0, _ = num(col["d0"], "d0_mm")
        k_rate, _ = num(col["k"], "burning_rate_mm2_s")
        burn_time, _ = num(col["bt"], "burn_time_s")

        # Diamètre d'extinction : « – » ou 0 = pas d'extinction (Table IX, p. 19) -> sans objet si l'issue le confirme
        d_ext, reason = num(col["dext"], "d_ext_mm")
        if d_ext == 0 or reason == "tiret" or d_ext is None:
            if outcome in ("disruption", "completion"):
                if d_ext == 0:
                    flags.add("d_ext_mm", "zero_fictif")
                flags.add("d_ext_mm", "sans_objet")
                d_ext = None
            elif d_ext == 0:  # extinction annoncée mais diamètre 0 : non mesurable
                flags.add("d_ext_mm", "zero_fictif")
                d_ext = None
        flags.add("spread_rate_mm_s", "sans_objet")  # vitesse de propagation : notion des solides, pas des gouttelettes
        if r["FLEX Identifier"] in duplicated_ids:
            flags.add("cir_identifier", "a_verifier")

        x_sum = sum(v for v in x.values() if v is not None)
        if not 0.97 <= x_sum <= 1.03:
            flags.add("x_o2", "incoherent")

        family.append({
            "experiment": "FLEX",
            "psi_id": "PSI-69",
            "test_id": r["FLEX Test #"],
            "cir_identifier": r["FLEX Identifier"] or None,
            "test_date": us_date_to_iso(r["Test Date"]),
            "test_time_gmt": r["Test GMT"] or None,
            "session": us_date_to_iso(r["Test Date"]),
            "fuel": r["Fuel"].lower() or None,
            "pressure_kpa": round(p_mmhg * MMHG_TO_KPA, 2) if p_mmhg is not None else None,
            "x_o2": x["o2"], "x_n2": x["n2"], "x_co2": x["co2"], "x_he": x["he"],
            "diluent": _diluent(x["n2"], x["co2"], x["he"]),
            "d0_mm": d0,
            "d_ext_mm": d_ext,
            "burning_rate_mm2_s": k_rate,
            "burn_time_s": burn_time,
            "test_end_raw": end_raw or None,
            "outcome": outcome,
            "gravity": "micro",
            "source_file": path.name,
            "source_line": r["source_line"],
            "qc_flags": flags.to_str(keep_columns=FAMILY_COLUMNS),
        })
        unified.append({
            "experiment": "FLEX",
            "psi_id": "PSI-69",
            "doi": meta["doi"],
            "test_id": r["FLEX Test #"],
            "fuel_type": "droplet",
            "material": r["Fuel"].lower() or None,
            "geometry": "droplet",
            "o2_percent": round(x["o2"] * 100, 2) if x["o2"] is not None else None,
            "pressure_kpa": round(p_mmhg * MMHG_TO_KPA, 2) if p_mmhg is not None else None,
            "flow_cm_s": None,  # piège G : gouttelettes libres ou à dérive lente, écoulement non quantifié
            "gravity": "micro",
            "outcome": outcome,
            "spread_rate_mm_s": None,
            "burning_rate": k_rate,
            "source_doc": path.name,
            "source_page": f"ligne {r['source_line']}",
            "notes": f"Test end: {end_raw}; diluant: {_diluent(x['n2'], x['co2'], x['he'])}; burning_rate = K en mm²/s ({FLEX_REPORT}, Table IX)",
            "qc_flags": flags.to_str(keep_columns=COLUMNS, rename=TO_UNIFIED),
        })

    family_df = pd.DataFrame(family).astype({k: v[0] for k, v in FAMILY_COLUMNS.items()})
    return family_df[list(FAMILY_COLUMNS)], pd.DataFrame(unified), skipped


def build():
    """Toutes les expériences de la famille. Renvoie (table famille, lignes unifiées, lignes écartées)."""
    family, unified, skipped = build_flex()
    # TODO CFI (PSI-39) : même structure, colonnes Pressure (« 1 atm »), Oxygen, Nitrogen, Helium, Fiber, Fuel
    return family, unified, skipped
