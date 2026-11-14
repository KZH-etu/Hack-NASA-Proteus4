"""Extrait l'annexe A du rapport BASS-II (NASA/TM-20210011385, pp. 103–113) vers
data/processed/annotations/bass2_appendix.csv : sens de l'écoulement et observations de chaque essai,
plus une issue déduite des observations quand elle y est écrite explicitement.

- Le PDF est téléchargé depuis NTRS dans data/raw/ntrs/pdf/ s'il manque.
- Les lignes du tableau sont repérées par les bordures du PDF ; le n° d'essai est le premier identifiant
  (B1, O3a...) de la ligne, les observations sont la dernière cellule.
- Issue : seulement si le texte est explicite (extinction, soufflage, absence d'allumage, combustion jusqu'au bout).
  Sinon vide : un texte qui ne parle pas d'extinction ne prouve pas que la flamme a tenu.
- Les saisies manuelles (annotations/bass_outcomes.csv) restent prioritaires dans le build.

Usage :
    python -m src.data.extract_bass2_appendix
"""

import csv
import re

import pymupdf
import requests

from src.data.common import PROCESSED, ROOT

NTRS_ID = "20210011385"
REPORT = "NASA/TM-20210011385"
PDF = ROOT / "data" / "raw" / "ntrs" / "pdf" / f"{NTRS_ID}.pdf"
PDF_URL = f"https://ntrs.nasa.gov/api/citations/{NTRS_ID}/downloads/TM-{NTRS_ID}.pdf"
APPENDIX_PDF_PAGES = range(111, 122)  # pages imprimées 103 à 113
OUT = PROCESSED / "annotations" / "bass2_appendix.csv"
COLUMNS = ["experiment", "test_id", "outcome", "flow_direction", "source_doc", "source_page", "annotator", "note"]

TEST_ID = re.compile(r"^[BFPMOT]\d+[a-z]?$")
DIRECTIONS = {"opposed": "opposed", "concurrent": "concurrent", "stagnation": "stagnation"}

# Tournures négatives retirées avant de classer : « did not blowoff », « no blowoff attained »,
# « still did not extinguish », « tried blowoff without success »
NEGATIONS = re.compile(r"(?:did not|didn't|does not|no|not|never)\s+(?:\w+\s+){0,2}?(?:blow ?off|extingui\w*|extinction)\w*"
                       r"|(?:tried|attempted) blow ?off(?: without success)?")

# Ordre important : la première règle qui correspond l'emporte.
# « burned » passe avant « extinguished » : une flamme qui s'éteint après avoir brûlé tout l'échantillon
# (« extinguishes at burnout ») n'est pas une extinction due aux conditions.
OUTCOME_RULES = [
    # Flamme qui ne tient que tant que l'allumeur est là : pas d'allumage autonome
    ("no_ignition", re.compile(r"no ignition|did not ignite|didn't ignite|failed to ignite|would not ignite|never ignited"
                               r"|no sustained flame at any flow|upon igniter removal|without igniter on")),
    ("burned", re.compile(r"burn(ed)? (to|until) (the )?end|burned (completely|entire|the entire|whole)|complete(ly)? burn|burn ?out"
                          r"|burned out|(reached|to) (the )?end of (the )?sample|whole sample|full sample length"
                          r"|steady[^;]* until turned (the )?(flow )?off")),
    ("extinguished", re.compile(r"extingui|extinction|\bext\b|blow ?off|blew off|quench|went out|flamed? out|died"
                                r"|would not sustain|not sustain|no sustained|no joy on sustained|stayed lit [^;]*less than"
                                r"|would not stay lit|blew out|blow out|go(es)? out|\bout at\b")),
]


def download_pdf():
    if PDF.exists():
        return
    PDF.parent.mkdir(parents=True, exist_ok=True)
    r = requests.get(PDF_URL, timeout=600)
    r.raise_for_status()
    PDF.write_bytes(r.content)


def classify(observation):
    text = NEGATIONS.sub(" ", observation.lower())
    for outcome, pattern in OUTCOME_RULES:
        if pattern.search(text):
            return outcome
    return None


def extract():
    doc = pymupdf.open(PDF)
    rows = []
    for n in APPENDIX_PDF_PAGES:
        page = doc[n - 1]
        words = page.get_text("words")  # x0, y0, x1, y1, mot, ...
        printed = re.search(rf"{re.escape(REPORT)}\s+(\d+)", page.get_text()).group(1)
        table = page.find_tables().tables[0]
        for row in table.rows[1:]:
            x0, y0, x1, y1 = row.bbox
            band = [w for w in words if y0 - 1 <= (w[1] + w[3]) / 2 <= y1 + 1 and x0 - 1 <= w[0] <= x1 + 1]
            ids = [w for w in band if TEST_ID.match(w[4])]
            if not ids:
                continue
            test_id = min(ids, key=lambda w: w[0])[4]
            last_cell = [c for c in row.cells if c][-1]
            observation = " ".join(w[4] for w in sorted((w for w in band if w[0] >= last_cell[0] - 1), key=lambda w: (round(w[1]), w[0])))
            found = {DIRECTIONS[w[4].lower()] for w in band if w[4].lower() in DIRECTIONS}
            rows.append({
                "experiment": "BASS-II",
                "test_id": test_id,
                "outcome": classify(observation) or "",
                "flow_direction": found.pop() if len(found) == 1 else "",
                "source_doc": REPORT,
                "source_page": f"{printed} (annexe A)",
                "annotator": "extraction automatique (src/data/extract_bass2_appendix.py)",
                "note": observation,
            })
    return rows


def main():
    download_pdf()
    rows = extract()
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    filled = lambda col: sum(1 for r in rows if r[col])
    print(f"{OUT.relative_to(ROOT)} : {len(rows)} essais, {filled('flow_direction')} sens d'écoulement, {filled('outcome')} issues")


if __name__ == "__main__":
    main()
