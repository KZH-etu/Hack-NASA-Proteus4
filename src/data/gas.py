"""Famille « flammes gazeuses » : ACME CFI-G (PSI-159), ACME Flame Design (PSI-10), SPICE (PSI-107).

Vocabulaire commun aux trois expériences :
- flame_type : normal (combustible dans le jet du brûleur, oxydant dans la chambre),
  inverse (oxydant dans le jet, combustible dans la chambre), coflow (SPICE : jet de combustible dans un co-courant d'air) ;
- x_fuel : fraction de combustible côté combustible (jet pour normal / coflow, chambre pour inverse) ;
- x_o2 : fraction d'O2 côté oxydant (chambre pour normal, jet pour inverse, air pour SPICE).
ACME : la date d'essai vient du code de test « AAJJJ... » (année + jour de l'année, cf. note de la table PSI-23).
"""

import datetime
import re

import pandas as pd

from src.common.schema import COLUMNS
from src.data.common import ATM_TO_KPA, Flags, experimental_table, parse_number, psi_index, read_raw_csv

MSG_PRESSURE_NOTE = "pression cabine nominale 1 atm dans la boîte à gants (MSG), non mesurée par essai ; cf. NASA/TM-20210011385 p. 11"

FAMILY_COLUMNS = {
    "experiment": ("string", "", "ACME CFI-G, ACME Flame Design ou SPICE"),
    "psi_id": ("string", "", "Investigation PSI"),
    "test_id": ("string", "", "Code d'essai (ACME, espaces retirés) ou « GMT<jour>-L<ligne> » (SPICE, qui n'a pas d'identifiant)"),
    "session": ("string", "", "Groupe pour la validation croisée : jour d'essai (ACME) ou flamme = jour + heure d'allumage (SPICE)"),
    "test_date": ("string", "AAAA-MM-JJ", "ACME : déduite du code AAJJJ ; SPICE : année inconnue, vide"),
    "gmt_day": ("Int64", "jour de l'année", "Jour GMT (SPICE ; ACME : JJJ du code)"),
    "flame_type": ("string", "", "normal, inverse ou coflow"),
    "fuel": ("string", "", "Combustible (ethylene, propane, n-butane...)"),
    "fuel_label_raw": ("string", "", "Libellé d'origine (ex. « 30% butane » = bouteille à 30 %, « 75 % Propylene »)"),
    "x_fuel": ("Float64", "fraction molaire", "Combustible côté combustible, en début d'essai"),
    "x_fuel_final": ("Float64", "fraction molaire", "Combustible dans la chambre en fin d'essai (flammes inverses)"),
    "x_o2": ("Float64", "fraction molaire", "O2 côté oxydant, en début d'essai"),
    "x_o2_final": ("Float64", "fraction molaire", "O2 dans la chambre en fin d'essai (flammes normales)"),
    "pressure_kpa": ("Float64", "kPa", "Pression en début d'essai (CFI-G : « approx p », marqué approx)"),
    "pressure_final_kpa": ("Float64", "kPa", "Pression en fin d'essai (Flame Design)"),
    "fuel_rate_mg_s": ("Float64", "mg/s", "Débit de combustible au brûleur (mélange)"),
    "hc_rate_mg_s": ("Float64", "mg/s", "Débit d'hydrocarbure seul (SPICE « HC Fuel Rate », CFI-G « mHC » / « HC burnrate »)"),
    "fuel_rate_sccm": ("Float64", "sccm", "Débit de combustible (SPICE)"),
    "o2_rate_mg_s": ("Float64", "mg/s", "Débit d'O2 au brûleur (flammes inverses)"),
    "n2_rate_mg_s": ("Float64", "mg/s", "Débit de N2 au brûleur"),
    "total_rate_mg_s": ("Float64", "mg/s", "Débit total au brûleur"),
    "nozzle_mm": ("Float64", "mm", "Diamètre de la buse (SPICE)"),
    "coflow_cm_s": ("Float64", "cm/s", "Vitesse du co-courant d'air (SPICE)"),
    "z_st": ("Float64", "", "Fraction de mélange stœchiométrique"),
    "t_ad_K": ("Float64", "K", "Température adiabatique de flamme (calculée par l'équipe ACME)"),
    "tfp": ("boolean", "", "Sonde TFP (pyrométrie à filament fin) utilisée (CFI-G)"),
    "hot_ignition_raw": ("string", "", "Allumage chaud tel qu'écrit (yes, no, flash)"),
    "end_mode_raw": ("string", "", "Fin d'essai : SE = auto-extinction, FT = coupure du débit, « - » = rien"),
    "cool_flame": ("boolean", "", "Flamme froide observée : colonne « Cool flame? » ou commentaire explicite ; vide = non renseigné (pas « non »)"),
    "burn_time_s": ("Float64", "s", "Durée de la flamme chaude"),
    "peak_burner_T_K": ("Float64", "K", "Température maximale du brûleur (source en °C, + 273.15)"),
    "flame_color": ("string", "", "Couleur notée (minuscules)"),
    "outcome": ("string", "", "Issue normalisée (OUTCOMES du schéma) ; vide pour Flame Design et SPICE (pas d'issue dans la table)"),
    "gravity": ("string", "", "micro : investigations de type « Microgravity Investigation » (ISS)"),
    "comments": ("string", "", "Commentaires d'origine"),
    "source_file": ("string", "", "Fichier PSI d'origine"),
    "source_line": ("Int64", "", "Ligne dans le fichier d'origine (en-tête = 1)"),
    "qc_flags": ("string", "", "Marques qualité « colonne:motif;... »"),
}

