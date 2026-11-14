"""Famille « solides » : BASS (PSI-26), BASS-II (PSI-25), Saffire I, II, III (PSI-98, 99, 100).

Sources et règles : docs/regles_valeurs_manquantes.md. En bref :
- BASS : table PSI enrichie par la matrice « As Run » (O2, pression, débit, observations), jointure sur (n° As Run, n° d'essai) ;
- BASS-II : pression nominale 1 atm ; tiges = PMMA coulé (NASA/TM-20210011385 p. 47) ; « Air display » = anémomètre en cm/s (p. 21) ;
- BASS / BASS-II : l'issue et le sens de l'écoulement viennent de data/processed/annotations/bass_outcomes.csv (saisie manuelle) ;
- Saffire-II : les colonnes 1g deviennent des lignes séparées (gravity = 1g).
"""

import csv
import re

import pandas as pd

from src.common.schema import COLUMNS, OUTCOMES
from src.data.common import ATM_TO_KPA, PROCESSED, RAW_PSI, Row as _Row, experimental_table, psi_index, read_raw_csv, us_date_to_iso

BASS2_REPORT = "NASA/TM-20210011385"
SAFFIRE_PAPER = "NTRS 20170001636 (Table 1)"
BASS_DRAWINGS = "plans BASS (PSI-26, Engineering Documents : PMMA.Spherical.Section, Blk.PMMA.Rod)"

FAMILY_COLUMNS = {
    "experiment": ("string", "", "BASS, BASS-II, Saffire-I, Saffire-II, Saffire-III"),
    "psi_id": ("string", "", "Investigation PSI"),
    "test_id": ("string", "", "BASS : « AR<n° As Run>-T<n° essai> » ; BASS-II : n° d'essai (B1, O3a...) ; Saffire : n° d'échantillon (+ « -1g » pour les essais au sol)"),
    "session": ("string", "", "Groupe pour la validation croisée : jour d'essai (BASS, BASS-II) ou vol (Saffire)"),
    "test_date": ("string", "AAAA-MM-JJ", "Date de l'essai"),
    "pi": ("string", "", "Chercheur principal responsable de l'essai (BASS-II)"),
    "sample_no": ("string", "", "Numéro d'échantillon"),
    "material": ("string", "", "pmma, sibal (tissu 75 % coton / 25 % fibre de verre), nomex, ultem, silicone, paraffin wax, japan wax, wax, pmma+nomex"),
    "material_raw": ("string", "", "Description d'origine de l'échantillon"),
    "geometry": ("string", "", "flat sample, film, slab, rod, sphere, spherical section, candle, fabric, structured sample"),
    "thickness_mm": ("Float64", "mm", "Épaisseur"),
    "width_cm": ("Float64", "cm", "Largeur"),
    "length_cm": ("Float64", "cm", "Longueur (Saffire)"),
    "diameter_mm": ("Float64", "mm", "Diamètre (tiges, sphères)"),
    "color": ("string", "", "black / clear (PMMA)"),
    "sides_burning": ("Int64", "", "Échantillon allumé sur 1 ou 2 faces (« 1 sided »)"),
    "flow_direction": ("string", "", "opposed / concurrent / stagnation (bougies) ; BASS-II : annexe A du rapport"),
    "flow_cm_s": ("Float64", "cm/s", "Vitesse d'air si une seule valeur ; vide si rampe (voir flow_min / flow_max)"),
    "flow_min_cm_s": ("Float64", "cm/s", "Plus petite vitesse d'air affichée pendant l'essai (hors réglages en « pot ») ; "
                                         "PAS le débit d'extinction (voir extinction_*)"),
    "flow_max_cm_s": ("Float64", "cm/s", "Plus grande vitesse d'air affichée pendant l'essai"),
    "extinction_mode": ("string", "", "Essais éteints : low_flow (en baissant le débit), blowoff (soufflage, débit élevé), "
                                      "flow_off (débit coupé volontairement), brief_flame (flamme brève qui ne s'établit pas), "
                                      "steady_flow (éteinte à vitesse constante) ; vide si le texte ne le dit pas"),
    "extinction_flow_cm_s": ("Float64", "cm/s", "Vitesse d'air à l'extinction, seulement si écrite en cm/s "
                                                "(« 5 3 2 ext », « 10 blowoff », « extinguished 8 cm/s ») ; marque deduit"),
    "extinction_pot": ("Float64", "réglage", "Réglage du potentiomètre du ventilateur à l'extinction (« at pot 0.35 ») ; "
                                             "non converti en cm/s : calibration variable selon le jour et absente sous 1–2"),
    "flow_raw": ("string", "", "Vitesse d'air telle qu'écrite (« Air display », « Air Flow »)"),
    "fan_raw": ("string", "", "Réglage du ventilateur tel qu'écrit (« Fan display », potentiomètre)"),
    "flow_restrictor": ("string", "", "Restricteur de débit (BASS, BASS-II)"),
    "x_o2": ("Float64", "fraction molaire", "O2 initial"),
    "x_o2_final": ("Float64", "fraction molaire", "O2 final (BASS-II)"),
    "pressure_kpa": ("Float64", "kPa", "Pression (BASS : mesurée ; BASS-II : nominale 1 atm ; Saffire : non donnée)"),
    "co2_initial_pct": ("Float64", "% vol", "CO2 initial (BASS-II)"),
    "co2_final_pct": ("Float64", "% vol", "CO2 final (BASS-II)"),
    "co2_mmhg": ("Float64", "mmHg", "CO2 (BASS)"),
    "co_initial_ppm": ("Float64", "ppm", "CO initial (BASS-II)"),
    "co_final_ppm": ("Float64", "ppm", "CO final (BASS-II)"),
    "ignition_power_W": ("Float64", "W", "Puissance de l'allumeur (Saffire)"),
    "ignition_time_s": ("Float64", "s", "Durée d'allumage (Saffire)"),
    "burn_time_s": ("Float64", "s", "Durée de combustion (Saffire)"),
    "burn_length_cm": ("Float64", "cm", "Longueur brûlée (Saffire-II)"),
    "burn_complete": ("boolean", "", "Échantillon entièrement brûlé (« Complete »)"),
    "spread_rate_mm_s": ("Float64", "mm/s", "Vitesse de propagation (Saffire-II)"),
    "spread_mode": ("string", "", "Mode de propagation noté (ex. « acceleratory » : pas de vitesse unique)"),
    "observations": ("string", "", "Observations d'origine (BASS : matrice As Run ; BASS-II : annexe A du rapport) et textes qualitatifs"),
    "outcome": ("string", "", "Issue normalisée ; BASS / BASS-II : depuis annotations/bass_outcomes.csv"),
    "gravity": ("string", "", "micro (vol) ou 1g (essais au sol de Saffire-II)"),
    "source_file": ("string", "", "Fichier PSI d'origine"),
    "source_line": ("Int64", "", "Ligne dans le fichier d'origine (en-tête = 1)"),
    "qc_flags": ("string", "", "Marques qualité « colonne:motif;... »"),
}

