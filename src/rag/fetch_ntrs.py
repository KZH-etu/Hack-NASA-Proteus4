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
- EXTRA : documents NASA hors NTRS.
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
}

EXTRA = [
    {
        "id": "nasa-np-2015-10-034-jsc",
        "title": "Combustion in Reduced Gravity (ISS mini-book, A Researcher's Guide to Combustion Science)",
        "pdf_url": "https://www.nasa.gov/wp-content/uploads/2016/05/np-2015-10-034-jsc_combustion_in_reduced_gravity-iss-mini-book-011116-508.pdf",
        "url": "https://www.nasa.gov/missions/station/a-researchers-guide-to-combustion-science/",
        "year": "2015", "sti_type": "BOOKLET", "report_numbers": "NP-2015-10-034-JSC", "topics": ["fire_safety", "overview"],
    },
]

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


def collect(per_topic, priority_only):
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
    return list(docs.values())


# ---------- Téléchargement et découpage par page ----------

def download(doc, max_mb):
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


def split_pages(doc_id, pdf_path):
    """pages/<id>.jsonl ; renvoie (nb de pages, nb de pages avec du texte)."""
    out = OUT / "pages" / f"{doc_id}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    pdf = pymupdf.open(pdf_path)
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
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    print("Recherche des documents...")
    docs = collect(args.per_topic, args.priority_only)
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
            n_pages, n_text = split_pages(doc["id"], path)
            if n_pages and n_text / n_pages < 0.2:
                status += " ; scan_sans_texte"  # document numérisé sans couche texte : inutilisable sans OCR
        doc.update(pdf_path=path.relative_to(ROOT).as_posix() if path else "", size_mb=round(path.stat().st_size / 1e6, 1) if path else "",
                   n_pages=n_pages, n_pages_text=n_text, status=status, downloaded_at=today)
        log.append({"date": today, "id": doc["id"], "status": status, "pdf_url": doc["pdf_url"]})
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