TO_UNIFIED = {"x_o2": "o2_percent", "coflow_cm_s": "flow_cm_s"}
FUEL_NAMES = {"c2h4": "ethylene", "c3h8": "propane", "ch4": "methane", "butane": "n-butane"}


# ---------- Outils ----------

class Row:
    """Une ligne en cours de nettoyage : valeurs de la table famille + marques qualité."""

    def __init__(self, raw, experiment, psi_id, path):
        self.raw, self.flags, self.qualitative = raw, Flags(), []
        self.values = {c: None for c in FAMILY_COLUMNS}
        self.values.update(experiment=experiment, psi_id=psi_id, gravity="micro",
                           source_file=path.name, source_line=raw["source_line"])

    def num(self, source_col, target, scale=1.0, offset=0.0):
        """Lit un nombre de la source dans `target` ; marque rampe / approx / incohérent."""
        text = self.raw.get(source_col, "")
        if text.upper() in ("RAMP", "RAMPED"):
            self.flags.add(target, "rampe")
            return None
        value, reason = parse_number(text)
        if reason == "approx":
            self.flags.add(target, reason)
        elif reason == "non_numerique":
            if text.startswith("#"):  # « #DIV/0! », « #VALUE! »
                self.flags.add(target, "erreur_excel")
            else:  # « LOW O2 » : texte gardé dans les commentaires
                self.flags.add(target, "qualitatif")
                self.qualitative.append(f"{source_col} = {text}")
        if value is not None:
            value = round(value * scale + offset, 6)
        self.values[target] = value
        return value

    def flag(self, column, reason):
        self.flags.add(column, reason)


def _fuel(label):
    """« 30% butane » -> ('n-butane', 0.30) ; « 75 % Propylene » -> ('propylene', 0.75) ; « C2H4 » -> ('ethylene', None)."""
    m = re.match(r"\s*(\d+(?:\.\d+)?)\s*%\s*(.+)", label)
    pct, name = (float(m.group(1)) / 100, m.group(2)) if m else (None, label)
    name = name.strip().lower()
    return FUEL_NAMES.get(name, name), pct