TO_UNIFIED = {"x_o2": "o2_percent"}
ROD_DIAMETERS_MM = {"1/4": 6.35, "3/8": 9.525, "1/2": 12.7, "0.25": 6.35, "0.375": 9.525, "0.5": 12.7}


ROUND_SHAPES = ("rod", "sphere", "spherical section", "candle")


def Row(raw, experiment, psi_id, path):
    return _Row(raw, FAMILY_COLUMNS, experiment, psi_id, path)


def flag_shape(row):
    """Dimensions sans objet selon la géométrie : pas de largeur / épaisseur pour une tige ou une sphère,
    pas de diamètre pour un échantillon plat."""
    v = row.values
    if v["geometry"] in ROUND_SHAPES:
        for col in ("width_cm", "thickness_mm"):
            if v[col] is None:
                row.flag(col, "sans_objet")
    elif v["geometry"] and v["diameter_mm"] is None:
        row.flag("diameter_mm", "sans_objet")


# ---------- Lecture des descriptions ----------

def parse_sample(desc, row):
    """Matériau, géométrie et dimensions à partir d'une description d'échantillon BASS / BASS-II."""
    v, d = row.values, re.sub(r"\s+", " ", desc.lower()).replace("parrafin", "paraffin").replace("blac ", "black ")
    v["material_raw"] = desc or None
    if "sibal" in d:
        v["material"], v["geometry"] = "sibal", "fabric"
    elif "nomex" in d:
        v["material"], v["geometry"] = "nomex", "fabric"
    elif "ultem" in d:
        v["material"], v["geometry"] = "ultem", "sheet"
    elif "wax" in d or "candle" in d:
        v["material"] = "japan wax" if "japan" in d else "paraffin wax" if "paraffin" in d else ("wax" if "wax" in d else None)
        v["geometry"] = "candle" if "candle" in d else "slab"
    else:  # PMMA : explicite, ou tige / sphère / film d'après les documents NASA
        v["material"] = "pmma"
        if "pmma" not in d:
            row.flag("material", "doc")
        v["geometry"] = ("rod" if "rod" in d else "spherical section" if "spherical section" in d
                         else "sphere" if "sphere" in d else "slab" if "slab" in d
                         else "film" if "film" in d or "micron" in d else "flat sample")
    # « candle » sans précision : matériau inconnu, laissé vide (vrai manquant)

    rod = re.search(r"(1/4|3/8|1/2|0\.25|0\.375|0\.5)(?=\s*(\"|in|rod|black|clear))", d)
    if v["geometry"] == "rod" and rod:
        v["diameter_mm"] = ROD_DIAMETERS_MM[rod.group(1)]
    sphere = re.search(r"(\d+(?:\.\d+)?) ?cm", d)
    if v["geometry"] in ("sphere", "spherical section") and sphere:
        v["diameter_mm"] = float(sphere.group(1)) * 10
    elif sphere and v["geometry"] not in ("candle", "rod"):
        v["width_cm"] = float(sphere.group(1))
    micron = re.search(r"(\d+(?:\.\d+)?) ?micron", d)
    mm = re.search(r"(\d*\.?\d+) ?mm", d)
    if micron:
        v["thickness_mm"] = float(micron.group(1)) / 1000
    elif mm:
        v["thickness_mm"] = float(mm.group(1))
    v["color"] = "black" if "black" in d else "clear" if "clear" in d else None
    sides = re.search(r"([12]) ?sided", d)
    v["sides_burning"] = int(sides.group(1)) if sides else None
    if "opposed" in d or "oppsed" in d:
        v["flow_direction"] = "opposed"


