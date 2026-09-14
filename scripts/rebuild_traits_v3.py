"""
Rebuild the species trait table with claim-level extraction, and join the specimen
metadata that does not need to be mined from literature at all.

Re-extraction runs over the cached QA answers in the checkpoint directory, so this does
not call the QA API. Geography, collection date and life stage come from the BOLD source
file, where they were all along.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from trait_extraction_v3 import extract_body_size, extract_habitat, extract_trophic  # noqa: E402

FIELDS = [
    "species", "genus", "family", "ncbi_taxid", "taxid_matched_rank",
    # trophic guild
    "trophic_guild", "trophic_guild_indirect", "trophic_evidence_type", "trophic_note",
    "trophic_n_docs", "trophic_sources", "trophic_qa_answer",
    # body size
    "body_size_mm", "body_size_indirect_mm", "body_size_note",
    "body_size_n_docs", "body_size_sources", "body_size_qa_answer",
    # habitat
    "habitat", "habitat_indirect", "habitat_evidence_type", "habitat_note",
    "habitat_n_docs", "habitat_sources", "habitat_qa_answer",
    # specimen metadata, straight from BOLD
    "bold_n_specimens", "bold_life_stage", "bold_habitat", "bold_sampling_protocol",
    "bold_country", "bold_province", "bold_coord", "bold_elev_m",
    "bold_collection_dates", "bold_biome", "bold_ecoregion",
]


def uniq(values) -> str:
    """Pipe-joined unique non-empty values, order preserved."""
    return "|".join(dict.fromkeys(v.strip() for v in values if v and v.strip()))


def load_bold(path: str) -> dict[str, dict]:
    """Aggregate BOLD specimen records per species."""
    agg: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    counts: dict[str, int] = defaultdict(int)
    cols = {
        "bold_life_stage": "life_stage", "bold_habitat": "habitat",
        "bold_sampling_protocol": "sampling_protocol", "bold_country": "country.ocean",
        "bold_province": "province.state", "bold_coord": "coord", "bold_elev_m": "elev",
        "bold_collection_dates": "collection_date_start", "bold_biome": "biome",
        "bold_ecoregion": "ecoregion",
    }
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        for rec in csv.DictReader(f):
            sp = (rec.get("species") or "").strip()
            if not sp:
                continue
            counts[sp] += 1
            for out, src in cols.items():
                v = (rec.get(src) or "").strip()
                if v:
                    agg[sp][out].append(v)

    result = {}
    for sp, fields in agg.items():
        row = {"bold_n_specimens": counts[sp]}
        for out in cols:
            vals = fields.get(out, [])
            if out == "bold_collection_dates" and vals:
                # BOLD writes dates as DD/M/YYYY; the year is the last component.
                years = sorted({p for v in vals
                                for p in [v.replace("-", "/").split("/")[-1].strip()]
                                if len(p) == 4 and p.isdigit()})
                row[out] = f"{years[0]}-{years[-1]}" if len(years) > 1 else (years[0] if years else "")
            elif out in ("bold_coord", "bold_elev_m"):
                row[out] = uniq(vals[:3])          # a sample is enough; full set is in BOLD
            else:
                row[out] = uniq(vals)
        result[sp] = row
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoints", default="results/checkpoints_species_v2")
    ap.add_argument("--bold", default="data/bold_collembola_180226.csv")
    ap.add_argument("--output", default="collembola_species_traits_v3.csv")
    args = ap.parse_args()

    bold = load_bold(args.bold)
    rows = []

    for path in sorted(Path(args.checkpoints).glob("*.json")):
        if path.name.startswith("_"):
            continue
        ck = json.loads(path.read_text())
        sp = ck["species"]
        tx = ck.get("taxid_info") or {}
        tro, siz, hab = (ck.get(k) or {} for k in ("trophic", "size", "habitat"))

        t = extract_trophic(tro.get("answer", ""), sp)
        b = extract_body_size(siz.get("answer", ""), sp)
        h = extract_habitat(hab.get("answer", ""), sp)

        row = {
            "species": sp, "genus": ck.get("genus", ""), "family": ck.get("family", ""),
            "ncbi_taxid": tx.get("taxid", ""), "taxid_matched_rank": tx.get("matched_rank", ""),

            "trophic_guild": "|".join(t["guilds"]),
            "trophic_guild_indirect": "|".join(t["guilds_indirect"]),
            "trophic_evidence_type": t["evidence_type"], "trophic_note": t["note"],
            "trophic_n_docs": tro.get("n_docs", 0), "trophic_sources": tro.get("source_docids", ""),
            "trophic_qa_answer": tro.get("answer", ""),

            "body_size_mm": b["range_mm"], "body_size_indirect_mm": b["range_indirect_mm"],
            "body_size_note": b["note"],
            "body_size_n_docs": siz.get("n_docs", 0), "body_size_sources": siz.get("source_docids", ""),
            "body_size_qa_answer": siz.get("answer", ""),

            "habitat": "|".join(h["habitats"]), "habitat_indirect": "|".join(h["habitats_indirect"]),
            "habitat_evidence_type": h["evidence_type"], "habitat_note": h["note"],
            "habitat_n_docs": hab.get("n_docs", 0), "habitat_sources": hab.get("source_docids", ""),
            "habitat_qa_answer": hab.get("answer", ""),
        }
        row.update({k: "" for k in FIELDS if k.startswith("bold_")})
        row.update(bold.get(sp, {}))
        rows.append(row)

    out = Path(args.output)
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    def n(key):
        return sum(1 for r in rows if str(r.get(key) or "").strip())

    print(f"{len(rows)} species -> {out}\n")
    print(f"{'':22}{'primary':>9}{'indirect':>10}")
    for label, prim, ind in [("trophic guild", "trophic_guild", "trophic_guild_indirect"),
                             ("body size", "body_size_mm", "body_size_indirect_mm"),
                             ("habitat", "habitat", "habitat_indirect")]:
        print(f"{label:22}{n(prim):>9}{n(ind):>10}")
    print(f"\n{'taxid resolved':22}{n('ncbi_taxid'):>9}")
    print(f"{'BOLD life stage':22}{n('bold_life_stage'):>9}")
    print(f"{'BOLD habitat':22}{n('bold_habitat'):>9}")
    print(f"{'BOLD coordinates':22}{n('bold_coord'):>9}")
    print(f"{'BOLD collection date':22}{n('bold_collection_dates'):>9}")


if __name__ == "__main__":
    main()
