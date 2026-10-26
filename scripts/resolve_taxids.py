"""
Resolve NCBI Taxonomy IDs for the species list, verifying every hit.

The previous resolver searched NCBI with the bare name and took the first id. When a
species is absent from NCBI, NCBI's search falls back to matching individual words, so
"Halisotoma arenicola" returned the lugworm genus Arenicola, "Tetracanthella brachyura"
returned the crab infraorder Brachyura, and the resolver recorded each as an exact species
match. Bachir Balech found ten such cases in October 2026.

Every candidate is now fetched and checked: its scientific name must equal the name asked
for, and its lineage must contain Collembola. A species that fails falls back to its genus,
then to its family as recorded in BOLD, each under the same two checks. Anything still
unverified gets "N/A" rather than a wrong organism.

The output also carries the NCBI family, compared against the family recorded in BOLD, so
taxa whose placement differs between the two backbones are flagged rather than silently
reconciled.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
DELAY = 0.34  # NCBI: at most 3 requests per second without an API key


def esearch_exact(name: str) -> list[str]:
    r = requests.get(f"{EUTILS}/esearch.fcgi", timeout=20, params={
        "db": "taxonomy", "term": f'"{name}"[Scientific Name]', "retmode": "json"})
    time.sleep(DELAY)
    return r.json().get("esearchresult", {}).get("idlist", [])


def efetch(ids: list[str]) -> dict[str, dict]:
    """Scientific name, rank, lineage and family for each taxid."""
    out: dict[str, dict] = {}
    for i in range(0, len(ids), 100):
        batch = ids[i:i + 100]
        r = requests.get(f"{EUTILS}/efetch.fcgi", timeout=60,
                         params={"db": "taxonomy", "id": ",".join(batch), "retmode": "xml"})
        time.sleep(DELAY)
        for taxon in ET.fromstring(r.content).findall("Taxon"):
            tid = taxon.findtext("TaxId")
            lineage = taxon.findtext("Lineage") or ""
            family = ""
            for t in taxon.findall("LineageEx/Taxon"):
                if t.findtext("Rank") == "family":
                    family = t.findtext("ScientificName") or ""
            out[tid] = {"name": taxon.findtext("ScientificName") or "",
                        "rank": taxon.findtext("Rank") or "",
                        "lineage": lineage, "family": family}
    return out


def verified(tid: str, expected_name: str, info: dict) -> bool:
    rec = info.get(tid)
    return bool(rec) and rec["name"].lower() == expected_name.lower() \
        and "Collembola" in rec["lineage"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--traits", default="collembola_species_traits_v4.csv")
    ap.add_argument("--bold", default="data/bold_collembola_180226.csv")
    ap.add_argument("--output", default="taxids_verified.csv")
    ap.add_argument("--cache", default="results/taxid_cache_verified.json")
    args = ap.parse_args()

    species = [r for r in csv.DictReader(open(args.traits))]
    bold_family = {}
    with open(args.bold, newline="", encoding="utf-8", errors="replace") as f:
        for rec in csv.DictReader(f):
            sp = (rec.get("species") or "").strip()
            if sp and sp not in bold_family:
                bold_family[sp] = (rec.get("family") or "").strip()

    cache_path = Path(args.cache)
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}

    # 1. exact-name searches: species, genus, then the family recorded in BOLD
    for r in species:
        sp, genus = r["species"], r["species"].split()[0]
        for q in (sp, genus, bold_family.get(sp, "")):
            if not q:
                continue
            if q not in cache:
                try:
                    cache[q] = esearch_exact(q)
                except Exception as exc:
                    print(f"  [WARN] {q}: {exc}")
                    cache[q] = None
        cache_path.write_text(json.dumps(cache))

    # 2. fetch every candidate once, then verify
    cand = sorted({t for ids in cache.values() if ids for t in ids})
    info = efetch(cand)

    rows = []
    for r in species:
        sp, genus = r["species"], r["species"].split()[0]
        tid, rank, status = "", "", "unresolved"
        fam = bold_family.get(sp, "")
        sp_ok = [t for t in (cache.get(sp) or []) if verified(t, sp, info)]
        g_ok = [t for t in (cache.get(genus) or []) if verified(t, genus, info)]
        f_ok = [t for t in (cache.get(fam) or []) if fam and verified(t, fam, info)]
        if sp_ok:
            tid, rank, status = sp_ok[0], "species", "species"
        elif g_ok:
            tid, rank, status = g_ok[0], "genus", "genus_fallback"
        elif f_ok:
            tid, rank, status = f_ok[0], "family", "family_fallback"
        ncbi_fam = info.get(tid, {}).get("family", "") if tid else ""
        bfam = bold_family.get(sp, "")
        conflict = bool(ncbi_fam and bfam and ncbi_fam.lower() != bfam.lower())
        rows.append({
            "species": sp,
            "ncbi_taxid": tid or "N/A",
            "taxid_matched_rank": rank or "N/A",
            "taxid_status": status,
            "ncbi_scientific_name": info.get(tid, {}).get("name", "") if tid else "",
            "ncbi_family": ncbi_fam,
            "bold_family": bfam,
            "family_conflict_bold_ncbi": "yes" if conflict else "",
            "previous_taxid": r.get("ncbi_taxid", ""),
            "previous_rank": r.get("taxid_matched_rank", ""),
            "ncbi_lineage": info.get(tid, {}).get("lineage", "") if tid else "",
        })

    with open(args.output, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    from collections import Counter
    st = Counter(x["taxid_status"] for x in rows)
    changed = [x for x in rows if x["ncbi_taxid"] not in (x["previous_taxid"], "N/A")]
    print(f"{len(rows)} species -> {args.output}")
    print(f"  species-level, verified : {st['species']}")
    print(f"  genus fallback, verified: {st['genus_fallback']}")
    print(f"  family fallback, verified: {st['family_fallback']}")
    print(f"  unresolved              : {st['unresolved']}")
    print(f"  taxid changed vs before : {len(changed)}")
    print(f"  BOLD/NCBI family conflict: {sum(1 for x in rows if x['family_conflict_bold_ncbi'])}")


if __name__ == "__main__":
    main()