def parse_flow(text, row, target="flow_cm_s"):
    """Vitesse d'air affichée (cm/s). « 10, 5, 3 » -> min 3, max 10, rampe ; « 5 » -> 5.

    Les réglages du potentiomètre ne sont pas des vitesses : « 5 3 pot 0.4 » (pot devant), « 3 0.5 pot 0.4 pot »
    (pot derrière), « 5 pots 0.4 0.36 0.32 » (tous les nombres qui suivent « pots »), « (pot .9, .5) ».
    « <1 » compte pour 1 dans le minimum (marque approx).
    """
    v = row.values
    v["flow_raw"] = text or None
    t = re.sub(r"\([^)]*\)", " ", (text or "").lower())
    tokens = re.findall(r"[a-z]+|<?\s*\d*\.?\d+\??", t)
    is_num = lambda tok: bool(re.fullmatch(r"<?\s*\d*\.?\d+\??", tok))
    pot = set()
    for i, tok in enumerate(tokens):
        if tok == "pots":
            j = i + 1
            while j < len(tokens) and is_num(tokens[j]):
                pot.add(j)
                j += 1
        elif tok == "pot":
            after = i + 1 < len(tokens) and is_num(tokens[i + 1])
            after_is_suffixed = i + 2 < len(tokens) and tokens[i + 2] == "pot"
            if after and not after_is_suffixed:
                pot.add(i + 1)
            elif i > 0 and is_num(tokens[i - 1]):
                pot.add(i - 1)
    numbers, words, below = [], [], False
    for i, tok in enumerate(tokens):
        if i in pot or tok in ("pot", "pots"):
            continue
        if is_num(tok):
            below = below or tok.startswith("<")
            numbers.append(float(tok.lstrip("< ").rstrip("?")))
        else:
            words.append(tok)
    if not numbers:
        if text:
            row.flag(target, "qualitatif")
        return
    v["flow_min_cm_s"], v["flow_max_cm_s"] = min(numbers), max(numbers)
    if below:
        row.flag("flow_min_cm_s", "approx")  # « <1 » : borne haute
    if len(numbers) > 1:
        row.flag(target, "rampe")
    elif words or below:  # « 3 ign », « 10 max » : une valeur accompagnée de texte
        row.flag(target, "qualitatif")
    else:
        v[target] = numbers[0]
    if "?" in t:
        row.flag(target, "approx")


# « 5 3 2 ext », « 10 blowoff », « out .275 » (flamme éteinte au réglage 0.275) ; « no ign » = pas d'allumage
EXTINCTION_WORDS = re.compile(r"(?<![a-z])(ext|extinct|extinguish|blow ?off|out(?=\s*\.?\d))")
NO_IGNITION_WORDS = re.compile(r"(?<![a-z])no ign")


def outcome_from_text(row, *texts):
    """Issue écrite en toutes lettres dans les colonnes de débit, si l'annexe n'en a pas donné."""
    joined = " ".join(t for t in texts if t).lower()
    if row.values["outcome"] is None and NO_IGNITION_WORDS.search(joined):
        row.values["outcome"] = "no_ignition"
        row.flag("outcome", "deduit")
        return "absence d'allumage notée dans les colonnes de débit"
    m = EXTINCTION_WORDS.search(joined)
    if m and row.values["outcome"] is None:
        row.values["outcome"] = "extinguished"
        row.flag("outcome", "deduit")
        return "soufflage (blowoff)" if "blow" in m.group(1) else "extinction notée dans les colonnes de débit"
    return None


# Conditions d'extinction écrites dans les textes (Air display, Fan display, observations)
OUT_WORD = r"(?:extingui\w*|extinction|went out|goes out|go out|flame out|\bout\b|died|quench\w*|blew (?:out|off)|blow ?off)"
BLOWOFF = re.compile(r"blow ?off|blew (?:out|off)")
FLOW_OFF = re.compile(r"turned (?:the )?(?:flow|fan)(?: pot)? (?:off|to 0\b)|turned off (?:the )?flow|(?:flow|fan) off\b"
                      r"|pot to 0\b|until turned (?:the )?(?:flow )?off|air (?:reading|display) (?:was )?(?:at )?zero")
