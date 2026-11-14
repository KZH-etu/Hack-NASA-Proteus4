"""Télécharge le corpus du RAG (documents NASA) dans data/raw/ntrs/.

Sorties (non versionnées, regénérables) :
- catalog.csv / catalog.jsonl : une ligne par document (id, titre, auteurs, année, type, n° de rapport, thèmes,
  liens, nb de pages, nb de pages avec texte) ; le .jsonl garde aussi le résumé et les mots-clés ;
- pdf/<id>.pdf : le document ;
- pages/<id>.jsonl : une ligne par page {"page": n° de page du PDF, "label": n° imprimé si le PDF le donne, "text": ...}
  -> le RAG peut citer « titre, id, page » ;
- download_log.csv : statut de chaque téléchargement.

Sources :
- PRIORITY : documents choisis à la main (rapports des expériences PSI, atmosphère d'exploration) ;
- TOPICS : recherches NTRS par thème, gardées seulement si le titre / résumé / mots-clés contiennent les mots du thème
  (la recherche NTRS seule renvoie beaucoup de hors-sujet) ;
- EXTRA : ressources du challenge hors NTRS : guide du chercheur, fiches des investigations (page « NASA Combustion
  Science » de Glenn), rapport du Sénat sur Apollo 1, pages web (Apollo 1, Apollo 13, incendie de Mir, spinoffs)
  converties en texte (web/<id>.html -> une « page »), vidéo ScienceCasts (catalogue seulement, pas de texte) ;
- TASKBOOK : fiches des projets « COMBUSTION SCIENCE » du NASA Task Book (recherche du site officiel), sans les
  coordonnées personnelles des chercheurs.
API publique : https://ntrs.nasa.gov/api/openapi/ (sans compte).

Usage :
    python -m src.rag.fetch_ntrs                     # tout (déjà téléchargé = ignoré)
    python -m src.rag.fetch_ntrs --per-topic 5       # moins de documents par thème
    python -m src.rag.fetch_ntrs --priority-only
"""

import argparse
import csv
import datetime
import json
import re
from html.parser import HTMLParser
from pathlib import Path

import pymupdf
import requests

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "raw" / "ntrs"
API = "https://ntrs.nasa.gov/api"
SPACE = r"microgravity|micro-gravity|low[- ]gravity|reduced[- ]gravity|spacecraft|space station|\bISS\b|orbit|cygnus|zero[- ]g"

# id NTRS -> thèmes (vérifiés à la main le samedi 14 novembre 2026)
PRIORITY = {
    "20150023456": ["flex"],                  # NASA/TP-2015-216046, Detailed Results from FLEX
    "20130014061": ["flex"],                  # Methanol droplet combustion in oxygen-inert environments
    "20210011385": ["bass"],                  # NASA/TM-20210011385, BASS-II Summary Report
    "20160000593": ["bass"],                  # Combustion of Solids in Microgravity: BASS-II
    "20150008961": ["bass"],                  # Microgravity flammability of PMMA rods in concurrent flow
    "20160012691": ["bass", "flammability"],  # Blowoff limits 1g vs microgravity
    "20150019858": ["bass"],                  # CSA-CP and CDM sensor readings during BASS-II
    "20220015583": ["acme"],                  # ACME: Advanced Combustion via Microgravity Experiments
    "20210021781": ["acme"],                  # Recent research on gaseous flames aboard the ISS
    "20170001636": ["saffire"],               # Saffire: objectives, development and status
    "20170000230": ["saffire"],               # Operation and development status of Saffire
    "20130013505": ["atmosphere"],            # Effects of the 8 psia / 32 % O2 atmosphere
    "20150021491": ["atmosphere"],            # Evidence report: hypobaric hypoxia from the exploration atmosphere
    "20060013463": ["atmosphere"],            # Exploration spacecraft internal atmosphere pressure and composition
    "20050185597": ["atmosphere"],            # Bounding the spacecraft atmosphere design space
    # Incidents cités dans les ressources du challenge (Apollo 1, Apollo 13)
    "19930078717": ["incidents"],             # Report of Apollo 204 (Apollo 1) Review Board
    "19700076776": ["incidents"],             # Report of Apollo 13 Review Board, final report
    "20110015690": ["incidents"],             # A case study of the failure on Apollo 13
    # Norme d'inflammabilité NASA-STD-6001 (le « Test 1 » au sol auquel BASS et Saffire comparent la microgravité)
    "20170004702": ["standards"],             # NASA-STD-6001B Test 1 upward flame propagation, sample length and MOC
    "20040084156": ["standards"],             # Most probable fire scenarios in spacecraft and habitats: why Test 1...
    "20150020937": ["standards"],             # Flammability configuration analysis for spacecraft applications (JSC-29353)
    "19720016150": ["standards", "incidents"],  # Flammability testing conducted in support of Apollo 13
    # Articles complets des spinoffs cités dans les ressources du challenge (liens hdl:2060/<id>)
    "20070018916": ["spinoff"],               # Fire Detector
    "20030005480": ["spinoff"],               # Fireman's Air Tanks
    "20030002834": ["spinoff"],               # New Technology for the Fire Attire
}

