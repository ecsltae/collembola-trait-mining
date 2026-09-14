"""
Score an extraction version against the partner adjudication set.

A case is resolved when the specific value the reviewers objected to no longer appears in
the primary column. Cases whose verdict keeps a value additionally require the note the
reviewers asked for.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from trait_extraction_v3 import extract_body_size, extract_habitat, extract_trophic  # noqa: E402

CK_KEY = {"trophic_guild": "trophic", "body_size": "size", "habitat": "habitat"}


def run_v3(ck: dict, trait: str, species: str) -> tuple[str, str, str]:
    """Return (primary value, note, evidence type) for one trait."""
    answer = (ck.get(CK_KEY[trait], {}) or {}).get("answer", "")
    if trait == "trophic_guild":
        r = extract_trophic(answer, species)
        return "|".join(r["guilds"]), r["note"], r["evidence_type"]
    if trait == "body_size":
        r = extract_body_size(answer, species)
        return r["range_mm"], r["note"], r["evidence_type"]
    r = extract_habitat(answer, species)
    return "|".join(r["habitats"]), r["note"], r["evidence_type"]


def toks(value: str) -> set[str]:
    return {t.strip() for t in (value or "").split("|") if t.strip()}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", default="review_adjudication_2026-09.csv")
    ap.add_argument("--checkpoints", default="results/checkpoints_species_v2")
    ap.add_argument("--show", default="", help="only print cases of this failure class")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    ck_dir = Path(args.checkpoints)
    gold = list(csv.DictReader(open(args.gold)))

    per_class: dict[str, Counter] = {}
    failures = []

    for row in gold:
        sp, trait = row["species"], row["trait"]
        path = ck_dir / (sp.replace(" ", "_") + ".json")
        if not path.exists():
            continue
        ck = json.loads(path.read_text())
        new, note, ev = run_v3(ck, trait, sp)

        bad = toks(row["current_value"]) - toks(row["expected_value"])
        if trait == "body_size":
            # Ranges are not token sets: the old value is wrong unless it became the expected one.
            resolved = (new == "" or new == row["expected_value"])
        else:
            resolved = not (bad & toks(new))

        # Verdicts that keep a value also need the note the reviewers asked for.
        if row["verdict"] in ("keep_with_note", "keep_fix_note"):
            resolved = bool(toks(new) & toks(row["expected_value"])) and (
                bool(note) or ev == "experimental")
        elif row["verdict"] == "add":
            resolved = new == row["expected_value"]
        elif row["verdict"] == "revise" and row["expected_value"]:
            if trait != "body_size":
                resolved = resolved and bool(toks(new) & toks(row["expected_value"]))

        # Two properties, and they are not the same thing. Removing a wrong value is a
        # property of extraction. Recovering the right value usually needs the source text,
        # which means re-running QA, not re-reading a cached answer.
        if trait == "body_size":
            harm_removed = (new != row["current_value"]) or not row["current_value"]
        else:
            harm_removed = not (bad & toks(new))

        cls = row["failure_class"]
        c = per_class.setdefault(cls, Counter())
        c["total"] += 1
        c["harm"] += int(harm_removed)
        c["resolved" if resolved else "open"] += 1
        if not resolved:
            failures.append((sp, trait, cls, row["current_value"], new, row["expected_value"], note))

    tot = sum(c["total"] for c in per_class.values())
    res = sum(c["resolved"] for c in per_class.values())
    harm = sum(c["harm"] for c in per_class.values())
    print(f"Rejected value no longer assigned : {harm}/{tot} ({100*harm/tot:.0f}%)")
    print(f"Reviewer's expected value reached : {res}/{tot} ({100*res/tot:.0f}%)\n")
    print(f"{'failure class':34} {'wrong gone':>11} {'fully right':>12} {'total':>6}")
    for cls in sorted(per_class, key=lambda c: -per_class[c]["total"]):
        c = per_class[cls]
        print(f"{cls:34} {c['harm']:>11} {c['resolved']:>12} {c['total']:>6}")

    if failures and (args.verbose or args.show):
        print("\nOpen cases:")
        for sp, trait, cls, old, new, exp, note in failures:
            if args.show and cls != args.show:
                continue
            print(f"  {sp:26} {trait:13} [{cls}]")
            print(f"      was={old!r}  now={new!r}  expected={exp!r}")
            if note:
                print(f"      note={note[:120]}")


if __name__ == "__main__":
    main()
