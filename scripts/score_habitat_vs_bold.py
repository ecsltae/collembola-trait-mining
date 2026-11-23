"""
Score literature-mined habitat against the habitat BOLD collectors recorded in the field
(D10.3 action P10).

BOLD is not a gold standard for habitat. A species' BOLD records show where its barcoded
specimens were collected, which is a sample of its habitats, not their full range. So:

  confirmed     a literature class that at least one BOLD record of the species also has.
                The share of literature classes confirmed is a LOWER BOUND on precision:
                an unconfirmed class may be right and simply never sampled for barcoding.
  contradicted  a literature class absent from BOLD for a species with at least
                --min-records habitat records, all of which agree on other classes. These
                are the cases worth a reviewer's look, not proven errors.
  BOLD recall   the share of a species' BOLD classes that the literature also found.

Only BOLD's free-text `habitat` field and `sampling_protocol` are used. `biome` and
`ecoregion` are derived from the coordinates (WWF regions), not observed, and a grassland
inside the "temperate broadleaf forest" biome is still a grassland.

BOLD habitat strings are mapped onto EUNIS level 1 (2012 letters) the same way the
literature is, with the extractor's own vocabulary, except where a string carries an
explicit EUNIS code ("EUNIS G1.1; Riparian ... woodland", "R1, Dry grasslands"): the code
then decides. Codes from the 2021 revision are mapped to their 2012 level-1 letter.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# EUNIS 2012 level-1 letters, and the 2021 revision's letters mapped onto them.
EUNIS_CODE = {
    "A": "A_marine", "B": "B_coastal", "C": "C_inland_water", "D": "D_mire_bog_fen",
    "E": "E_grassland", "F": "F_heath_scrub", "G": "G_woodland_forest",
    "H": "H_cave_ice_scree", "I": "I_agricultural", "J": "J_artificial",
    # 2021: M marine, N coastal, P inland waters, Q wetlands, R grasslands, S heathland and
    # scrub, T forest, U inland sparsely vegetated, V vegetated man-made.
    "M": "A_marine", "N": "B_coastal", "P": "C_inland_water", "Q": "D_mire_bog_fen",
    "R": "E_grassland", "S": "F_heath_scrub", "T": "G_woodland_forest",
    "U": "H_cave_ice_scree", "V": "I_agricultural",
}
# A code at the start of the string, or after "EUNIS". "U. bark" (under bark) has no digit
# and is not a code. X (habitat complexes) has no level-1 equivalent and falls through to
# the vocabulary.
_CODE = re.compile(r"(?:^|\bEUNIS\s+)([A-JMNPQRSTUV])\d{1,2}[A-Z]?(?:\.\w+)?\b")
_NULL = {"", "NA", "_", "N/A", "na"}


def bold_classes(habitat: str, protocol: str, ex) -> tuple[set[str], set[str]]:
    """EUNIS macro classes and microhabitats of one BOLD record."""
    habitat = "" if habitat.strip() in _NULL else habitat.strip()
    protocol = "" if protocol.strip() in _NULL else protocol.strip()
    m = _CODE.search(habitat)
    macro = {EUNIS_CODE[m.group(1)]} if m else set(ex._macro_in(habitat))
    if not m and protocol:
        macro |= set(ex._macro_in(protocol))      # "Seaweed from rocky beach"
    micro = set(ex._micro_in(habitat)) | set(ex._micro_in(protocol))
    return macro, micro


def load_bold(path: Path, ex) -> dict[str, dict]:
    per: dict[str, dict] = defaultdict(lambda: {"n": 0, "macro": Counter(), "micro": Counter()})
    with open(path, encoding="utf-8", errors="replace") as fh:
        for r in csv.DictReader(fh):
            sp = (r.get("species") or "").strip()
            if not sp:
                continue
            macro, micro = bold_classes(r.get("habitat", ""), r.get("sampling_protocol", ""), ex)
            if not (macro or micro):
                continue
            d = per[sp]
            d["n"] += 1
            d["macro"].update(macro)
            d["micro"].update(micro)
    return per


def literature(version: str, species: list[str], ck_dir: Path, ex) -> dict[str, dict]:
    out = {}
    for sp in species:
        path = ck_dir / (sp.replace(" ", "_") + ".json")
        if not path.exists():
            continue
        answer = ((json.loads(path.read_text()).get("habitat") or {}).get("answer")) or ""
        h = ex.extract_habitat(answer, sp)
        out[sp] = {"macro": set(h["eunis"]), "micro": set(h["microhabitat"]),
                   "macro_ind": set(h["eunis_indirect"])}
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="v5", choices=["v4", "v5"])
    ap.add_argument("--bold", default="data/bold_collembola_180226.csv")
    ap.add_argument("--traits", default="collembola_species_traits_v4.csv",
                    help="only used for the species list")
    ap.add_argument("--checkpoints", default="results/checkpoints_species_v2")
    ap.add_argument("--min-records", type=int, default=3)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    ex = __import__(f"trait_extraction_{args.version}")
    species = [r["species"] for r in csv.DictReader(open(args.traits, encoding="utf-8"))]
    bold = load_bold(Path(args.bold), ex)
    lit = literature(args.version, species, Path(args.checkpoints), ex)

    both = [sp for sp in species if sp in lit and lit[sp]["macro"] and bold.get(sp, {}).get("macro")]
    lit_any = sum(1 for sp in species if sp in lit and lit[sp]["macro"])
    bold_any = sum(1 for sp in species if bold.get(sp, {}).get("macro"))

    n_cls = n_conf = sp_conf = rec_num = rec_den = 0
    per_class = defaultdict(Counter)
    rows, contradicted = [], []
    for sp in both:
        L, B = lit[sp]["macro"], set(bold[sp]["macro"])
        conf = L & B
        n_cls += len(L)
        n_conf += len(conf)
        sp_conf += bool(conf)
        rec_num += len(B & L)
        rec_den += len(B)
        for c in L:
            per_class[c]["lit"] += 1
            per_class[c]["conf"] += c in B
        strong = bold[sp]["n"] >= args.min_records
        for c in sorted(L - B):
            if strong:
                contradicted.append((sp, c, bold[sp]["n"], dict(bold[sp]["macro"])))
        rows.append({
            "species": sp,
            "bold_records_with_habitat": bold[sp]["n"],
            "bold_eunis": "|".join(f"{k}:{v}" for k, v in bold[sp]["macro"].most_common()),
            "literature_eunis": "|".join(sorted(L)),
            "confirmed": "|".join(sorted(conf)),
            "not_in_bold": "|".join(sorted(L - B)),
            "bold_only": "|".join(sorted(B - L)),
            "bold_micro": "|".join(f"{k}:{v}" for k, v in bold[sp]["micro"].most_common()),
            "literature_micro": "|".join(sorted(lit[sp]["micro"])),
        })

    # Microhabitat, where both sides have one.
    m_both = [sp for sp in species if sp in lit and lit[sp]["micro"] and bold.get(sp, {}).get("micro")]
    m_cls = sum(len(lit[sp]["micro"]) for sp in m_both)
    m_conf = sum(len(lit[sp]["micro"] & set(bold[sp]["micro"])) for sp in m_both)

    print(f"habitat vs BOLD field records  ({args.version}, {len(species)} species)")
    print(f"  species with a literature EUNIS class       : {lit_any}")
    print(f"  species with a BOLD habitat record           : {bold_any}")
    print(f"  species with both (scored)                   : {len(both)}")
    print(f"  literature classes confirmed by BOLD         : {n_conf}/{n_cls} "
          f"({100*n_conf/max(n_cls,1):.0f}%)  lower bound on precision")
    print(f"  species with at least one class confirmed    : {sp_conf}/{len(both)} "
          f"({100*sp_conf/max(len(both),1):.0f}%)")
    print(f"  BOLD classes the literature also found       : {rec_num}/{rec_den} "
          f"({100*rec_num/max(rec_den,1):.0f}%)")
    print(f"  microhabitat confirmed (species with both={len(m_both)}): {m_conf}/{m_cls} "
          f"({100*m_conf/max(m_cls,1):.0f}%)")
    print(f"\n  {'class':22} {'assigned':>9} {'confirmed':>10}")
    for c in sorted(per_class, key=lambda c: -per_class[c]["lit"]):
        print(f"  {c:22} {per_class[c]['lit']:>9} {per_class[c]['conf']:>10}")
    print(f"\n  not in BOLD although the species has >= {args.min_records} habitat records "
          f"({len(contradicted)}), for review:")
    for sp, c, n, b in contradicted:
        print(f"    {sp:30} {c:20} BOLD ({n} records): {b}")

    out = Path(args.out or f"results/habitat_vs_bold_{args.version}.csv")
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ["species"])
        w.writeheader()
        w.writerows(rows)
    print(f"\n  per-species table: {out}")


if __name__ == "__main__":
    main()