LOW_FLOW = re.compile(r"decreas|reduc|turned (?:it |the )?(?:flow |pot )?down|lower(?:ed)? (?:the )?flow|low(?:er)? flow|down to"
                      r"|slow ramp|limit|after flow change|fan pot changed to")
# Flamme brève qui ne s'établit pas après l'allumage (ni soufflage, ni bas débit)
BRIEF = re.compile(r"brief(?:ly)? (?:ignition|flame|flash)|flash|no sustained|would not (?:sustain|stay lit)|no joy on sustained"
                   r"|while the igniter was still on|before spreading beyond (?:the )?igniter|did not spread at all|only stayed lit")
POT_AT_OUT = re.compile(OUT_WORD + r"[^;.]{0,30}?\bpot(?:entiometer)?s?\b(?:\s*(?:of|=|setting|at))*\s*(\d*\.\d+|\d+(?:\.\d+)?)")
# « out immediately at 0.34 » ; « at » obligatoire (« blowoff! HCl still 0.8 » n'est pas un réglage)
NUMBER_AT_OUT = re.compile(OUT_WORD + r"[^;.\d]{0,20}?(?:\bat|just as we reached a)\s*(0?\.\d+)\b(?!\s*(?:cm|mm|%|min|s\b))")
VALUE_POT_AT_OUT = re.compile(OUT_WORD + r"[^;.]{0,40}?\bat\s*(\d*\.\d+)\s*pot\b")       # « quenched after prolonged burn at 0.4 pot »
POT_BEFORE_OUT = re.compile(r"\bpot\w*\s*(?:changed\s*)?(?:to|of|at|=)\s*(\d*\.\d+)[^;.]{0,40}?" + OUT_WORD)  # « fan pot changed to 0.6 and flame went out »
LAST_POT_OUT = re.compile(r"(\d*\.\d+)\s*(?:extinction|extinguished|flame extinguished)\b")   # « … 0.285, 0.28 extinction finally »
CMS_AT_OUT = re.compile(OUT_WORD + r"[^;.]{0,40}?(\d+(?:\.\d+)?)\s*cm/s")
DISPLAY_THEN_OUT = re.compile(r"(\d*\.?\d+)\s*(?:ext|blow ?off)\b")  # « 5 3 2 ext » : dernière vitesse affichée


def extinction_details(row):
    """Mode, réglage du potentiomètre et vitesse d'air à l'extinction, quand le texte de la source les donne.
    Rien n'est converti : un réglage « pot » reste un réglage (calibration du ventilateur non fiable sous 1–2)."""
    from src.data.extract_bass2_appendix import NEGATIONS  # « did not blowoff », « no blowoff attained »

    v = row.values
    if v["outcome"] != "extinguished":
        return
    flow_text = (v["flow_raw"] or "").lower()
    text = NEGATIONS.sub(" ", " ; ".join(t for t in (v["flow_raw"], v["fan_raw"], v["observations"]) if t).lower())
    # Plusieurs réglages cités (« oscillating at 0.36, out immediately at 0.34 ») : le dernier est celui de l'extinction
    patterns = [POT_AT_OUT, VALUE_POT_AT_OUT, NUMBER_AT_OUT, POT_BEFORE_OUT] + ([LAST_POT_OUT] if "pot" in text else [])
    found = [m for p in patterns for m in p.finditer(text)]
    pot = max(found, key=lambda m: m.end()) if found else None
    if pot:
        v["extinction_pot"] = float(pot.group(1))
        row.flag("extinction_pot", "deduit")
    cms = CMS_AT_OUT.search(text)
    shown = DISPLAY_THEN_OUT.search(flow_text)
    if cms:
        v["extinction_flow_cm_s"] = float(cms.group(1))
    elif shown and not re.search(r"\b0\s*ext", flow_text):
        v["extinction_flow_cm_s"] = float(shown.group(1))
    if v["extinction_flow_cm_s"] is not None:
        row.flag("extinction_flow_cm_s", "deduit")

    ext_flow, top = v["extinction_flow_cm_s"], v["flow_max_cm_s"]
    if BLOWOFF.search(text):
        v["extinction_mode"] = "blowoff"
    elif FLOW_OFF.search(text) or re.search(r"\b0\s*ext", flow_text):
        v["extinction_mode"] = "flow_off"
    elif BRIEF.search(text):
        v["extinction_mode"] = "brief_flame"
    elif LOW_FLOW.search(text) or pot or (shown and ext_flow is not None):
        v["extinction_mode"] = "low_flow"
    elif ext_flow is not None and top is not None and ext_flow < top:
        v["extinction_mode"] = "low_flow"      # éteinte à une vitesse plus basse que la plus haute de l'essai
    elif ext_flow is not None and v["flow_min_cm_s"] == top:
        v["extinction_mode"] = "steady_flow"   # une seule vitesse pendant tout l'essai
    if v["extinction_mode"]:
        row.flag("extinction_mode", "deduit")


