#!/usr/bin/env python3
"""
Species-level trait mining for Collembola via SIBILS QA.

For each identified species (binomial) in the BOLD dataset, this script:
  1. Resolves the NCBI Taxonomy ID (so collaborators can check the taxonomic path)
  2. Asks SIBILS QA three questions (generative):
       - trophic guild : "What does {species} feed on?"
       - body size     : "What is the body length of {species}?"
       - habitat       : "What is the habitat of {species}?"
  3. Extracts structured values: trophic guild(s), body-size measurements, habitat terms
  4. Writes a single shareable CSV (+ per-species JSON checkpoints, resumable)

This addresses the collaborators' feedback (Montagna, Balech et al.):
  - assignment at SPECIES level, not genus
  - NCBI taxids included for taxonomic verification
  - body size and habitat trials in addition to trophic guild

Usage:
  python scripts/collembola_species_traits.py [options]
    --csv PATH          BOLD CSV (default: "collembola_Bold_180226.xlsx - collemboli2.csv")
    --api URL           SIBILS QA base URL (default: https://qa.dev.sibils.org/api)
    --output PATH       master output CSV (default: results/collembola_species_traits.csv)
    --checkpoint-dir D  per-species JSON dir (default: results/species_checkpoints)
    --limit N           only process the first N species (for a quick trial)
    --delay SECS        pause between species (default: 0.4)
"""

import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path
from typing import Optional

import requests


# ---------------------------------------------------------------------------
# Trophic guild keyword scheme (Potapov et al. 2022) — same as the genus run
# ---------------------------------------------------------------------------

GUILD_KEYWORDS = {
    "fungivore":   ["fung", "hyphae", "hypha", "mycelium", "mycorrhiz", "spore", "yeast",
                    "mold", "mould", "mushroom", "oomycete", "ergosterol", "mycophag"],
    "bacterivore": ["bacteri", "microorganism", "microbe", "microbial community",
                    "prokaryote", "archaea"],
    "algivore":    ["alga", "algae", "diatom", "cyanobacteri", "microalga", "biofilm"],
    "herbivore":   ["plant root", "root hair", "pollen", "seed", "moss", "lichen",
                    "liverwort", "bryophyte", "plant tissue", "vascular plant"],
    "predator":    ["prey", "predat", "hunt", "capture", "nematode", "rotifer",
                    "protozoa", "tardigrade", "enchytraeid"],
    "detritivore": ["detritus", "decompos", "organic matter", "litter", "humus",
                    "soil organic", "carrion", "dead plant", "dead wood", "decaying"],
    "omnivore":    ["omnivore", "generalist", "opportunistic", "mixed diet",
                    "multiple food source", "various food"],
}
_GUILD_PAT = {g: [re.compile(k, re.I) for k in ks] for g, ks in GUILD_KEYWORDS.items()}


def infer_guilds(texts: list[str]) -> list[str]:
    combined = " ".join(t for t in texts if t).lower()
    scores = {g: sum(1 for p in pats if p.search(combined)) for g, pats in _GUILD_PAT.items()}
    matched = sorted([g for g, s in scores.items() if s > 0], key=lambda g: -scores[g])
    if not matched:
        return ["unknown"]
    if len(matched) >= 3 and "omnivore" not in matched:
        matched = ["omnivore"] + matched
    return matched


# ---------------------------------------------------------------------------
# Body-size extraction
# ---------------------------------------------------------------------------

_SIZE_RE = re.compile(
    r'(\d+(?:[.,]\d+)?)\s*(?:(?:[-–—]|to)\s*(\d+(?:[.,]\d+)?)\s*)?'
    r'(mm|millimet(?:er|re)s?|µm|μm|um|microns?|micromet(?:er|re)s?)\b',
    re.I,
)

def _to_mm(value: float, unit: str) -> float:
    unit = unit.lower()
    if unit.startswith(("µ", "μ", "u", "micron", "micromet")):
        return value / 1000.0
    return value  # mm / millimetre

