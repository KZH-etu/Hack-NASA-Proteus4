"""Construit data/processed/ à partir de data/raw/psi/ (lancer d'abord `python -m src.data.download_psi`).

Sorties :
- unified.parquet          table catalogue, toutes familles (schéma src/common/schema.py)
- experiments_all.csv      la même table en CSV (lisible sur GitHub), avec liens PSI et DOI
- families/<famille>.parquet  une table de modélisation par famille physique, avec ses colonnes propres
- campaigns.csv            une ligne par investigation PSI (DOI, plateforme, nb de lignes, statut)
- skipped_rows.csv         lignes des tables sources écartées, avec la raison
- data_dictionary.md       colonnes, unités, descriptions (généré)
- qc_report.md             lignes par campagne, marques qualité, cases vides par motif (généré)
- annotations/             valeurs saisies à la main (non écrasées)

Usage :
    python -m src.data.build_unified

Dans le code :
    from src.data.build_unified import load_unified_table, load_family
"""

import csv
import json
from collections import Counter

import pandas as pd

from src.common.schema import COLUMNS, FUEL_TYPES, GRAVITY_LEVELS, OUTCOMES, QC_REASONS, check_qc_flags
from src.data import droplets, gas, solids
from src.data.common import PROCESSED, RAW_PSI, psi_index

# Familles traitées : nom -> module (chaque module expose build() et FAMILY_COLUMNS)
FAMILIES = {"droplets": droplets, "gas": gas, "solids": solids}

# Investigations pas encore traitées (affichées comme « à faire » dans campaigns.csv et qc_report.md)
PENDING = {
    "PSI-39": "droplets",
    "PSI-101": "aerosols", "PSI-102": "aerosols",
}

UNIFIED_DOCS = {
    "experiment": ("", "Nom de l'expérience"),
    "psi_id": ("", "Investigation PSI"),
    "doi": ("", "DOI de l'investigation PSI"),
    "test_id": ("", "Identifiant de l'essai dans la source"),
    "fuel_type": ("", f"Famille : {', '.join(FUEL_TYPES)}"),
    "material": ("", "Combustible ou matériau (minuscules)"),
    "geometry": ("", "Géométrie de l'échantillon"),
    "o2_percent": ("%", "O2 initial côté oxydant, en % molaire (flammes inverses ACME : O2 du jet du brûleur)"),
    "pressure_kpa": ("kPa", "Pression ambiante"),
    "flow_cm_s": ("cm/s", "Vitesse d'écoulement imposé (SPICE : co-courant d'air) ; vide si non quantifiée (FLEX : gouttelettes libres ou à dérive lente) ou sans objet (ACME : brûleur sphérique en chambre calme)"),
    "gravity": ("", f"{' / '.join(GRAVITY_LEVELS)} ; ne jamais mélanger les deux dans un entraînement"),
    "outcome": ("", f"Issue normalisée : {', '.join(OUTCOMES)} (texte d'origine dans notes)"),
    "spread_rate_mm_s": ("mm/s", "Vitesse de propagation de flamme"),
    "burning_rate": ("mm²/s", "Constante de combustion K des gouttelettes (FLEX) ; sans objet pour les gaz et les solides"),
    "source_doc": ("", "Fichier PSI ou document NASA d'où vient la ligne"),
    "source_page": ("", "Ligne du fichier PSI ou page du document"),
    "notes": ("", "Texte d'origine utile (issue brute, diluant, unités)"),
    "qc_flags": ("", "Marques qualité « colonne:motif;... »"),
}

QC_REASON_DOCS = {
    "sans_objet": "vide car sans objet vu l'issue de l'essai (ne compte pas comme un trou de données)",
    "doc": "valeur absente de la table, prise dans un document NASA (source_doc / source_page)",
    "nominal": "valeur nominale de l'expérience, pas mesurée essai par essai",
    "recopie": "recopiée d'une autre ligne de la même table",
    "zero_fictif": "0 de la source remplacé par vide (0 utilisé pour « pas de donnée »)",
    "incoherent": "valeur physiquement douteuse",
    "a_verifier": "sources NASA contradictoires ou identifiant en double",
    "approx": "valeur approchée dans la source (« ~6 »)",
    "rampe": "condition variable pendant l'essai",
    "sans_allumage_chaud": "burn time = 0 car pas d'allumage chaud",
    "qualitatif": "texte qualitatif à la place d'un nombre (« LOW O2 ») : vide, texte gardé en commentaire",
    "erreur_excel": "erreur de formule dans la source (« #DIV/0! », « #VALUE! ») : vide",
    "deduit": "déduit d'un texte explicite de la même ligne (ex. « 5 3 2 ext » -> extinction)",
}

ANNOTATION_TEMPLATES = {
    "bass_outcomes.csv": ["experiment", "test_id", "outcome", "flow_direction", "source_doc", "source_page", "annotator", "note"],
}