def with_unit(text):
    """« 20 cm/s » -> (20, None) ; « ~ 21.5 » -> (21.5, 'approx') ; « 22.1 to 22.0 » -> (22.05, 'approx') ;
    texte -> (None, 'qualitatif') ; vide -> (None, None)."""
    t = (text or "").strip().lower()
    if not t:
        return None, None
    rng = re.fullmatch(r"(\d*\.?\d+)\s*(?:-|to)\s*(\d*\.?\d+)\s*[a-z/%]*", t)
    if rng:
        return round((float(rng.group(1)) + float(rng.group(2))) / 2, 4), "approx"
    m = re.fullmatch(r"(~)?\s*(\d*\.?\d+)\s*(mm/s|cm/s|cm|mm|w|s)?", t)
    if m:
        return float(m.group(2)), "approx" if m.group(1) else None
    m = re.fullmatch(r"~\s*(\d*\.?\d+)\s*(cm|mm)?\s*\(.*\)", t)  # « ~ 10 cm (note 3) »
    if m:
        return float(m.group(1)), "approx"
    return None, "qualitatif"


def set_unit(row, column, text, scale=1.0):
    value, reason = with_unit(text)
    if reason == "qualitatif":
        row.flag(column, "qualitatif")
        row.qualitative.append(f"{column} = {text}")
    elif reason:
        row.flag(column, reason)
    row.values[column] = round(value * scale, 6) if value is not None else None
    return value


ANNOTATION_FILES = (  # du moins prioritaire au plus prioritaire
    ("bass2_appendix.csv", True),   # extrait automatiquement de l'annexe A (src/data/extract_bass2_appendix.py)
    ("bass_outcomes.csv", False),   # saisies manuelles : remplacent l'extraction automatique
)