# thème -> (requête NTRS, mots exigés dans titre / résumé / mots-clés, exiger aussi un contexte spatial)
TOPICS = {
    "bass": ("Burning and Suppression of Solids microgravity", r"\bBASS\b|burning and suppression of solids", False),
    "saffire": ("Saffire spacecraft fire experiment", r"saffire", False),
    "flex": ("Flame Extinguishment Experiment droplet", r"\bFLEX\b|flame extinguishment", False),
    "acme": ("Advanced Combustion via Microgravity Experiments", r"\bACME\b|advanced combustion via microgravity", False),
    "cfi": ("cool flame droplet microgravity", r"cool flame", True),
    "same": ("smoke aerosol measurement experiment", r"\bSAME\b|smoke aerosol", True),
    "spice": ("smoke point co-flow experiment", r"smoke point|\bSPICE\b", True),
    "fire_safety": ("spacecraft fire safety", r"fire safety|fire detection|fire suppression", True),
    "flammability": ("material flammability oxygen concentration", r"flammab", True),
    "flame_spread": ("flame spread microgravity solid fuel", r"flame spread", True),
    "droplet": ("droplet combustion microgravity", r"droplet", True),
    "atmosphere": ("exploration atmosphere oxygen pressure", r"exploration atmosphere|psia|oxygen concentration|enriched", True),
    "sofie": ("Solid Fuel Ignition and Extinction", r"\bSoFIE\b|solid fuel ignition and extinction", False),
    "suppression": ("fire suppression spacecraft extinguisher", r"suppress|extinguish", True),
    "smolder": ("smoldering combustion microgravity", r"smolder|smoulder", True),
    "detection": ("spacecraft fire detection smoke", r"detect|smoke", True),
    "soot": ("soot laminar diffusion flame microgravity", r"soot", True),
    "ignition": ("piloted ignition solid microgravity", r"ignition", True),
    "incidents": ("Apollo Review Board fire oxygen", r"apollo (204|1|13)\b|review board", False),
    "slice": ("coflow laminar diffusion flame microgravity", r"co-?flow", True),
    "particles": ("smoke particle detection space station", r"particle|particulate|smoke", True),
}

