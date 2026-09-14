#!/usr/bin/env python3
"""
Collembola trophic guild extraction via BioMoQA-RAG + MetaP classifier.

For each of the 102 Collembola genera in the BOLD CSV:
  1. Query BioMoQA-RAG: "What does {genus} feed on?" (generative, all collections)
  2. Send cited passages through MetaP biotic interaction classifier
  3. Map free-text answers + feeding sentences to standard trophic guilds
  4. Optionally query BiotXplorer community check for literature interaction scores
  5. Write genus-level and species-level output CSVs

Usage:
  python scripts/collembola_trophic_batch.py [options]

  --csv PATH           BOLD CSV path (default: "collembola_Bold_180226.xlsx - collemboli2.csv")
  --api URL            BioMoQA-RAG base URL (default: https://qa.dev.sibils.org/api)
  --classifier URL     MetaP classifier URL (default: http://localhost:8001)
  --output PATH        Genus-level output CSV (default: results/collembola_trophic_guilds.csv)
  --species-output P   Species-level output CSV (default: results/collembola_species_guilds.csv)
  --checkpoint-dir D   Per-genus JSON checkpoint dir (default: results/checkpoints/)
  --skip-classifier    Skip MetaP classification (if port 8001 not running)
  --biotxplorer        Enable BiotXplorer community check (port 8010, slow ~10 min)
  --delay SECS         Delay between QA calls (default: 0.3)
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
# Trophic guild keyword mapping
# Based on Potapov et al. 2022 (Soil Biol. Biochem.) guild scheme for Collembola:
#   fungivore, bacterivore, herbivore/algivore, predator, detritivore, omnivore
# ---------------------------------------------------------------------------

GUILD_KEYWORDS: dict[str, list[str]] = {
    "fungivore": [
        "fung", "hyphae", "hypha", "mycelium", "mycorrhiz", "spore", "yeast",
        "mold", "mould", "mushroom", "oomycete", "ergosterol",
    ],
    "bacterivore": [
        "bacteri", "microorganism", "microbe", "microbial community",
        "prokaryote", "archaea",
    ],
    "algivore": [
        "alga", "algae", "diatom", "cyanobacteri", "microalga", "biofilm",
        "green alga", "lichen photobiont",
    ],
    "herbivore": [
        "plant root", "root hair", "pollen", "seed", "leaf litter fungi",
        "moss", "lichen", "liverwort", "bryophyte", "epiphyte",
        "plant tissue", "vascular plant",
    ],
    "predator": [
        "prey", "predat", "hunt", "capture", "nematode", "mite", "collembola",
        "arthropod", "protozoa", "tardigrade", "enchytraeid", "parasite",
    ],
    "detritivore": [
        "detritus", "decompos", "organic matter", "litter", "humus",
        "soil organic", "carrion", "dead plant", "dead wood",
    ],
    "omnivore": [
        "omnivore", "generalist", "opportunistic", "various food",
        "mixed diet", "multiple food source",
    ],
}

# Confidence: how many keyword hits before assigning a guild (≥1 hit assigns it)
_COMPILED: dict[str, list[re.Pattern]] = {
    guild: [re.compile(kw, re.IGNORECASE) for kw in kws]
    for guild, kws in GUILD_KEYWORDS.items()
}

def infer_guilds(texts: list[str]) -> list[str]:
    """
    Score each guild against a list of text fragments.
    Returns guilds with ≥1 keyword hit, sorted by hit count descending.
    If nothing matches, returns ["unknown"].
    """
    scores: dict[str, int] = {g: 0 for g in GUILD_KEYWORDS}
    combined = " ".join(texts).lower()
    for guild, patterns in _COMPILED.items():
        for pat in patterns:
            if pat.search(combined):
                scores[guild] += 1
    matched = [g for g, s in scores.items() if s > 0]
    matched.sort(key=lambda g: -scores[g])
    if not matched:
        return ["unknown"]
    # Collapse omnivore: if ≥3 guilds, call it omnivore
    if len(matched) >= 3 and "omnivore" not in matched:
        matched = ["omnivore"] + matched
    return matched


# ---------------------------------------------------------------------------
# CSV loading
# ---------------------------------------------------------------------------

def load_bold_csv(csv_path: str) -> tuple[list[dict], list[dict]]:
    """
    Returns:
      genera: list of {genus, family}, deduplicated
      species: full list of rows with at least {processid, species, genus, family, ...}
    """
    seen_genera: set[str] = set()
    genera: list[dict] = []
    species_rows: list[dict] = []

    with open(csv_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            genus = (row.get("genus") or row.get("Genus") or "").strip()
            family = (row.get("family") or row.get("Family") or "").strip()
            sp = (row.get("species") or row.get("Species") or "").strip()
            pid = (row.get("processid") or "").strip()
            if genus and genus not in seen_genera:
                seen_genera.add(genus)
                genera.append({"genus": genus, "family": family})
            if genus:
                species_rows.append({
                    "processid": pid,
                    "species": sp,
                    "genus": genus,
                    "family": family,
                })

    genera.sort(key=lambda x: x["genus"])
    return genera, species_rows


# ---------------------------------------------------------------------------
# BioMoQA-RAG query
# ---------------------------------------------------------------------------

def query_biomoqa(genus: str, api_url: str, timeout: int = 60) -> Optional[dict]:
    url = f"{api_url.rstrip('/')}/qa"
    payload = {
        "question": f"What does {genus} feed on?",
        "mode": "generative",
        "retrieval": "sparse",
    }
    try:
        resp = requests.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        print(f"  [ERROR] BioMoQA-RAG query failed for {genus}: {exc}", file=sys.stderr)
        return None


def parse_biomoqa_response(data: dict) -> dict:
    best_answer = ""
    best_score = -1.0
    best_collection = ""
    all_docids: list[str] = []
    all_passages: list[str] = []

    for col_result in data.get("collection_results") or []:
        collection = col_result.get("collection", "")
        answers = col_result.get("answers") or []
        if not answers:
            continue
        top = answers[0]
        score = top.get("answer_score") or 0.0
        answer_text = top.get("answer") or ""
        if score > best_score and answer_text:
            best_score = score
            best_answer = answer_text
            best_collection = collection
        for ans in answers:
            for doc in ans.get("docs") or []:
                docid = doc.get("docid") or ""
                if docid:
                    all_docids.append(f"{docid}({doc.get('doc_source','')})")
                text = doc.get("doc_text") or ""
                if text and text not in all_passages:
                    all_passages.append(text)

    return {
        "qa_has_answer": bool(best_answer),
        "qa_answer": best_answer,
        "qa_best_collection": best_collection,
        "qa_source_docids": "|".join(dict.fromkeys(all_docids)),
        "n_docs_retrieved": len(all_passages),
        "passages": all_passages,
    }


# ---------------------------------------------------------------------------
# Sentence splitting
# ---------------------------------------------------------------------------

_SENTENCE_SEP = re.compile(r"(?<=[.!?])\s+")

def split_sentences(text: str, min_len: int = 20) -> list[str]:
    parts = _SENTENCE_SEP.split(text.strip())
    return [p.strip() for p in parts if len(p.strip()) >= min_len]


# ---------------------------------------------------------------------------
# MetaP biotic interaction classifier
# ---------------------------------------------------------------------------

def classify_sentences(sentences: list[str], classifier_url: str, timeout: int = 30) -> list[str]:
    """Return sentences labeled biotic_interaction by MetaP."""
    if not sentences:
        return []
    url = f"{classifier_url.rstrip('/')}/predict/batch"
    payload = {"sentences": sentences}
    try:
        resp = requests.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        return [
            sent for pred, sent in zip(data.get("predictions") or [], sentences)
            if pred.get("label") == "biotic_interaction"
        ]
    except Exception as exc:
        print(f"  [WARN] MetaP classifier error: {exc}", file=sys.stderr)
        return []


# ---------------------------------------------------------------------------
# BiotXplorer community check
# ---------------------------------------------------------------------------

def biotxplorer_check(genus_names: list[str], port: int = 8010, timeout: int = 600) -> dict[str, dict]:
    """
    POST /check to community check API. Returns {genus: {partners, max_score}}.
    Slow: BiotXplorer is rate-limited ~25 req/min.
    """
    url = f"http://localhost:{port}/check"
    payload = {"sample_id": "collembola_bold", "species": genus_names, "use_biotxplorer": True}
    try:
        resp = requests.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        print(f"  [ERROR] BiotXplorer /check failed: {exc}", file=sys.stderr)
        return {}

    results: dict[str, dict] = {}
    for sp in data.get("species") or []:
        name = sp.get("canonical") or ""
        genus = name.split()[0] if name else ""
        if not genus:
            continue
        partners = list(sp.get("interacts_with") or [])
        scores = sp.get("biotxplorer_scores") or {}
        max_score = max(scores.values(), default=0.0) if scores else 0.0
        results[genus] = {"partners": partners, "max_score": max_score}
    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Collembola trophic guild batch extraction")
    parser.add_argument("--csv", default="data/bold_collembola_180226.csv")
    parser.add_argument("--api", default="https://qa.dev.sibils.org/api")
    parser.add_argument("--classifier", default="http://localhost:8001")
    parser.add_argument("--output", default="results/collembola_trophic_guilds.csv")
    parser.add_argument("--species-output", default="results/collembola_species_guilds.csv")
    parser.add_argument("--checkpoint-dir", default="results/checkpoints_genus")
    parser.add_argument("--skip-classifier", action="store_true")
    parser.add_argument("--biotxplorer", action="store_true")
    parser.add_argument("--delay", type=float, default=0.3)
    args = parser.parse_args()

    checkpoint_dir = Path(args.checkpoint_dir)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)

    print(f"Loading from {args.csv} ...")
    genera, species_rows = load_bold_csv(args.csv)
    print(f"  {len(genera)} unique genera, {len(species_rows)} species records.")

    # --- Phase 1: BioMoQA-RAG QA (resumable via checkpoints) ---
    print(f"\nPhase 1: BioMoQA-RAG QA ({args.api})")
    qa_results: dict[str, dict] = {}

    for i, entry in enumerate(genera, 1):
        genus = entry["genus"]
        ckpt = checkpoint_dir / f"{genus}.json"
        if ckpt.exists():
            with open(ckpt) as fh:
                qa_results[genus] = json.load(fh)
            print(f"  [{i:3d}/{len(genera)}] {genus} — checkpoint")
            continue

        print(f"  [{i:3d}/{len(genera)}] {genus} ...", end="", flush=True)
        raw = query_biomoqa(genus, args.api)
        parsed = parse_biomoqa_response(raw) if raw else {
            "qa_has_answer": False, "qa_answer": "", "qa_best_collection": "",
            "qa_source_docids": "", "n_docs_retrieved": 0, "passages": [],
        }
        qa_results[genus] = parsed
        with open(ckpt, "w") as fh:
            json.dump(parsed, fh)
        status = "OK" if parsed["qa_has_answer"] else "no answer"
        print(f" {status} ({parsed['n_docs_retrieved']} docs)")
        time.sleep(args.delay)

    answered = sum(1 for v in qa_results.values() if v["qa_has_answer"])
    print(f"  {answered}/{len(genera)} genera with QA answers.")

    # --- Phase 2: MetaP classifier ---
    interaction_sentences: dict[str, list[str]] = {}

    if not args.skip_classifier:
        print(f"\nPhase 2: MetaP biotic interaction classifier ({args.classifier})")
        for i, entry in enumerate(genera, 1):
            genus = entry["genus"]
            passages = qa_results[genus].get("passages") or []
            sentences = []
            for p in passages:
                sentences.extend(split_sentences(p))
            hits = classify_sentences(sentences, args.classifier) if sentences else []
            interaction_sentences[genus] = hits
            print(f"  [{i:3d}/{len(genera)}] {genus}: {len(sentences)} sent → {len(hits)} interactions")
    else:
        print("\nPhase 2: skipped (--skip-classifier)")
        for entry in genera:
            interaction_sentences[entry["genus"]] = []

    # --- Phase 3: Trophic guild inference ---
    print("\nPhase 3: Trophic guild inference")
    guild_map: dict[str, list[str]] = {}
    for entry in genera:
        genus = entry["genus"]
        qa = qa_results[genus]
        texts = [qa.get("qa_answer") or ""] + (interaction_sentences.get(genus) or [])
        guilds = infer_guilds(texts)
        guild_map[genus] = guilds
        print(f"  {genus:20s} → {', '.join(guilds)}")

    # --- Phase 4: BiotXplorer (optional) ---
    biotx_data: dict[str, dict] = {}
    if args.biotxplorer:
        print(f"\nPhase 4: BiotXplorer community check (port 8010) — may take ~10 min ...")
        genus_names = [e["genus"] for e in genera]
        biotx_data = biotxplorer_check(genus_names)
        print(f"  Resolved {len(biotx_data)} genera.")

    # --- Write genus-level CSV ---
    genus_fields = [
        "genus", "family",
        "trophic_guilds", "trophic_guild_primary",
        "qa_has_answer", "qa_answer", "qa_best_collection",
        "qa_source_docids", "n_docs_retrieved",
        "interaction_sentences", "n_interaction_sentences",
    ]
    if args.biotxplorer:
        genus_fields += ["biotxplorer_partners", "biotxplorer_max_score"]

    print(f"\nWriting genus-level output to {args.output} ...")
    with open(args.output, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=genus_fields)
        writer.writeheader()
        for entry in genera:
            genus = entry["genus"]
            qa = qa_results[genus]
            sents = interaction_sentences.get(genus) or []
            guilds = guild_map[genus]
            row = {
                "genus": genus,
                "family": entry["family"],
                "trophic_guilds": "|".join(guilds),
                "trophic_guild_primary": guilds[0],
                "qa_has_answer": qa["qa_has_answer"],
                "qa_answer": qa["qa_answer"],
                "qa_best_collection": qa["qa_best_collection"],
                "qa_source_docids": qa["qa_source_docids"],
                "n_docs_retrieved": qa["n_docs_retrieved"],
                "interaction_sentences": "||".join(sents),
                "n_interaction_sentences": len(sents),
            }
            if args.biotxplorer:
                bx = biotx_data.get(genus) or {}
                row["biotxplorer_partners"] = "|".join(bx.get("partners") or [])
                row["biotxplorer_max_score"] = bx.get("max_score", "")
            writer.writerow(row)

    # --- Write species-level CSV ---
    # Build genus → guild lookup
    genus_to_guilds = {e["genus"]: guild_map[e["genus"]] for e in genera}

    species_fields = [
        "processid", "species", "genus", "family",
        "trophic_guilds", "trophic_guild_primary",
    ]
    print(f"Writing species-level output to {args.species_output} ...")
    with open(args.species_output, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=species_fields)
        writer.writeheader()
        for row in species_rows:
            genus = row["genus"]
            guilds = genus_to_guilds.get(genus, ["unknown"])
            writer.writerow({
                "processid": row["processid"],
                "species": row["species"],
                "genus": genus,
                "family": row["family"],
                "trophic_guilds": "|".join(guilds),
                "trophic_guild_primary": guilds[0],
            })

    print(f"Done.")
    print(f"\nSummary:")
    print(f"  Genera with QA answer:        {answered}/{len(genera)}")
    with_int = sum(1 for g in genera if interaction_sentences.get(g["genus"]))
    print(f"  Genera with feeding sentences: {with_int}/{len(genera)}")
    guild_counts: dict[str, int] = {}
    for guilds in guild_map.values():
        guild_counts[guilds[0]] = guild_counts.get(guilds[0], 0) + 1
    print(f"  Primary guild distribution:")
    for g, c in sorted(guild_counts.items(), key=lambda x: -x[1]):
        print(f"    {g:15s} {c}")
    print(f"\n  Genus CSV:   {args.output}")
    print(f"  Species CSV: {args.species_output}")


if __name__ == "__main__":
    main()