def _acme_date(test):
    """Code ACME « 21088A1 » -> ('2021-03-29', 88) : AA = année, JJJ = jour de l'année."""
    m = re.match(r"(\d{2})(\d{3})", test)
    if not m:
        return None, None
    year, day = 2000 + int(m.group(1)), int(m.group(2))
    return (datetime.date(year, 1, 1) + datetime.timedelta(days=day - 1)).isoformat(), day


def _unified(row, meta, geometry, notes):
    v = row.values
    o2 = v["x_o2"]
    flags = row.flags
    flags.add("spread_rate_mm_s", "sans_objet")  # pas de propagation sur un solide
    flags.add("burning_rate", "sans_objet")      # notion de gouttelette ; les débits sont dans families/gas
    if v["experiment"] != "SPICE":
        flags.add("flow_cm_s", "sans_objet")     # brûleur sphérique en chambre calme : débits en mg/s, pas de vitesse
    return {
        "experiment": v["experiment"],
        "psi_id": v["psi_id"],
        "doi": meta["doi"],
        "test_id": v["test_id"],
        "fuel_type": "gas",
        "material": v["fuel"],
        "geometry": geometry,
        "o2_percent": round(o2 * 100, 3) if o2 is not None else None,
        "pressure_kpa": v["pressure_kpa"],
        "flow_cm_s": v["coflow_cm_s"],
        "gravity": "micro",
        "outcome": v["outcome"],
        "spread_rate_mm_s": None,
        "burning_rate": None,
        "source_doc": v["source_file"],
        "source_page": f"ligne {v['source_line']}",
        "notes": notes,
        "qc_flags": flags.to_str(keep_columns=COLUMNS, rename=TO_UNIFIED),
    }


def _finish(row):
    if row.qualitative:
        texts = "; ".join(dict.fromkeys(row.qualitative))
        row.values["comments"] = f"{row.values['comments']} | {texts}" if row.values["comments"] else texts
    row.values["qc_flags"] = row.flags.to_str(keep_columns=FAMILY_COLUMNS)
    return row.values


# ---------- ACME CFI-G (PSI-159) ----------

def _cfig_outcome(row, hot, end, comments):
    """Règles de docs/regles_valeurs_manquantes.md (correspondance des issues)."""
    if hot == "yes":
        return {"SE": "extinguished", "FT": "burned"}.get(end)
    if hot == "flash":
        return "extinguished"
    if hot == "no":
        if row.values["cool_flame"]:
            return "other"
        if end == "FT":
            row.flag("outcome", "a_verifier")
        return "no_ignition"
    return None


def _cool_flame(column_value, comments):
    text = f"{column_value} {comments}".lower()
    if column_value.lower().startswith("yes") or "cool flame!" in text or "direct cool" in text or "hot to cool" in text:
        return True
    if column_value.lower().startswith("no") or "no cool flame" in text:
        return False
    return None