# Ressources du challenge (pages et documents NASA hors NTRS). kind : pdf, html (texte de la page) ou video (pas de texte).
GLENN = "https://www.nasa.gov/wp-content/uploads/2025/07/"
GLENN_PAGE = "https://www.nasa.gov/glenn/glenn-expertise-space-exploration/physical-sciences-program/combustion-science/"
EXTRA = [
    {"id": "nasa-np-2015-10-034-jsc", "kind": "pdf", "year": "2015", "sti_type": "BOOKLET", "topics": ["overview"],
     "title": "A Researcher's Guide to: International Space Station Combustion Science (Combustion in Reduced Gravity)",
     "pdf_url": "https://www.nasa.gov/wp-content/uploads/2016/05/np-2015-10-034-jsc_combustion_in_reduced_gravity-iss-mini-book-011116-508.pdf",
     "url": "https://www.nasa.gov/missions/station/a-researchers-guide-to-combustion-science/", "report_numbers": "NP-2015-10-034-JSC"},
    # Fiches des investigations (page « NASA Combustion Science » de Glenn)
    *[{"id": f"glenn-{slug}", "kind": "pdf", "year": "2025", "sti_type": "FACT_SHEET", "topics": [topic], "title": title,
       "pdf_url": GLENN + f"{file}.pdf", "url": GLENN_PAGE, "report_numbers": ""}
      for slug, topic, file, title in (
          ("acme", "acme", "advanced-combustion-via-microgravity-experiments-acme", "Advanced Combustion via Microgravity Experiments (ACME)"),
          ("bass", "bass", "burning-and-suppression-of-solids-bass", "Burning and Suppression of Solids (BASS)"),
          ("daft", "particles", "dust-and-aerosol-measurement-feasibility-test-daft", "Dust and Aerosol Measurement Feasibility Test (DAFT)"),
          ("flex", "flex", "flame-extinguishment-experiment-flex", "Flame Extinguishment Experiment (FLEX)"),
          ("same", "same", "smoke-aerosol-measurement-experiment-same", "Smoke Aerosol Measurement Experiment (SAME)"),
          ("spice", "spice", "smoke-point-in-co-flow-experiment-spice", "Smoke Point In Co-flow Experiment (SPICE)"),
          ("saffire", "saffire", "spacecraft-fire-safety-demonstration-saffire", "Spacecraft Fire Safety Demonstration (Saffire)"),
          ("slice", "slice", "structure-liftoff-in-combustion-experiment-slice", "Structure and Liftoff In Combustion Experiment (SLICE)"),
      )],
    {"id": "nasa-std-6001b-change-3", "kind": "pdf", "year": "2025", "sti_type": "STANDARD", "topics": ["standards"],
     "title": "NASA-STD-6001B w/Change 3: Flammability, Offgassing, and Compatibility Requirements and Test Procedures",
     "pdf_url": "https://standards.nasa.gov/sites/default/files/standards/NASA/B-w/CHANGE-3/3/2025_06_25_NASA-STD-6001B_w_Change_3_FINAL_Admin-Change-FINAL.pdf",
     "url": "https://standards.nasa.gov/standard/NASA/NASA-STD-6001", "report_numbers": "NASA-STD-6001B"},
    {"id": "senate-report-956-apollo-204", "kind": "pdf", "year": "1968", "sti_type": "REPORT", "topics": ["incidents"],
     "title": "Apollo 204 Accident: Report of the Committee on Aeronautical and Space Sciences, United States Senate (Report 956)",
     "pdf_url": "https://history.nasa.gov/as204_senate_956.pdf", "url": "https://sma.nasa.gov/sma-disciplines/accllp/apollo-1",
     "report_numbers": "Senate Report 956"},
    # Pages web (texte de la page)
    *[{"id": f"web-{slug}", "kind": "html", "year": year, "sti_type": "WEB_PAGE", "topics": topics, "title": title,
       "pdf_url": None, "url": url, "report_numbers": ""}
      for slug, year, topics, title, url in (
          ("nasa-combustion-science", "2025", ["overview"], "NASA Combustion Science (Glenn Research Center)", GLENN_PAGE),
          ("researchers-guide-combustion", "2015", ["overview"], "A Researcher's Guide to: Combustion Science (page)",
           "https://www.nasa.gov/missions/station/a-researchers-guide-to-combustion-science/"),
          ("apollo-1", "", ["incidents"], "Apollo 1 (Apollo 204) fire: mission, accident, investigation and lessons learned",
           "https://sma.nasa.gov/sma-disciplines/accllp/apollo-1"),
          ("apollo-204-review-board-summary", "1967", ["incidents"], "Apollo 204 Review Board: summary",
           "https://history.nasa.gov/Apollo204/summary.html"),
          ("apollo-13", "", ["incidents"], "Apollo 13: oxygen tank explosion, investigation and lessons learned",
           "https://sma.nasa.gov/sma-disciplines/accllp/apollo-13"),
          ("mir-fire-1997", "2022", ["incidents"], "25 Years Ago: Fire Aboard Space Station Mir",
           "https://www.nasa.gov/history/25-years-ago-fire-aboard-space-station-mir/"),
          ("spinoff-9582", "", ["spinoff"], "NASA Spinoff: Fireman's Air Tanks", "https://spinoff.nasa.gov/node/9582"),
          ("spinoff-9407", "", ["spinoff"], "NASA Spinoff: Fire Detector", "https://spinoff.nasa.gov/node/9407"),
          ("spinoff-9918", "", ["spinoff"], "NASA Spinoff: New Technology for the Fire Attire", "https://spinoff.nasa.gov/node/9918"),
      )],
    {"id": "video-sciencecasts-combustion-iss", "kind": "video", "year": "2018", "sti_type": "VIDEO", "topics": ["overview"],
     "title": "NASA ScienceCasts: The Power of Studying Combustion on the ISS", "pdf_url": None,
     "url": "https://www.youtube.com/watch?v=W1oXykoz9zg", "report_numbers": ""},
]