# ---------- Chargement (utilisé par ml et app) ----------

def load_unified_table():
    """Table catalogue (une ligne par essai, toutes familles)."""
    return pd.read_parquet(PROCESSED / "unified.parquet")


def load_family(name):
    """Table de modélisation d'une famille : 'droplets' (puis 'gas', 'solids', 'aerosols')."""
    return pd.read_parquet(PROCESSED / "families" / f"{name}.parquet")


# ---------- Validation ----------

def validate_unified(df):
    """Erreurs bloquantes sur la table unifiée (liste vide si tout est bon)."""
    errors = []
    if list(df.columns) != list(COLUMNS):
        errors.append(f"colonnes différentes du schéma : {list(df.columns)}")
    for col, allowed in (("fuel_type", FUEL_TYPES), ("gravity", GRAVITY_LEVELS), ("outcome", OUTCOMES)):
        bad = set(df[col].dropna()) - set(allowed)
        if bad:
            errors.append(f"{col} : valeurs non autorisées {bad}")
    for col in ("experiment", "psi_id", "doi", "gravity", "source_doc", "source_page"):
        if df[col].isna().any():
            errors.append(f"{col} : {int(df[col].isna().sum())} ligne(s) sans valeur (traçabilité obligatoire)")
    o2 = df["o2_percent"].dropna()
    if ((o2 < 0) | (o2 > 100)).any():
        errors.append("o2_percent hors de [0, 100]")
    if (df["pressure_kpa"].dropna() <= 0).any():
        errors.append("pressure_kpa <= 0 (un 0 de la source doit être vidé avec zero_fictif)")
    for value in df["qc_flags"].dropna():
        errors += check_qc_flags(value)
    dup = df.duplicated(["experiment", "test_id"]).sum()
    if dup:
        errors.append(f"{dup} doublon(s) (experiment, test_id)")
    return errors


def validate_family(name, df, columns):
    errors = []
    if list(df.columns) != list(columns):
        errors.append(f"{name} : colonnes différentes de FAMILY_COLUMNS")
    for value in df["qc_flags"].dropna():
        errors += [f"{name} : {e}" for e in check_qc_flags(value, columns=columns)]
    return errors


# ---------- Rapports ----------

def flag_counter(series):
    return Counter(item for value in series.dropna() for item in value.split(";"))