def extract_body_size(text: str) -> dict:
    """Return {'measurements_mm': [floats], 'range_mm': 'a-b' or 'a', 'raw': [...]}. """
    if not text:
        return {"measurements_mm": [], "range_mm": "", "raw": []}
    vals, raw = [], []
    for m in _SIZE_RE.finditer(text):
        lo = float(m.group(1).replace(",", "."))
        unit = m.group(3)
        vals.append(_to_mm(lo, unit))
        if m.group(2):
            hi = float(m.group(2).replace(",", "."))
            vals.append(_to_mm(hi, unit))
        raw.append(m.group(0).strip())
    # keep biologically plausible springtail sizes (0.1–15 mm) to filter noise
    plaus = [v for v in vals if 0.1 <= v <= 15.0]
    rng = ""
    if plaus:
        lo, hi = min(plaus), max(plaus)
        rng = f"{lo:g}" if lo == hi else f"{lo:g}-{hi:g}"
    return {"measurements_mm": [round(v, 3) for v in plaus], "range_mm": rng, "raw": raw}


# ---------------------------------------------------------------------------
# Habitat extraction
# ---------------------------------------------------------------------------

HABITAT_KEYWORDS = {
    "soil":            ["soil", "edaphic", "subterranean", "underground", "belowground"],
    "leaf_litter":     ["leaf litter", "litter", "humus", "decaying leaves", "leaf-litter"],
    "moss_lichen":     ["moss", "bryophyte", "lichen", "liverwort"],
    "cave":            ["cave", "cavern", "troglo", "hypogean", "subterranea"],
    "forest_wood":     ["forest", "woodland", "tree trunk", "bark", "canopy", "deadwood", "dead wood", "alder", "coniferous"],
    "grassland":       ["grassland", "meadow", "pasture", "field", "steppe"],
    "freshwater":      ["freshwater", "stream", "pond", "lake", "riparian", "aquatic", "water surface", "wetland", "bog", "fen"],
    "marine_coastal":  ["marine", "coastal", "intertidal", "tidal", "seashore", "beach", "shore",
                        "littoral", "seaweed", "supralittoral", "rockpool", "salt marsh", "saltmarsh",
                        "estuar", "mudflat", "mud surface", "mud flat", "sea "],
    "alpine_glacier":  ["alpine", "glacier", "glacial", "snow", "nival", "high altitude", "high-altitude", "mountain", "subnival"],
    "agricultural":    ["agricultural", "crop", "cultivated", "greenhouse", "arable", "orchard", "vineyard"],
    "synanthropic":    ["compost", "garden", "urban", "domestic", "manure", "dung"],
    "sandy_dune":      ["sand", "dune", "silt"],
}
_HAB_PAT = {h: [re.compile(re.escape(k), re.I) for k in ks] for h, ks in HABITAT_KEYWORDS.items()}

def extract_habitat(text: str) -> list[str]:
    if not text:
        return []
    scores = {h: sum(1 for p in pats if p.search(text)) for h, pats in _HAB_PAT.items()}
    return sorted([h for h, s in scores.items() if s > 0], key=lambda h: -scores[h])


# ---------------------------------------------------------------------------
# NCBI taxid resolution (cached)
# ---------------------------------------------------------------------------

def resolve_taxid(name: str, cache: dict, delay: float = 0.34) -> dict:
    """Resolve an NCBI Taxonomy ID. Falls back to genus if species not found.
    Returns {'taxid': str, 'matched_rank': 'species'|'genus'|'', 'matched_name': str}."""
    if name in cache:
        return cache[name]
    result = {"taxid": "", "matched_rank": "", "matched_name": ""}
    for query, rank in [(name, "species"), (name.split()[0], "genus")]:
        try:
            r = requests.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
                             params={"db": "taxonomy", "term": query, "retmode": "json"},
                             timeout=15)
            ids = r.json().get("esearchresult", {}).get("idlist", [])
            time.sleep(delay)  # NCBI: <=3 req/s without an API key
            if ids:
                result = {"taxid": ids[0], "matched_rank": rank, "matched_name": query}
                break
        except Exception as exc:
            print(f"  [WARN] NCBI taxid lookup failed for '{query}': {exc}", file=sys.stderr)
    cache[name] = result
    return result


# ---------------------------------------------------------------------------
# Retrieval + QA — species-specific, phrase-matched
#
# The binomial is required as an adjacent PHRASE (must-clause) so retrieval can
# never match a different organism that merely shares the specific epithet
# (e.g. "polaris" -> the stonefly Arcynopteryx polaris). Trait-relevant terms
# are added as a should-clause so, among the right-organism documents, the ones
# describing the trait rank first. QA then runs on exactly those documents via
# doc_refs (retrieval is skipped). If no document mentions the full binomial,
# the trait is left blank — no information from a different taxon is assigned.
# ---------------------------------------------------------------------------

SEARCH_URL = "https://biodiversitypmc.sibils.org/api/search"

