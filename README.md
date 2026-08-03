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
| `trophic_n_docs` | Number of species-specific documents the answer was based on (0 = no species-specific evidence) |
| `trophic_sources` | Source document IDs (PMID / PMCID / Plazi) |
| `body_size_range_mm` | Body length parsed from the answer, in mm (single value or `min-max`) |
| `body_size_measurements_mm` | All plausible measurements found (0.1–15 mm), pipe-separated |
| `body_size_qa_answer` | Grounded answer to "What is the body length of *{species}*?" |
| `body_size_n_docs` | Species-specific documents behind the size answer |
| `body_size_sources` | Source document IDs |
| `habitat_categories` | Habitat class(es): soil, leaf_litter, moss_lichen, cave, forest_wood, grassland, freshwater, marine_coastal, alpine_glacier, agricultural, synanthropic, sandy_dune |
| `habitat_qa_answer` | Grounded answer to "What is the habitat of *{species}*?" |
| `habitat_n_docs` | Species-specific documents behind the habitat answer |
| `habitat_sources` | Source document IDs |

## Method

For each species and trait, retrieval **requires the full binomial as an adjacent phrase**
(genus + specific epithet linked together) across the Medline + PMC + Plazi collections, so
the specific epithet alone can never match a different organism that happens to share it
(e.g. "*polaris*" → the stonefly *Arcynopteryx polaris*, "*gibbosa*" → the snail *Chilina
gibbosa*). Trait-relevant terms are added as a soft ranking boost so, among the
right-organism documents, the ones describing the trait rank first. A **generative SIBILS QA**
answer (Qwen3-8B) is then produced from exactly those documents, and structured values are
derived from it:

- **Trophic guild** — keyword mapping onto the standard soil-fauna scheme (Potapov et al.
  2022, *Soil Biology & Biochemistry*): fungivore, bacterivore, algivore, herbivore,
  detritivore, predator, omnivore.
- **Body size** — measurements parsed from the answer text and normalised to mm (0.1–15 mm).
- **Habitat** — keyword mapping onto the habitat classes listed above.
- **NCBI taxid** — resolved via NCBI E-utilities (`esearch`), falling back to the genus ID
  when the species name is not in NCBI Taxonomy (recorded in `taxid_matched_rank`).

If no document mentions the full binomial, the trait is left blank — **no information from a
different taxon is ever assigned to a species** (`*_n_docs = 0`).

## Results at a glance

| | Species |
|---|---:|
| Total species | 330 |
| NCBI taxid resolved | 323 (244 species-level, 79 genus-level) |
| Trophic guild assigned | 40 |
| Body size extracted | 27 |
| Habitat inferred | 221 |

Species-level literature is sparse: most species have documents that mention them (typically
Plazi taxonomic treatments) but do not state diet or size. Only assignments with genuine
species-specific evidence are recorded — hence the conservative counts.

## Caveats

Read the QA answer and follow the source IDs before relying on any value.

- **Sparse where the literature is silent.** Many species have never had their diet, size, or
  habitat described — those rows read `unknown` / empty rather than borrowing a value from a
  congener or a different organism. This is deliberate.
- **Trophic guild — predator over-assignment.** The keyword mapper cannot yet tell "X preys on
  Y" from "Y preys on X". Collembola are common prey, so some `predator` labels reflect the
  species being *eaten*. Check the `trophic_qa_answer` before trusting a predator label.
- **Body size is conservative.** Measurements are only taken from documents that pass the
  binomial-phrase filter; taxonomic descriptions in Plazi carry many more measurements that a
  future pass could mine more aggressively.
- **Habitat** is keyword-based and multi-label; a class may reflect an incidental mention.
- **NCBI taxid** uses `esearch`; `taxid_matched_rank = genus` means the species name was not
  found and the genus ID is given instead, and NCBI synonyms can map two names to one ID.

## Provenance

Values are literature-grounded and auditable: each trait carries the SIBILS QA answer, the
number of species-specific documents it rests on (`*_n_docs`), and the source document IDs.
No manual curation was applied to the values in this file.