# NASA Task Book : fiches des projets financés (recherche « Physical Sciences > COMBUSTION SCIENCE » du site officiel)
TASKBOOK = "https://taskbook.nasaprs.com/tbp/index.cfm"
TASKBOOK_COMBUSTION = "306,168,167,171,169"  # valeur de la case « COMBUSTION SCIENCE » du formulaire de recherche

CATALOG_COLUMNS = ["id", "title", "authors", "year", "sti_type", "report_numbers", "topics", "source", "url", "pdf_url",
                   "pdf_path", "size_mb", "n_pages", "n_pages_text", "status", "downloaded_at"]

session = requests.Session()
session.mount("https://", requests.adapters.HTTPAdapter(max_retries=requests.adapters.Retry(
    total=4, backoff_factor=2, status_forcelist=(429, 500, 502, 503, 504), allowed_methods=("GET",))))


# ---------- NTRS ----------

def citation(ntrs_id):
    r = session.get(f"{API}/citations/{ntrs_id}", timeout=60)
    r.raise_for_status()
    return r.json()


def search(query, size=40):
    r = session.get(f"{API}/citations/search", params={"q": query, "page.size": size}, timeout=60)
    r.raise_for_status()
    return r.json().get("results", [])


def pdf_link(record):
    for d in record.get("downloads") or []:
        if d.get("mimetype") == "application/pdf" and d.get("links", {}).get("pdf"):
            return "https://ntrs.nasa.gov" + d["links"]["pdf"]
    return None


def describe(record, topics, source):
    """Fiche catalogue d'un enregistrement NTRS."""
    authors = [a.get("meta", {}).get("author", {}).get("name") for a in record.get("authorAffiliations") or []]
    dates = [p.get("publicationDate", "") for p in record.get("publications") or []] + [record.get("submittedDate", "")]
    year = next((d[:4] for d in dates if d), "")
    numbers = [n.replace("Report Number: ", "") for n in record.get("otherReportNumbers") or []]
    return {
        "id": str(record["id"]),
        "title": record.get("title", "").strip(),
        "authors": "; ".join(a for a in authors[:6] if a),
        "year": year,
        "sti_type": record.get("stiType", ""),
        "report_numbers": "; ".join(dict.fromkeys(numbers)),
        "topics": topics,
        "source": source,
        "url": f"https://ntrs.nasa.gov/citations/{record['id']}",
        "kind": "pdf",
        "pdf_url": pdf_link(record),
        "abstract": (record.get("abstract") or "").strip(),
        "keywords": record.get("keywords") or [],
    }


def usable(record):
    return (record.get("distribution") == "PUBLIC" and str(record.get("downloadsAvailable")) == "True"
            and pdf_link(record) is not None)


def relevant(record, pattern, need_space):
    text = " ".join([record.get("title", ""), record.get("abstract") or "", " ".join(record.get("keywords") or [])])
    return re.search(pattern, text, re.I) and (not need_space or re.search(SPACE, text, re.I))