def build_cfig():
    meta = psi_index()["PSI-159"]
    family, unified = [], []
    for kind in ("Normal", "Inverse"):
        path = experimental_table("PSI-159", kind)
        for _, r in read_raw_csv(path).iterrows():
            row = Row(r, "ACME CFI-G", "PSI-159", path)
            v = row.values
            v["test_id"] = r["Test"].replace(" ", "")
            v["test_date"], v["gmt_day"] = _acme_date(v["test_id"])
            v["session"] = v["test_id"][:5]
            v["flame_type"] = kind.lower()
            v["fuel_label_raw"] = r["Fuel"]
            v["fuel"], bottle = _fuel(r["Fuel"])
            row.num("approx p (bar)", "pressure_kpa", scale=100)
            row.flag("pressure_kpa", "approx")
            if kind == "Normal":
                row.num("XO2 before test", "x_o2")
                row.num("XO2  after test", "x_o2_final")
                row.num("Xf", "x_fuel")
                row.num("mHC (mg/s)", "hc_rate_mg_s")
                row.num("Peak burner T (C )", "peak_burner_T_K", offset=273.15)
            else:
                row.num("Xf  before test", "x_fuel")
                row.num("Xf  after test", "x_fuel_final")
                row.num("XO2", "x_o2")
                row.num("HC burnrate (mg/s)", "hc_rate_mg_s")
                row.num("O2 flow rate (mg/s)", "o2_rate_mg_s")
                row.num("Peak burner Temp (C)", "peak_burner_T_K", offset=273.15)
            if v["x_fuel"] == 0 and v["hc_rate_mg_s"] == 0:  # pas de combustible : essai sans flamme possible
                row.flag("x_fuel", "a_verifier")
            row.num("Tad (K)", "t_ad_K")
            row.num("Zst", "z_st")
            v["tfp"] = {"yes": True, "no": False}.get(r["TFP"].lower())
            hot = r["Hot ignition"].lower() or None
            end = r[[c for c in r.index if c.lower().startswith("self")][0]] or None
            v["hot_ignition_raw"], v["end_mode_raw"] = hot, end
            v["comments"] = r["Comments"] or None
            v["cool_flame"] = _cool_flame(r.get("Cool flame?", ""), r["Comments"])
            burn = row.num("burn time (sec)", "burn_time_s")
            if hot == "no":
                if burn is None:  # pas d'allumage chaud : durée de flamme chaude nulle
                    v["burn_time_s"] = 0.0
                row.flag("burn_time_s", "sans_allumage_chaud")
            color = r.get("Color", "").lower()
            v["flame_color"] = color if color not in ("", "-") else None
            v["outcome"] = _cfig_outcome(row, hot, end, r["Comments"])

            notes = f"flamme {kind.lower()} ; Hot ignition: {r['Hot ignition']} ; fin: {end or '-'}"
            if kind == "Inverse":
                notes += " ; o2_percent = O2 du jet oxydant (la chambre contient le combustible)"
            if bottle:
                notes += f" ; bouteille {r['Fuel']}"
            unified.append(_unified(row, meta, f"brûleur sphérique, flamme {kind.lower()}", notes))
            family.append(_finish(row))
    return family, unified, []


# ---------- ACME Flame Design (PSI-10) ----------

def build_flame_design():
    meta = psi_index()["PSI-10"]
    family, unified = [], []
    for kind in ("Normal", "Inverse"):
        path = experimental_table("PSI-10", kind)
        for _, r in read_raw_csv(path).iterrows():
            row = Row(r, "ACME Flame Design", "PSI-10", path)
            v = row.values
            v["test_id"] = r["Test"].replace(" ", "")
            v["test_date"], v["gmt_day"] = _acme_date(v["test_id"])
            v["session"] = v["test_id"][:5]
            v["flame_type"] = kind.lower()
            row.num("pinit (atm)", "pressure_kpa", scale=ATM_TO_KPA)
            row.num("pfinal (atm)", "pressure_final_kpa", scale=ATM_TO_KPA)
            row.num("mN2 (mg/s)", "n2_rate_mg_s")
            row.num("mtot (mg/s)", "total_rate_mg_s")
            row.num("mean Zst", "z_st")
            row.num("Tad (K)", "t_ad_K")
            if kind == "Normal":
                v["fuel_label_raw"] = r["Fuel"]
                v["fuel"], _ = _fuel(r["Fuel"])
                row.num("Xfuel", "x_fuel")
                row.num("mfuel (mg/s)", "fuel_rate_mg_s")
                row.num("XO2 (init)", "x_o2")
                row.num("XO2 (final)", "x_o2_final")
            else:  # combustible dans la chambre : éthylène (colonnes « XC2H4 »)
                v["fuel_label_raw"] = "C2H4 (chambre)"
                v["fuel"] = "ethylene"
                row.num("XC2H4 initial", "x_fuel")
                row.num("XC2H4 final", "x_fuel_final")
                row.num("XO2", "x_o2")
                row.num("mO2 (mg/s)", "o2_rate_mg_s")
            notes = f"flamme {kind.lower()} ; pas d'issue enregistrée dans la table (limites de suie et d'extinction étudiées)"
            if kind == "Inverse":
                notes += " ; o2_percent = O2 du jet oxydant"
            unified.append(_unified(row, meta, f"brûleur sphérique, flamme {kind.lower()}", notes))
            family.append(_finish(row))
    return family, unified, []


