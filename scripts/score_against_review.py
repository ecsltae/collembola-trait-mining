"""
Score an extraction version against one or more partner adjudication sets.

Two properties are reported, and they are not the same thing:

  wrong gone   the value the reviewers objected to is no longer in the primary column.
               That is something extraction can achieve by reading more carefully.
  fully right  the output also reaches the value the reviewers expected. That often
               needs the source text, because a cached QA answer summarises rather
               than reproduces its document.

Habitat categories changed between v3 (one axis) and v4 (EUNIS macrohabitat plus
microhabitat), so every habitat token, in the gold files and in the output, is mapped
onto the v4 scheme before comparison. v3's forest_wood maps to forest *and* dead wood,
because that conflation is exactly what the reviewers objected to: a case where they
asked for "forest" instead is scored as resolved when dead wood is gone and forest stays.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

CK_KEY = {"trophic_guild": "trophic", "body_size": "size", "habitat": "habitat"}

LEGACY_HABITAT = {
    "forest_wood":    {"G_woodland_forest", "deadwood"},
    "forest":         {"G_woodland_forest"},
    "woodland":       {"G_woodland_forest"},
    "grassland":      {"E_grassland"},
    "freshwater":     {"C_inland_water"},
    "marine_coastal": {"B_coastal", "A_marine"},
    "alpine_glacier": {"H_cave_ice_scree"},
    "cave":           {"H_cave_ice_scree"},
    "agricultural":   {"I_agricultural"},
    "synanthropic":   {"J_artificial", "dung_compost"},
    "sandy_dune":     {"B_coastal"},
    "floodplain":     set(),   # not a EUNIS class; floodplain species are terrestrial
}


def habitat_tokens(value: str) -> set[str]:
    out: set[str] = set()
    for t in (value or "").split("|"):
        t = t.strip()
        if t:
            out |= LEGACY_HABITAT.get(t, {t})
    return out


def toks(value: str, trait: str) -> set[str]:
    if trait == "habitat":
        return habitat_tokens(value)
    return {t.strip() for t in (value or "").split("|") if t.strip()}


def run(version: str, ck: dict, trait: str, species: str) -> tuple[str, str, str]:
    """Return (primary value, note, evidence type) for one trait."""
    mod = __import__(f"trait_extraction_{version}")
    answer = (ck.get(CK_KEY[trait], {}) or {}).get("answer", "")
    if trait == "trophic_guild":
        r = mod.extract_trophic(answer, species)
        return "|".join(r["guilds"]), r["note"], r["evidence_type"]
    if trait == "body_size":
        r = mod.extract_body_size(answer, species)
        return r["range_mm"], r["note"], r["evidence_type"]
    r = mod.extract_habitat(answer, species)
    if version == "v3":
        return "|".join(r["habitats"]), r["note"], r["evidence_type"]
    return "|".join(r["eunis"] + r["microhabitat"]), r["note"], r["evidence_type"]


def score(gold_path: str, version: str, ck_dir: Path, verbose: bool) -> tuple[int, int, int]:
    gold = list(csv.DictReader(open(gold_path)))
    per_class: dict[str, Counter] = {}
    failures = []

    for row in gold:
        sp, trait = row["species"], row["trait"]
        path = ck_dir / (sp.replace(" ", "_") + ".json")
        if not path.exists():
            continue
        new, note, ev = run(version, json.loads(path.read_text()), trait, sp)
        verdict, exp = row["verdict"], row["expected_value"]

        bad = toks(row["current_value"], trait) - toks(exp, trait)
        if trait == "body_size":
            harm_removed = (new != row["current_value"]) or not row["current_value"]
            resolved = new == "" or new == exp
        else:
            harm_removed = not (bad & toks(new, trait))
            resolved = harm_removed

        if verdict in ("keep_with_note", "keep_fix_note"):
            resolved = bool(toks(new, trait) & toks(exp, trait)) and (bool(note) or ev == "experimental")
        elif verdict == "add":
            resolved = new == exp
        elif verdict == "note_only":
            # Value must stay out of the primary column and the note must say whose it is.
            resolved = harm_removed = (new == "") and ("reported in the source is for" in note)
        elif verdict == "revise" and exp and trait != "body_size":
            resolved = resolved and toks(exp, trait) <= toks(new, trait)

        cls = row["failure_class"]
        c = per_class.setdefault(cls, Counter())
        c["total"] += 1
        c["harm"] += int(harm_removed)
        c["resolved"] += int(resolved)
        if not resolved:
            failures.append((sp, trait, cls, row["current_value"], new, exp))

    tot = sum(c["total"] for c in per_class.values())
    harm = sum(c["harm"] for c in per_class.values())
    res = sum(c["resolved"] for c in per_class.values())
    print(f"\n{Path(gold_path).name}  ({version})")
    print(f"  rejected value no longer assigned : {harm}/{tot} ({100*harm/tot:.0f}%)")
    print(f"  reviewer's expected value reached : {res}/{tot} ({100*res/tot:.0f}%)")
    if verbose:
        print(f"\n  {'failure class':34} {'wrong gone':>11} {'fully right':>12} {'total':>6}")
        for cls in sorted(per_class, key=lambda c: -per_class[c]["total"]):
            c = per_class[cls]
            print(f"  {cls:34} {c['harm']:>11} {c['resolved']:>12} {c['total']:>6}")
        if failures:
            print("\n  open cases:")
            for sp, trait, cls, old, new, exp in failures:
                print(f"    {sp:26} {trait:13} [{cls}]  was={old!r} now={new!r} expected={exp!r}")
    return harm, res, tot


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="v4", choices=["v3", "v4"])
    ap.add_argument("--gold", nargs="+",
                    default=["review_adjudication_2026-09.csv", "review_adjudication_2026-10_v3.csv"])
    ap.add_argument("--checkpoints", default="results/checkpoints_species_v2")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    for g in args.gold:
        score(g, args.version, Path(args.checkpoints), args.verbose)


if __name__ == "__main__":
    main()