class SearchForm(HTMLParser):
    """Valeurs par défaut du formulaire de recherche du Task Book (champs cachés, cases cochées, options choisies)."""

    def __init__(self):
        super().__init__()
        self.fields, self.select = [], None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "input" and a.get("name") and a["name"] != "action":
            kind = (a.get("type") or "text").lower()
            if kind in ("hidden", "text") or (kind in ("checkbox", "radio") and "checked" in a):
                self.fields.append((a["name"], a.get("value", "")))
        elif tag == "select":
            self.select = a.get("name")
        elif tag == "option" and self.select and "selected" in a:
            self.fields.append((self.select, a.get("value", "")))

    def handle_endtag(self, tag):
        if tag == "select":
            self.select = None


def taskbook_ids():
    """Identifiants des projets « COMBUSTION SCIENCE » du Task Book (recherche du site, toutes les pages de résultats)."""
    tb = requests.Session()
    tb.headers["User-Agent"] = "Mozilla/5.0"
    home = tb.get(TASKBOOK, timeout=60).text
    form = SearchForm()
    form.feed(re.search(r'<form name="list".*?</form>', home, re.S).group(0))
    data = form.fields + [("action", "public_retrieve_result"), ("element", TASKBOOK_COMBUSTION), ("StartSearch", "Start Search")]
    page = tb.post(TASKBOOK, data=data, timeout=180).text
    total = re.search(r"Total Tasks:(?:<[^>]+>|&nbsp;|\s)*(\d+)", page)
    ids = list(dict.fromkeys(re.findall(r"TASKID=([0-9A-F]{32})", page)))
    for p in range(2, 50):  # pages de 25 résultats, jusqu'à ce qu'une page n'apporte plus rien
        page = tb.get(f"{TASKBOOK}?action=sort&sort=asc&col=pi&p={p}", timeout=180).text
        new = [i for i in dict.fromkeys(re.findall(r"TASKID=([0-9A-F]{32})", page)) if i not in ids]
        if not new:
            break
        ids += new
    print(f"  Task Book       : {len(ids)} projet(s) sur {total.group(1) if total else '?'}")
    return ids


def collect(per_topic, priority_only, with_taskbook=True):
    """Liste des documents à télécharger (dédoublonnés, thèmes fusionnés)."""
    docs = {}

    def add(doc):
        if doc["id"] in docs:
            docs[doc["id"]]["topics"] = sorted(set(docs[doc["id"]]["topics"]) | set(doc["topics"]))
        else:
            docs[doc["id"]] = doc

    for ntrs_id, topics in PRIORITY.items():
        record = citation(ntrs_id)
        if usable(record):
            add(describe(record, topics, "priorité"))
        else:
            print(f"  prioritaire sans PDF public : {ntrs_id}")
    for extra in EXTRA:
        add({**extra, "authors": "NASA", "source": "nasa.gov", "abstract": "", "keywords": []})
    if not priority_only:
        for topic, (query, pattern, need_space) in TOPICS.items():
            kept = [r for r in search(query) if usable(r) and relevant(r, pattern, need_space)][:per_topic]
            print(f"  thème {topic:13} : {len(kept)} document(s)")
            for r in kept:
                add(describe(r, [topic], f"recherche « {query} »"))
    if with_taskbook and not priority_only:
        for tid in taskbook_ids():
            add({"id": f"taskbook-{tid}", "kind": "taskbook", "title": "", "authors": "", "year": "", "sti_type": "TASK_BOOK",
                 "report_numbers": "", "topics": ["taskbook"], "source": "NASA Task Book (COMBUSTION SCIENCE)",
                 "url": f"{TASKBOOK}?action=public_query_taskbook_content&TASKID={tid}", "pdf_url": None,
                 "abstract": "", "keywords": []})
    return list(docs.values())


# ---------- Téléchargement et découpage par page ----------