def empty_cells_report(df):
    """Pour chaque colonne, classe les cases vides : sans objet, faux zéro vidé, autre marque (rampe, erreur...),
    colonne absente du fichier source ; le reste est vraiment manquant dans la source."""
    flags = df["qc_flags"].fillna("")
    lines = ["| Colonne | Vides | sans objet | faux zéro vidé | autre marque | absente du fichier source | vraiment manquants |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for col in df.columns:
        empty = df[col].isna()
        if not empty.any() or col == "qc_flags":
            continue
        source = "source_file" if "source_file" in df else "source_doc"  # colonne absente de ce fichier source
        has = lambda reason: flags.str.contains(f"{col}:{reason}", regex=False)
        # une marque explicite l'emporte sur « absente du fichier » : elle dit pourquoi c'est vide
        sans_objet = empty & has("sans_objet")
        zero = empty & ~sans_objet & has("zero_fictif")
        other = empty & ~sans_objet & ~zero & flags.str.contains(f"{col}:", regex=False)
        absent = empty & ~sans_objet & ~zero & ~other & df.groupby(source)[col].transform(lambda s: s.isna().all())
        missing = empty & ~absent & ~sans_objet & ~zero & ~other
        lines.append(f"| `{col}` | {empty.sum()} / {len(df)} | {sans_objet.sum()} | {zero.sum()} | {other.sum()} | {absent.sum()} | {missing.sum()} |")
    return lines


def write_qc_report(unified, families, skipped, campaigns):
    out = ["# Rapport qualité — data/processed", "",
           "Généré par `python -m src.data.build_unified`. Ne pas éditer à la main.",
           "Règles : `docs/regles_valeurs_manquantes.md`.", "",
           "## Lignes par campagne", "",
           "| PSI | Expérience | Famille | Lignes | Avec marques | Statut |", "|---|---|---|---:|---:|---|"]
    for c in campaigns:
        rows = unified[unified["psi_id"] == c["psi_id"]]
        out.append(f"| {c['psi_id']} | {c['experiment']} | {c['family']} | {len(rows)} | {int(rows['qc_flags'].notna().sum())} | {c['status']} |")
    out += ["", f"Lignes écartées : {len(skipped)} (détail dans `skipped_rows.csv`).", ""]
    for name, df in families.items():
        out += [f"## families/{name}.parquet ({len(df)} lignes)", "", "Marques les plus fréquentes :", ""]
        out += [f"- `{item}` × {n}" for item, n in flag_counter(df["qc_flags"]).most_common(15)] or ["- aucune"]
        out += ["", "Cases vides :", ""] + empty_cells_report(df) + [""]
    out += ["## unified.parquet", "", f"{len(unified)} lignes.", ""] + empty_cells_report(unified) + [""]
    (PROCESSED / "qc_report.md").write_text("\n".join(out), encoding="utf-8")


def write_data_dictionary():
    out = ["# Dictionnaire des données — data/processed", "",
           "Généré par `python -m src.data.build_unified` à partir du code. Ne pas éditer à la main.", "",
           "## unified.parquet (table catalogue)", "", "| Colonne | Type | Unité | Description |", "|---|---|---|---|"]
    out += [f"| `{c}` | {COLUMNS[c]} | {UNIFIED_DOCS[c][0]} | {UNIFIED_DOCS[c][1]} |" for c in COLUMNS]
    for name, module in FAMILIES.items():
        out += ["", f"## families/{name}.parquet", "", "| Colonne | Type | Unité | Description |", "|---|---|---|---|"]
        out += [f"| `{c}` | {t} | {u} | {d} |" for c, (t, u, d) in module.FAMILY_COLUMNS.items()]
    out += ["", "## Motifs de `qc_flags`", "", "| Motif | Sens |", "|---|---|"]
    out += [f"| `{r}` | {QC_REASON_DOCS[r]} |" for r in QC_REASONS]
    (PROCESSED / "data_dictionary.md").write_text("\n".join(out) + "\n", encoding="utf-8")


def campaigns_table(unified):
    rows = []
    for psi_id, meta in psi_index().items():
        info = json.loads(next(RAW_PSI.glob(f"{psi_id}_*/investigation.json")).read_text(encoding="utf-8"))
        n = int((unified["psi_id"] == psi_id).sum())
        rows.append({
            "psi_id": psi_id,
            "experiment": meta["acronym"].replace("_", " "),
            "family": meta["family"],
            "title": meta["title"],
            "doi": meta["doi"],
            "license": meta["license"] or None,
            "platform": info.get("flightProgram"),
            "hardware": (info.get("experimentHardware") or "").strip() or None,
            "project_type": info.get("projectType"),
            "start": info.get("investigationStartDate"),
            "end": info.get("investigationEndDate"),
            "n_rows": n,
            "status": "traité" if n else f"à faire ({PENDING.get(psi_id, '?')})",
        })
    return rows


def write_experiments_all(unified):
    """unified en CSV, avec les liens vers l'investigation PSI et le DOI (équivalent d'experiments_all.csv)."""
    out = unified.copy()
    out["psi_url"] = "https://psi.nasa.gov/physci/repo/data/investigations/" + out["psi_id"]
    out["doi_url"] = "https://doi.org/" + out["doi"]
    out.to_csv(PROCESSED / "experiments_all.csv", index=False, encoding="utf-8")


# ---------- Construction ----------

def main():
    (PROCESSED / "families").mkdir(parents=True, exist_ok=True)
    (PROCESSED / "annotations").mkdir(parents=True, exist_ok=True)

    families, unified_parts, skipped = {}, [], []
    for name, module in FAMILIES.items():
        family_df, unified_df, skipped_rows = module.build()
        families[name] = family_df
        unified_parts.append(unified_df)
        skipped += skipped_rows

    unified = pd.concat(unified_parts, ignore_index=True)[list(COLUMNS)].astype(COLUMNS)

    errors = validate_unified(unified)
    for name, df in families.items():
        errors += validate_family(name, df, FAMILIES[name].FAMILY_COLUMNS)
    if errors:
        raise SystemExit("Validation échouée :\n- " + "\n- ".join(errors))

    unified.to_parquet(PROCESSED / "unified.parquet", index=False)
    write_experiments_all(unified)
    for name, df in families.items():
        df.to_parquet(PROCESSED / "families" / f"{name}.parquet", index=False)

    campaigns = campaigns_table(unified)
    pd.DataFrame(campaigns).to_csv(PROCESSED / "campaigns.csv", index=False)
    pd.DataFrame(skipped, columns=["psi_id", "source_file", "source_line", "reason"]).to_csv(PROCESSED / "skipped_rows.csv", index=False)
    for file_name, header in ANNOTATION_TEMPLATES.items():
        path = PROCESSED / "annotations" / file_name
        if not path.exists():  # saisies manuelles : ne jamais écraser
            with open(path, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(header)
    write_data_dictionary()
    write_qc_report(unified, families, skipped, campaigns)

    print(f"unified.parquet : {len(unified)} lignes")
    for name, df in families.items():
        print(f"families/{name}.parquet : {len(df)} lignes")
    print(f"Investigations traitées : {sum(1 for c in campaigns if c['n_rows'])} / {len(campaigns)}")


if __name__ == "__main__":
    main()