TRAIT_TERMS = {
    "trophic": "feed diet food prey feeding fungi bacteria algae detritus",
    "size":    "body length size mm millimetre measurement",
    "habitat": "habitat soil litter moss cave forest inhabits found lives",
}
COL_FIELDS = {
    "medline": ["title", "abstract", "keywords"],
    "pmc":     ["title", "abstract", "keywords"],
    "plazi":   ["treatment_title", "text", "title"],
}


def phrase_search_ids(binomial: str, trait_key: str, n: int = 6) -> list[str]:
    """Return document IDs that contain the full binomial as a phrase, ranked by
    trait relevance, across Medline + PMC + Plazi."""
    ids: list[str] = []
    for col, fields in COL_FIELDS.items():
        esq = {"query": {"bool": {
            "must":   [{"multi_match": {"query": binomial, "type": "phrase", "fields": fields}}],
            "should": [{"multi_match": {"query": TRAIT_TERMS[trait_key], "fields": fields}}],
        }}}
        try:
            r = requests.post(SEARCH_URL, params={"col": col, "n": n},
                              data={"jq": json.dumps(esq)}, timeout=30)
            for h in r.json().get("elastic_output", {}).get("hits", {}).get("hits", []):
                if h.get("_id"):
                    ids.append(h["_id"])
        except Exception as exc:
            print(f"  [WARN] phrase search failed ({col}): {exc}", file=sys.stderr)
    return list(dict.fromkeys(ids))  # dedup, preserve order


def query_qa_docrefs(question: str, ids: list[str], api_url: str, timeout: int = 150) -> dict:
    """Run generative QA on exactly the given document IDs (skips retrieval)."""
    if not ids:
        return {"answer": "", "source_docids": "", "n_docs": 0, "n_ontarget": 0}
    try:
        resp = requests.post(f"{api_url.rstrip('/')}/qa", timeout=timeout,
                             json={"question": question, "mode": "generative", "doc_refs": ids})
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        print(f"  [ERROR] QA failed: {question!r}: {exc}", file=sys.stderr)
        return {"answer": "", "source_docids": "", "n_docs": 0, "n_ontarget": len(ids)}

    best, docids = "", []
    for cr in data.get("collection_results") or []:
        answers = cr.get("answers") or []
        if answers and answers[0].get("answer") and not best:
            best = answers[0]["answer"]
        for a in answers:
            for d in a.get("docs") or []:
                if d.get("docid"):
                    docids.append(f"{d['docid']}({d.get('doc_source','')})")
    return {"answer": best, "source_docids": "|".join(dict.fromkeys(docids)),
            "n_docs": data.get("ndocs_retrieved") or 0, "n_ontarget": len(ids)}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_species(csv_path: str) -> list[dict]:
    """Unique identified binomials from BOLD (excludes 'Genus sp.' / NA)."""
    seen, out = set(), []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            sp = (r.get("species") or "").strip()
            if sp and sp not in seen and not sp.endswith(" sp.") and sp != "NA":
                seen.add(sp)
                out.append({"species": sp, "genus": (r.get("genus") or "").strip(),
                            "family": (r.get("family") or "").strip()})
    return sorted(out, key=lambda x: x["species"])