class PageText(HTMLParser):
    """Texte lisible d'une page web : titres, paragraphes, listes ; sans menus, en-tête, pied de page ni scripts."""

    # pas « form » : les pages ASP.NET (sma.nasa.gov) mettent toute la page dans un <form>
    SKIP = {"script", "style", "nav", "header", "footer", "noscript", "svg", "button", "aside", "select"}
    BLOCKS = {"p", "h1", "h2", "h3", "h4", "h5", "li", "td", "th", "blockquote", "figcaption", "dd", "dt"}

    def __init__(self, everything=False):
        super().__init__()
        self.everything = everything  # True : tout le texte visible (pages sans paragraphes, ex. sma.nasa.gov)
        self.skip, self.block, self.parts, self.current = 0, 0, [], []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag in self.BLOCKS:
            self.block += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self.skip = max(0, self.skip - 1)
        elif tag in self.BLOCKS:
            self.block = max(0, self.block - 1)
            text = re.sub(r"\s+", " ", "".join(self.current)).strip()
            if text and (not self.parts or self.parts[-1] != text):
                self.parts.append(text)
            self.current = []

    def handle_data(self, data):
        if self.skip:
            return
        if self.everything:
            text = re.sub(r"\s+", " ", data).strip()
            if text and (not self.parts or self.parts[-1] != text):
                self.parts.append(text)
        elif self.block:
            self.current.append(data)


def html_text(html):
    """Texte principal d'une page : contenu de <main> s'il existe, paragraphes d'abord, sinon tout le texte visible."""
    start, end = html.find("<main"), html.rfind("</main>")
    candidates = ([html[start:end]] if start != -1 and end > start else []) + [html]  # <main> trop court : page entière
    text = ""
    for candidate in candidates:
        for everything in (False, True):
            parser = PageText(everything)
            parser.feed(candidate)
            text = "\n".join(parser.parts)
            if len(text) > 500:
                return text
    return text


def download(doc, max_mb):
    if doc["kind"] == "video":
        return None, "video_sans_texte"  # pas de transcription disponible : gardé au catalogue seulement
    if doc["kind"] in ("html", "taskbook"):
        path = OUT / "web" / f"{doc['id']}.html"
        if path.exists():
            return path, "already_present"
        r = session.get(doc["url"], headers={"User-Agent": "Mozilla/5.0"}, timeout=120)
        if not r.ok:
            return None, f"http_{r.status_code}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(r.text, encoding="utf-8")
        return path, "ok"
    path = OUT / "pdf" / f"{doc['id']}.pdf"
    if path.exists():
        return path, "already_present"
    head = session.head(doc["pdf_url"], allow_redirects=True, timeout=60)
    size = int(head.headers.get("content-length") or 0)
    if size > max_mb * 1e6:
        return None, f"trop_gros ({size / 1e6:.0f} Mo)"
    r = session.get(doc["pdf_url"], timeout=600)
    if not r.ok or not r.content.startswith(b"%PDF"):
        return None, f"http_{r.status_code}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(r.content)
    return path, "ok"


PRIVATE_LINE = re.compile(r"^(Address:|Email:|Phone:|Congressional District|Organization Type:)", re.I)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
PHONE = re.compile(r"(\+?1[-.\s]?)?\(?\b\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")


def taskbook_text(doc, html):
    """Texte d'une fiche du Task Book, à partir de « Fiscal Year: » (sans le menu du site) et sans les coordonnées
    personnelles (adresse, e-mail, téléphone), inutiles au RAG. Remplit titre, chercheur principal et année de `doc`."""
    plain = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).replace("&nbsp;", " ")
    field = lambda label: (re.search(label + r":\s*(.+?)\s{2,}", plain) or re.search(label + r":\s*(.{0,150})", plain))
    pi, fy = field("Principal Investigator/Affiliation"), re.search(r"Fiscal Year:\s*FY\s*(\d{4})", plain)
    title = re.search(r"Project Title:(?:&nbsp;|\s)*([^<]*?)\s*<", html)  # le titre s'arrête au lien du bouton « Reduce »
    title = re.sub(r"\s+", " ", title.group(1)).strip() if title else ""
    doc["title"] = f"NASA Task Book : {title}" if title else "NASA Task Book (projet sans titre)"
    doc["authors"] = re.sub(r"\s+", " ", pi.group(1)).strip() if pi else ""
    doc["year"] = fy.group(1) if fy else ""
    lines = html_text(html).split("\n")
    start = next((i for i, line in enumerate(lines) if line.startswith("Fiscal Year:")), 0)
    kept, skip_next = [], False
    for line in lines[start:]:
        if skip_next:
            skip_next = False
            continue
        if PRIVATE_LINE.match(line):
            skip_next = line.rstrip().endswith("Address:")  # la ligne suivante est l'adresse postale
            continue
        kept.append(line)
    text = re.sub(r"Center Contact:.*?(?=Unique ID:|$)", "", "\n".join(kept), flags=re.M)
    text = PHONE.sub("", EMAIL.sub("", text))  # aucune coordonnée personnelle dans le corpus
    return f"{doc['title']}\n{text}"