def load_annotations():
    """Issue, sens d'écoulement et observations BASS / BASS-II, avec leur page. Clé : (expérience, n° d'essai)."""
    merged = {}
    for name, automatic in ANNOTATION_FILES:
        path = PROCESSED / "annotations" / name
        if not path.exists():
            continue
        with open(path, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if not r.get("test_id"):
                    continue
                if r["outcome"] and r["outcome"] not in OUTCOMES:
                    raise ValueError(f"{name} : issue « {r['outcome']} » non autorisée ({r['experiment']} {r['test_id']})")
                current = merged.setdefault((r["experiment"], r["test_id"]), {})
                for field in ("outcome", "flow_direction", "note"):
                    if r.get(field):
                        current[field] = r[field]
                        current[f"{field}_auto"] = automatic
                        current[f"{field}_source"] = f"{r['source_doc']} p. {r['source_page']}"
    return merged


def apply_annotation(row, annotations):
    """Applique une annotation ; renvoie la note de source (ou None). Issue extraite automatiquement : marque deduit."""
    a = annotations.get((row.values["experiment"], row.values["test_id"]))
    if not a:
        return None
    sources = set()
    if a.get("outcome"):
        row.values["outcome"] = a["outcome"]
        row.flag("outcome", "deduit" if a["outcome_auto"] else "doc")
        sources.add(a["outcome_source"])
    if a.get("flow_direction"):
        row.values["flow_direction"] = a["flow_direction"]
        row.flag("flow_direction", "doc")
        sources.add(a["flow_direction_source"])
    if a.get("note"):
        row.values["observations"] = a["note"]
        sources.add(a["note_source"])
    return "annexe / annotation : " + ", ".join(sorted(sources)) if sources else None


# ---------- Sortie unifiée ----------

def _unified(row, meta, notes):
    v = row.values
    row.flag("burning_rate", "sans_objet")  # constante K : notion de gouttelette
    o2 = v["x_o2"]
    return {
        "experiment": v["experiment"], "psi_id": v["psi_id"], "doi": meta["doi"], "test_id": v["test_id"],
        "fuel_type": "solid", "material": v["material"], "geometry": v["geometry"],
        "o2_percent": round(o2 * 100, 3) if o2 is not None else None,
        "pressure_kpa": v["pressure_kpa"], "flow_cm_s": v["flow_cm_s"], "gravity": v["gravity"],
        "outcome": v["outcome"], "spread_rate_mm_s": v["spread_rate_mm_s"], "burning_rate": None,
        "source_doc": v["source_file"], "source_page": f"ligne {v['source_line']}",
        "notes": "; ".join(n for n in notes if n) or None,
        "qc_flags": row.flags.to_str(keep_columns=COLUMNS, rename=TO_UNIFIED),
    }


# ---------- BASS (PSI-26) ----------

def _clean_id(value):
    return re.sub(r"\.0$", "", str(value).strip()) if value is not None and str(value) != "nan" else ""


def build_bass(annotations):
    meta = psi_index()["PSI-26"]
    path = experimental_table("PSI-26")
    table = read_raw_csv(path)
    xlsx = next(RAW_PSI.glob("PSI-26_*/documents/*As Run_Test Matrix.xlsx"))
    asrun = pd.read_excel(xlsx, sheet_name="as run matrix", header=None, dtype=str).iloc[3:].dropna(how="all")
    asrun.columns = range(asrun.shape[1])
    asrun = {(_clean_id(r[2]), _clean_id(r[3])): r for _, r in asrun.iterrows()}

    family, unified, skipped = [], [], []
    for _, r in table.iterrows():
        if not r["Test #"]:
            skipped.append({"psi_id": "PSI-26", "source_file": path.name, "source_line": r["source_line"],
                            "reason": f"pas_un_essai ({r['Fuel Sample Material']})"})
            continue
        row = Row(r, "BASS", "PSI-26", path)
        v = row.values
        key = (_clean_id(r["As Run Test #"]), _clean_id(r["Test #"]))
        v["test_id"] = f"AR{key[0]}-T{key[1]}"
        v["test_date"] = v["session"] = us_date_to_iso(r["Date"])
        v["sample_no"] = _clean_id(r["Sample #"]) or None
        parse_sample(r["Fuel Sample Material"], row)
        x = asrun.get(key)
        if x is not None:  # matrice « As Run » : conditions mesurées
            cell = lambda i: str(x[i]).strip() if str(x[i]) != "nan" else ""
            row.num("O2 % by volume", "x_o2", text=cell(26))
            row.num("pressure, atm", "pressure_kpa", scale=ATM_TO_KPA, text=cell(27))
            row.num("CO2, mm Hg", "co2_mmhg", text=cell(28))
            parse_flow(x[10] if str(x[10]) != "nan" else "", row)
            v["fan_raw"] = x[9] if str(x[9]) != "nan" else None
            v["flow_restrictor"] = _clean_id(x[7]) or None
            v["observations"] = str(x[29]).strip() if str(x[29]) != "nan" else None
        note = apply_annotation(row, annotations) or outcome_from_text(row, v["flow_raw"], v["fan_raw"])
        notes = [f"échantillon : {r['Fuel Sample Material']}", "conditions : matrice As Run (PSI-26)", note]
        if "material:doc" in row.flags.items:
            notes.append(f"matériau PMMA : {BASS_DRAWINGS}")
        extinction_details(row)
        flag_shape(row)
        unified.append(_unified(row, meta, notes))
        family.append(row.finish("observations"))
    return family, unified, skipped


# ---------- BASS-II (PSI-25) ----------

def build_bass2(annotations):
    meta = psi_index()["PSI-25"]
    path = experimental_table("PSI-25")
    family, unified = [], []
    for _, r in read_raw_csv(path).iterrows():
        row = Row(r, "BASS-II", "PSI-25", path)
        v = row.values
        v["test_id"] = r["Test #"]
        v["test_date"] = v["session"] = us_date_to_iso(r["Date"])
        v["pi"] = r["PI"] or None
        v["sample_no"] = r["Sample #"] or None
        parse_sample(r["Fuel Sample Material"], row)
        parse_flow(r["Air display"], row)
        v["fan_raw"] = r["Fan display"] or None
        v["flow_restrictor"] = r["Flow restrictor"] or None
        o2 = row.num("Calibrated  initial O2 % by vol", "x_o2", scale=0.01)
        o2f = row.num("Calibrated final O2 % by vol", "x_o2_final", scale=0.01)
        if o2 is not None and o2f is not None and o2f < 0.10:  # chute impossible dans la boîte à gants
            row.flag("x_o2_final", "incoherent")
        row.num("Initial CO2 % by vol", "co2_initial_pct")
        row.num("Final CO2 % by vol", "co2_final_pct")
        for col, target in (("Initial CO (ppm)", "co_initial_ppm"), ("Final CO (ppm)", "co_final_ppm")):
            if (row.num(col, target) or 0) < 0:  # dérive du capteur, valeur gardée
                row.flag(target, "incoherent")
        v["pressure_kpa"] = ATM_TO_KPA
        row.flag("pressure_kpa", "nominal")
        note = apply_annotation(row, annotations)
        deduced = outcome_from_text(row, r["Air display"], r["Fan display"])  # seulement si l'annexe n'a rien donné
        notes = [f"échantillon : {r['Fuel Sample Material']}", f"pression nominale 1 atm ({BASS2_REPORT} p. 11, 41)",
                 note, deduced, None if note else "absent de l'annexe A du rapport"]
        if "material:doc" in row.flags.items:
            notes.append(f"matériau PMMA : {BASS2_REPORT} p. 47 (tiges de PMMA coulé) / {BASS_DRAWINGS}")
        extinction_details(row)
        flag_shape(row)
        unified.append(_unified(row, meta, notes))
        family.append(row.finish("observations"))
    return family, unified, []


# ---------- Saffire I, II, III (PSI-98, 99, 100) ----------

SAFFIRE_MATERIALS = {"sibal fabric": "sibal", "cotton-fiberglass (sibal)": "sibal", "silicone": "silicone",
                     "pmma & nomex": "pmma+nomex", "pmma": "pmma"}
# Matériaux absents de la table Saffire-II, donnés par NTRS 20170001636 (Table 1)
SAFFIRE2_MISSING_MATERIAL = {"2-6": ("sibal", "fabric"), "2-9": ("pmma", "flat sample")}
SAFFIRE2_STRUCTURED = "2-8"  # « Structured PMMA » (S8), épaisseur « See Fig. 5 »


def _col(r, *starts):
    for c in r.index:
        if any(c.lower().startswith(s.lower()) for s in starts):
            return r[c]
    return ""


def _saffire_outcome(length, complete, length_reason):
    if complete or (length is not None and length > 0):
        return "burned"
    if length == 0 or length_reason == "qualitatif":
        return "other"  # pas de propagation (longueur brûlée ~ 0) ou cas mixte PMMA / Nomex
    return None


def build_saffire():
    family, unified, skipped = [], [], []
    for psi_id, name in (("PSI-98", "Saffire-I"), ("PSI-99", "Saffire-II"), ("PSI-100", "Saffire-III")):
        meta = psi_index()[psi_id]
        path = experimental_table(psi_id)
        table = read_raw_csv(path)
        notes_text = {m.group(1): s for s in table.iloc[:, 0] for m in [re.match(r"(Note \d)", s)] if m}
        for _, r in table.iterrows():
            sample = r.iloc[0]
            material_raw = _col(r, "Material")
            if sample.startswith("Note"):
                skipped.append({"psi_id": psi_id, "source_file": path.name, "source_line": r["source_line"], "reason": "note_de_bas_de_tableau"})
                continue
            if "/" in sample or material_raw.lower().startswith("pre-test flow"):
                skipped.append({"psi_id": psi_id, "source_file": path.name, "source_line": r["source_line"], "reason": "visualisation_ecoulement_pre_essai"})
                continue
            row = Row(r, name, psi_id, path)
            v = row.values
            v["test_id"] = v["sample_no"] = sample
            v["session"] = name
            v["material_raw"] = material_raw or None
            v["material"] = SAFFIRE_MATERIALS.get(material_raw.lower())
            v["geometry"] = "fabric" if v["material"] == "sibal" else "flat sample"
            if not material_raw and sample in SAFFIRE2_MISSING_MATERIAL:
                v["material"], v["geometry"] = SAFFIRE2_MISSING_MATERIAL[sample]
                row.flag("material", "doc")
            if psi_id == "PSI-99" and sample == SAFFIRE2_STRUCTURED:
                v["geometry"] = "structured sample"
                row.flag("geometry", "doc")
            thickness_raw = _col(r, "Sample Thickness", "Samle Thickness")
            if psi_id in ("PSI-98", "PSI-100"):  # en-tête « cm » : 0.37 cm = 3,7 mm, irréaliste pour ce tissu (0,33 mm)
                set_unit(row, "thickness_mm", thickness_raw, scale=10)
                row.flag("thickness_mm", "incoherent")
            elif re.fullmatch(r"0\d+ mm", thickness_raw):  # « 037 mm » : décimale manquante
                v["thickness_mm"] = float("0." + thickness_raw[1:].split()[0])
                row.flag("thickness_mm", "a_verifier")
            elif thickness_raw.endswith("cm"):
                set_unit(row, "thickness_mm", thickness_raw, scale=10)
            else:
                set_unit(row, "thickness_mm", thickness_raw)
            set_unit(row, "length_cm", _col(r, "Sample Length"))
            set_unit(row, "width_cm", _col(r, "Sample Width"))
            if psi_id == "PSI-98":  # longueur 40,6 / largeur 94 : inversées par rapport au document NASA (0,4 m x 0,95 m)
                row.flag("length_cm", "a_verifier")
                row.flag("width_cm", "a_verifier")
            flow = set_unit(row, "flow_cm_s", _col(r, "Air Flow"))
            v["flow_raw"] = _col(r, "Air Flow") or None
            v["flow_min_cm_s"] = v["flow_max_cm_s"] = flow
            if psi_id == "PSI-99":  # PSI : « 20 ou 30 cm/s selon le matériau » ; table : 20 partout
                row.flag("flow_cm_s", "a_verifier")
            o2 = set_unit(row, "x_o2", _col(r, "Percent O2"), scale=0.01)
            set_unit(row, "ignition_power_W", _col(r, "Ignition Power"))
            set_unit(row, "ignition_time_s", _col(r, "Ignition Time"))
            set_unit(row, "burn_time_s", _col(r, "Burn Time"))
            direction = _col(r, "Flow Direction", "Direction").strip().lower()
            v["flow_direction"] = direction or None

            cells = " ".join(r.astype(str)).lower()
            refs = [notes_text[n] for n in notes_text if n.lower() in cells or (n == "Note 1" and o2 is not None)]
            row.qualitative += refs  # texte des notes dans observations (Note 1 : en-tête de la colonne O2)
            notes = [f"échantillon : {material_raw or v['material']}"] + refs
            if "material:doc" in row.flags.items or "geometry:doc" in row.flags.items:
                notes.append(f"matériau : {SAFFIRE_PAPER}")

            if psi_id == "PSI-99":
                ug_len_raw = _ug(r, "-g Burn Length")
                ug_spread_raw = _ug(r, "-g Spread")
                g1_len_raw, g1_spread_raw = _col(r, "1-g Burn Length"), _col(r, "1-g Spread")
                base = dict(v)
                base_flags = list(row.flags.items)
                base_qual = list(row.qualitative)

                # Vol (microgravité)
                _set_burn(row, ug_len_raw, ug_spread_raw)
                v["outcome"] = _saffire_outcome(v["burn_length_cm"], v["burn_complete"], _reason(row, "burn_length_cm"))
                flag_shape(row)
                unified.append(_unified(row, meta, notes + ["essai en vol (Cygnus)"]))
                family.append(row.finish("observations"))

                # Essai au sol (1g) : même échantillon, conditions non données dans la table
                ground = Row(r, name, psi_id, path)
                ground.values.update({k: base[k] for k in ("material", "material_raw", "geometry", "thickness_mm", "length_cm", "width_cm", "sample_no", "session")})
                ground.flags.items = [f for f in base_flags if f.split(":")[0] in ("material", "geometry", "thickness_mm", "length_cm", "width_cm")]
                ground.qualitative = [q for q in base_qual if q.split(" = ")[0] in ("thickness_mm", "length_cm", "width_cm")]
                ground.values.update(test_id=f"{sample}-1g", gravity="1g")
                _set_burn(ground, g1_len_raw, g1_spread_raw)
                ground.values["outcome"] = _saffire_outcome(ground.values["burn_length_cm"], ground.values["burn_complete"], _reason(ground, "burn_length_cm"))
                flag_shape(ground)
                ground_notes = [n for n in notes if not n.startswith("Note 1")]  # la Note 1 porte sur l'O2 du vol
                unified.append(_unified(ground, meta, ground_notes + ["essai de comparaison au sol (1g) : O2, débit et pression non donnés dans la table"]))
                family.append(ground.finish("observations"))
            else:
                if v["burn_time_s"]:
                    v["outcome"] = "burned"
                flag_shape(row)
                unified.append(_unified(row, meta, notes + ["essai en vol (Cygnus)"]))
                family.append(row.finish("observations"))
    return family, unified, skipped


def _ug(r, suffix):
    """Colonne microgravité de Saffire-II (« µ-g Burn Length », le « µ » varie selon l'encodage)."""
    for c in r.index:
        if c.endswith(suffix) or suffix in c:
            if not c.startswith("1"):
                return r[c]
    return ""


def _reason(row, column):
    for item in row.flags.items:
        col, reason = item.split(":")
        if col == column:
            return reason
    return None


def _set_burn(row, length_raw, spread_raw):
    """Longueur brûlée et vitesse de propagation Saffire-II (vol ou sol)."""
    v = row.values
    text = length_raw.strip()
    if text.lower().startswith("complete"):
        v["burn_complete"] = True
        if v["length_cm"] is not None:  # brûlé entièrement = toute la longueur de l'échantillon
            v["burn_length_cm"] = v["length_cm"]
            row.flag("burn_length_cm", "recopie")
    else:
        cleaned = re.sub(r"\((nomex|note \d)\)", "", text, flags=re.I).strip()
        if cleaned:
            set_unit(row, "burn_length_cm", cleaned)
        if cleaned != text:
            row.qualitative.append(f"burn_length_cm = {text}")
    length, burned = v["length_cm"], v["burn_length_cm"]
    if v["burn_complete"] is None and burned is not None and length is not None:
        v["burn_complete"] = burned >= length  # même ligne : longueur brûlée comparée à la longueur de l'échantillon
    s = spread_raw.strip()
    if s.lower().startswith("n/a"):
        row.flag("spread_rate_mm_s", "sans_objet")  # Nomex non allumé
    elif re.fullmatch(r"\d*\.?\d+\s*mm/s", s.lower()):
        set_unit(row, "spread_rate_mm_s", s)
    elif s.lower().startswith("note"):  # renvoi vers une note (texte dans observations)
        row.flag("spread_rate_mm_s", "qualitatif")
    elif s:
        v["spread_mode"] = s.lower()
        row.flag("spread_rate_mm_s", "qualitatif")
        row.qualitative.append(f"spread = {s}")
    elif v["burn_length_cm"] == 0:
        row.flag("spread_rate_mm_s", "sans_objet")  # pas de propagation


def build():
    """Toutes les expériences de la famille. Renvoie (table famille, lignes unifiées, lignes écartées)."""
    annotations = load_annotations()
    family, unified, skipped = [], [], []
    for f, u, s in (build_bass(annotations), build_bass2(annotations), build_saffire()):
        family += f
        unified += u
        skipped += s
    family_df = pd.DataFrame(family)[list(FAMILY_COLUMNS)].astype({k: v[0] for k, v in FAMILY_COLUMNS.items()})
    return family_df, pd.DataFrame(unified), skipped