def clean_answer(ans: str, cap: int = 400) -> str:
    if not ans:
        return ""
    t = re.sub(r'^(Based on|According to) the (provided )?documents,?\s*', '', ans.strip(), flags=re.I)
    t = re.sub(r'\s+', ' ', t).replace('|', '/')
    return (t[:cap].rsplit(' ', 1)[0] + '…') if len(t) > cap else t


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Species-level Collembola trait mining via SIBILS QA")
    ap.add_argument("--csv", default="data/bold_collembola_180226.csv")
    ap.add_argument("--api", default="https://qa.dev.sibils.org/api")
    ap.add_argument("--output", default="results/collembola_species_traits.csv")
    ap.add_argument("--checkpoint-dir", default="results/checkpoints_species_v2")
    ap.add_argument("--taxid-cache", default="")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--delay", type=float, default=0.4)
    args = ap.parse_args()

    ckpt_dir = Path(args.checkpoint_dir)
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)

    taxid_cache_path = Path(args.taxid_cache) if args.taxid_cache else ckpt_dir / "_taxid_cache.json"
    taxid_cache = {}
    if taxid_cache_path.exists():
        taxid_cache = json.loads(taxid_cache_path.read_text())

    species = load_species(args.csv)
    if args.limit:
        species = species[:args.limit]
    print(f"Loaded {len(species)} identified species.\n")

    QUESTIONS = {
        "trophic": "What does {sp} feed on?",
        "size":    "What is the body length of {sp}?",
        "habitat": "What is the habitat of {sp}?",
    }

    for i, entry in enumerate(species, 1):
        sp = entry["species"]
        ckpt = ckpt_dir / (sp.replace(" ", "_").replace("/", "_") + ".json")
        if ckpt.exists():
            print(f"  [{i:3d}/{len(species)}] {sp} — checkpoint")
            continue

        print(f"  [{i:3d}/{len(species)}] {sp} ...", end="", flush=True)
        rec = dict(entry)
        rec["taxid_info"] = resolve_taxid(sp, taxid_cache)
        taxid_cache_path.write_text(json.dumps(taxid_cache))
        for key, tmpl in QUESTIONS.items():
            ids = phrase_search_ids(sp, key)
            rec[key] = query_qa_docrefs(tmpl.format(sp=sp), ids, args.api)
            time.sleep(args.delay)
        ckpt.write_text(json.dumps(rec))
        ont = "/".join(str(rec[k]["n_ontarget"]) for k in QUESTIONS)
        print(f" done (on-target tg/sz/hab: {ont}, taxid:{rec['taxid_info']['taxid'] or '-'})")

    # ---- assemble master CSV from checkpoints ----
    print("\nAssembling master CSV ...")
    fields = [
        "species", "genus", "family", "ncbi_taxid", "taxid_matched_rank",
        "trophic_guilds", "trophic_guild_primary", "trophic_qa_answer",
        "trophic_n_docs", "trophic_sources",
        "body_size_range_mm", "body_size_measurements_mm", "body_size_qa_answer",
        "body_size_n_docs", "body_size_sources",
        "habitat_categories", "habitat_qa_answer",
        "habitat_n_docs", "habitat_sources",
    ]
    n_tg = n_size = n_hab = 0
    with open(args.output, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for entry in species:
            sp = entry["species"]
            ckpt = ckpt_dir / (sp.replace(" ", "_").replace("/", "_") + ".json")
            if not ckpt.exists():
                continue
            rec = json.loads(ckpt.read_text())
            tg_texts = [rec["trophic"]["answer"]]
            guilds = infer_guilds(tg_texts)
            size = extract_body_size(rec["size"]["answer"])
            hab = extract_habitat(rec["habitat"]["answer"])
            if guilds != ["unknown"]:
                n_tg += 1
            if size["range_mm"]:
                n_size += 1
            if hab:
                n_hab += 1
            w.writerow({
                "species": sp, "genus": entry["genus"], "family": entry["family"],
                "ncbi_taxid": rec["taxid_info"]["taxid"],
                "taxid_matched_rank": rec["taxid_info"]["matched_rank"],
                "trophic_guilds": "|".join(guilds),
                "trophic_guild_primary": guilds[0],
                "trophic_qa_answer": clean_answer(rec["trophic"]["answer"]),
                "trophic_n_docs": rec["trophic"].get("n_ontarget", 0),
                "trophic_sources": rec["trophic"]["source_docids"],
                "body_size_range_mm": size["range_mm"],
                "body_size_measurements_mm": "|".join(str(v) for v in size["measurements_mm"]),
                "body_size_qa_answer": clean_answer(rec["size"]["answer"]),
                "body_size_n_docs": rec["size"].get("n_ontarget", 0),
                "body_size_sources": rec["size"]["source_docids"],
                "habitat_categories": "|".join(hab),
                "habitat_qa_answer": clean_answer(rec["habitat"]["answer"]),
                "habitat_n_docs": rec["habitat"].get("n_ontarget", 0),
                "habitat_sources": rec["habitat"]["source_docids"],
            })

    done = sum(1 for e in species
               if (ckpt_dir / (e["species"].replace(" ", "_").replace("/", "_") + ".json")).exists())
    print(f"\nDone. {done}/{len(species)} species processed → {args.output}")
    print(f"  trophic guild assigned : {n_tg}")
    print(f"  body size extracted    : {n_size}")
    print(f"  habitat inferred       : {n_hab}")
    with_taxid = sum(1 for s in species if taxid_cache.get(s['species'], {}).get('taxid'))
    print(f"  NCBI taxid resolved    : {with_taxid}")


if __name__ == "__main__":
    main()