# ---------- SPICE (PSI-107) ----------

def build_spice():
    meta = psi_index()["PSI-107"]
    path = experimental_table("PSI-107")
    raw = read_raw_csv(path)
    data_cols = [c for c in raw.columns if c != "source_line"]
    duplicate = raw.duplicated(data_cols)
    family, unified, skipped = [], [], []
    for (_, r), is_copy in zip(raw.iterrows(), duplicate):
        if is_copy:  # copie exacte de la ligne précédente (mêmes heures, mêmes débits)
            skipped.append({"psi_id": "PSI-107", "source_file": path.name, "source_line": r["source_line"], "reason": "copie_exacte"})
            continue
        row = Row(r, "SPICE", "PSI-107", path)
        v = row.values
        v["gmt_day"] = int(r["GMT date"]) if r["GMT date"].isdigit() else None
        v["test_id"] = f"GMT{r['GMT date']}-L{r['source_line']}"
        ignition = r["GMT ignition"] if re.match(r"\d", r["GMT ignition"]) else None  # « Ku LOS » = perte de signal
        v["session"] = f"GMT{r['GMT date']} {ignition}" if ignition else f"GMT{r['GMT date']} L{r['source_line']}"
        v["flame_type"] = "coflow"
        v["fuel_label_raw"] = r["Fuel"]
        v["fuel"], v["x_fuel"] = _fuel(r["Fuel"])
        if v["x_fuel"] is None:
            v["x_fuel"] = 1.0  # combustible pur : pas de pourcentage dans le libellé
        row.num("Nozzle (mm)", "nozzle_mm")
        row.num("Fuel Rate (sccm)", "fuel_rate_sccm")
        row.num("Fuel Rate (mg/s)", "fuel_rate_mg_s")
        hc = row.num("HC Fuel Rate (mg/s)", "hc_rate_mg_s")
        if hc == 0 and v["fuel_rate_mg_s"] is None:  # 0 sur les lignes en perte de signal
            v["hc_rate_mg_s"] = None
            row.flag("hc_rate_mg_s", "zero_fictif")
        air = row.num("Air Rate (cm/s)", "coflow_cm_s")
        if air is not None and air < 0:  # vitesse négative impossible
            v["coflow_cm_s"] = None
            row.flag("coflow_cm_s", "incoherent")
        # Co-courant d'air de la cabine dans la MSG : O2 et pression nominaux
        v["x_o2"] = 0.21
        row.flag("x_o2", "nominal")
        v["pressure_kpa"] = ATM_TO_KPA
        row.flag("pressure_kpa", "nominal")
        notes = f"co-courant d'air (O2 nominal 21 %) ; {MSG_PRESSURE_NOTE}"
        if v["fuel_label_raw"] and "%" in v["fuel_label_raw"]:
            notes += f" ; {r['Fuel']} : diluant non précisé dans la source"
        if ignition is None:
            notes += " ; heures non disponibles (perte de signal Ku LOS)"
        unified.append(_unified(row, meta, f"jet co-courant, buse {r['Nozzle (mm)']} mm", notes))
        family.append(_finish(row))
    return family, unified, skipped


def build():
    """Toutes les expériences de la famille. Renvoie (table famille, lignes unifiées, lignes écartées)."""
    family, unified, skipped = [], [], []
    for builder in (build_cfig, build_flame_design, build_spice):
        f, u, s = builder()
        family += f
        unified += u
        skipped += s
    family_df = pd.DataFrame(family)[list(FAMILY_COLUMNS)].astype({k: v[0] for k, v in FAMILY_COLUMNS.items()})
    return family_df, pd.DataFrame(unified), skipped
