# Collembola functional traits from literature (SIBILS QA)

Species-level functional-trait annotations for **330 Collembola species** (from a BOLD
COI barcode dataset), mined from the published literature with the
[SIBILS](https://sibils.org) question-answering service. Three traits are covered —
**trophic guild, body size, and habitat** — and every value is traceable to the source
document(s) it came from. NCBI Taxonomy IDs are included so the taxonomic path of each
taxon can be verified.

This is the species-level revision of an earlier genus-level trial, following reviewer
feedback that guilds should be assigned per species rather than extrapolated across a genus.

## Data

[`collembola_species_traits.csv`](collembola_species_traits.csv) — one row per species (330 rows).

| Column | Description |
|---|---|
| `species` | Binomial name (as recorded in the BOLD dataset) |
| `genus`, `family` | Higher taxonomy from BOLD |
| `ncbi_taxid` | NCBI Taxonomy ID |
| `taxid_matched_rank` | `species` = exact species match · `genus` = species not in NCBI, genus ID used · empty = unresolved |
| `trophic_guilds` | All guilds with textual support (pipe-separated) |
| `trophic_guild_primary` | Best-supported guild, or `unknown` |
| `trophic_qa_answer` | Grounded SIBILS QA answer to "What does *{species}* feed on?" |
| `trophic_sources` | Source document IDs (PMID / PMCID / Plazi) |
| `body_size_range_mm` | Body length parsed from the answer, in mm (single value or `min-max`) |
| `body_size_measurements_mm` | All plausible measurements found (0.1–15 mm), pipe-separated |
| `body_size_qa_answer` | Grounded answer to "What is the body length of *{species}*?" |
| `body_size_sources` | Source document IDs |
| `habitat_categories` | Habitat class(es): soil, leaf_litter, moss_lichen, cave, forest_wood, grassland, freshwater, marine_coastal, alpine_glacier, agricultural, synanthropic, sandy_dune |
| `habitat_qa_answer` | Grounded answer to "What is the habitat of *{species}*?" |
| `habitat_sources` | Source document IDs |

## Method

For each species, three natural-language questions are put to **SIBILS QA** (generative
mode, Qwen3-8B over the Medline + Plazi + PMC collections). The grounded answer and its
cited source documents are stored verbatim. Structured values are then derived from the
answers:

- **Trophic guild** — keyword mapping onto the standard soil-fauna scheme (Potapov et al.
  2022, *Soil Biology & Biochemistry*): fungivore, bacterivore, algivore, herbivore,
  detritivore, predator, omnivore.
- **Body size** — measurements parsed from the answer text and normalised to mm, keeping
  biologically plausible values (0.1–15 mm).
- **Habitat** — keyword mapping onto the habitat classes listed above.
- **NCBI taxid** — resolved via NCBI E-utilities (`esearch`), falling back to the genus ID
  when the species name is not in NCBI Taxonomy (recorded in `taxid_matched_rank`).

## Results at a glance

| | Species |
|---|---:|
| Total species | 330 |
| NCBI taxid resolved | 323 (244 species-level, 79 genus-level) |
| Trophic guild assigned | 66 |
| Body size extracted | 104 |
| Habitat inferred | 250 |

Trophic-guild spread (primary): fungivore 21 · detritivore 16 · predator 11 · omnivore 8 ·
algivore 5 · bacterivore 5 · unknown 264.

## Caveats

Read the QA answer and follow the source IDs before relying on any value.

- **Sparse where the literature is silent.** Many species have never had their diet, size,
  or habitat described in the indexed literature — those rows read `unknown` / empty rather
  than borrowing a value from a congener. This is deliberate.
- **Trophic guild — predator over-assignment.** The keyword mapper cannot tell "X preys on
  Y" from "Y preys on X". Collembola are common prey, so some `predator` labels reflect the
  species being *eaten* rather than hunting. Check the `trophic_qa_answer` before trusting a
  predator label.
- **Body size** is regex-parsed from free text and may occasionally capture a measurement of
  something other than the whole animal — verify against `body_size_sources`.
- **Habitat** is keyword-based and multi-label; a class may reflect an incidental mention.
- **NCBI taxid** uses `esearch` name resolution; `taxid_matched_rank = genus` means the
  species name was not found and the genus ID is given instead, and NCBI synonyms can map
  two names to one ID. Use `taxid_matched_rank` to gate on exact matches.

## Provenance

Values are literature-grounded and auditable: each trait carries the SIBILS QA answer and
the source document IDs it was derived from. No manual curation was applied to the values in
this file.