def split_pages(doc, path):
    """pages/<id>.jsonl ; renvoie (nb de pages, nb de pages avec du texte). Une page web = une page."""
    out = OUT / "pages" / f"{doc['id']}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".html":
        html = path.read_text(encoding="utf-8")
        text = taskbook_text(doc, html) if doc["kind"] == "taskbook" else html_text(html)
        out.write_text(json.dumps({"page": 1, "label": None, "text": text}, ensure_ascii=False) + "\n", encoding="utf-8")
        return 1, int(len(text) > 50)
    pdf = pymupdf.open(path)
    with_text = 0
    with open(out, "w", encoding="utf-8") as f:
        for i, page in enumerate(pdf, start=1):
            text = re.sub(r"[ \t]+", " ", page.get_text()).strip()
            with_text += len(text) > 50
            f.write(json.dumps({"page": i, "label": page.get_label() or None, "text": text}, ensure_ascii=False) + "\n")
    return len(pdf), with_text


def main():
    parser = argparse.ArgumentParser(description="Télécharge le corpus NASA du RAG.")
    parser.add_argument("--per-topic", type=int, default=15, help="documents gardés par thème (défaut 15)")
    parser.add_argument("--max-mb", type=float, default=80, help="taille maximale d'un PDF (défaut 80 Mo)")
    parser.add_argument("--priority-only", action="store_true", help="seulement les documents prioritaires")
    parser.add_argument("--no-taskbook", action="store_true", help="sans les fiches du NASA Task Book")
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    print("Recherche des documents...")
    docs = collect(args.per_topic, args.priority_only, with_taskbook=not args.no_taskbook)
    print(f"{len(docs)} documents à traiter")

    today = datetime.date.today().isoformat()
    log = []
    for doc in docs:
        try:
            path, status = download(doc, args.max_mb)
        except requests.RequestException as e:
            path, status = None, f"erreur ({type(e).__name__})"
        n_pages = n_text = 0
        if path is not None:
            n_pages, n_text = split_pages(doc, path)
            if n_pages and n_text / n_pages < 0.2:
                status += " ; scan_sans_texte"  # document numérisé sans couche texte : inutilisable sans OCR
        doc.update(pdf_path=path.relative_to(ROOT).as_posix() if path else "", size_mb=round(path.stat().st_size / 1e6, 1) if path else "",
                   n_pages=n_pages, n_pages_text=n_text, status=status, downloaded_at=today)
        log.append({"date": today, "id": doc["id"], "status": status, "pdf_url": doc["pdf_url"] or doc["url"]})
        print(f"  {status:22} {doc['id']:24} {n_text:>4}/{n_pages:<4} p.  {doc['title'][:70]}")

    with open(OUT / "catalog.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CATALOG_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows({**d, "topics": "; ".join(d["topics"])} for d in docs)
    with open(OUT / "catalog.jsonl", "w", encoding="utf-8") as f:
        for d in docs:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    with open(OUT / "download_log.csv", "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["date", "id", "status", "pdf_url"])
        if f.tell() == 0:
            writer.writeheader()
        writer.writerows(log)

    usable_docs = [d for d in docs if d["n_pages_text"]]
    print(f"\n{len(usable_docs)} / {len(docs)} documents avec du texte, "
          f"{sum(d['n_pages_text'] for d in usable_docs)} pages -> {(OUT / 'catalog.csv').relative_to(ROOT)}")


if __name__ == "__main__":
    main()
