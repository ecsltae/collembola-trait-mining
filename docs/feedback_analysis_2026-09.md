# Analysis of Montagna & Costagliola feedback, September 2026

Source: `feedback/2026-09-14_montagna_costagliola_issues.docx`, reviewing
`results/collembola_species_traits.csv` (330 species).

## Scale of the problem

| Trait | Assigned | Rejected by review | Error rate |
|---|---:|---:|---:|
| Trophic guild | 40 | 27 | **68%** |
| Body size | 27 | 15 | **56%** |
| Habitat | 221 | 13 | unknown — partners checked only a subset and reported failures only |

Only 13 trophic assignments survived: *Ceratophysella denticulata, Cryptopygus clavatus,
Cyphoderus albinus, Entomobrya multifasciata, E. unostrigata, Folsomia quadrioculata,
Folsomides parvulus, Hemisotoma thermophila, Isotomiella minor, Orchesella cincta,
Proisotoma minuta, Protaphorura armata, P. cancellata*. Those were not positively
confirmed either, only not flagged.

The habitat denominator matters and we do not have it. Worth asking Matteo how many
species he checked, otherwise 13 reads as "13 out of 221" when it may be "13 out of 20".

## One root cause

The July fix worked at the level it operated on: retrieval now returns documents that
genuinely concern the target species. Every remaining problem is one level down.

**Extraction still runs over whole documents.** The keyword maps and the body-size regex
scan the entire QA answer and document text, so any matching token anywhere in an
on-target document can produce a label. What is missing is *claim-level attribution*:
which sentence asserts what, about which species, on what kind of evidence.

Two cases make this concrete. For *Friesea truncata* the correct body length (0.73–0.76 mm)
is present in the Plazi treatment we already retrieved, but we returned the value for
*Friesea major* from elsewhere in the same document. For *Neelus koseli* the correct
0.9–1.0 mm was in the document and we captured the head measurement instead. Right
document, wrong sentence.

## Failure classes

### Trophic guild (27 species)

Classes overlap; a species can appear in more than one.

**A. Occurrence treated as diet — 9 species.** Found in soil, litter, *Pinus* debris or
decomposed plant material, therefore labelled detritivore or herbivore. Matteo's position
is unambiguous: the substrate a species is found in is not evidence of what it eats.
*Folsomia spinosa, Friesea mirabilis, Isotomurus balteatus, Protaphorura subarmata,
Sminthurinus elegans, Tomocerina minuta, Willemia denisi, W. scandinavica,
Xenylla mediterranea.*

**B. Predator–prey direction reversed — 4 species.** The species is the prey, not the
predator. Known limitation, already documented in the README, still unfixed.
*Folsomia candida, Isotoma anglicana* (prey of spiders, PMID 14629361), *Isotoma riparia,
Lepidocyrtus cyaneus.*

**C. Laboratory evidence not marked as such — 7 species.** The label is often defensible
but must carry a note; feeding-preference trials show what an animal will accept, not what
it eats in the field. *Folsomia fimetaria, F. fimetarioides, Hypogastrura assimilis,
H. viatica, Neanura muscorum, Protaphorura fimata, Vertagopus pseudocinereus.*

**D. Statement about Collembola in general applied to a species — 2 species.**
*Sminthurinus niger, Vertagopus glacialis.*

**E. Label contradicts the evidence that is present — 8 species.** Here the source does
support something, just not what we wrote. *Folsomia fimetaria* (omnivore → microbivore),
*Isotoma caerulea, Isotomurus maculatus, Orchesella villosa* (bacterivore unsupported;
algae/plant/microbial use is what is documented), *Neanura moldavica* (no fungivory in the
sources at all), *Protaphorura fimata* (fungivore → herbivore + fungivore),
*Vertagopus glacialis* (omnivore → herbivore–detritivore), *Heteromurus nitidus* (label
correct, but our note asserts animal/omnivorous feeding the sources do not support).

### Body size (15 species)

**Congeneric contamination — 13 species.** A measurement from the right document but the
wrong species of the same genus. *Deutonura gibbosa* ← *D. zana*; *Entomobrya handschini*
← *E. maroccana*; *E. marginata* ← *E. boneti*; *Folsomia bisetosa* ← *F. mofettophila*;
*F. sensibilis* ← *F. minorae*; *Friesea truncata* ← *F. major*; *Mesogastrura libyca* ←
*M. seotalensis*; *Micranurida pygmaea* ← *M. hunanensis*; *Onychiurus ambulans* ←
*O. heilongjiangensis*; *Protaphorura janosik* ← *P. borinensis*; *Pseudosinella decipiens*
← cf. *decipiens* and *P. jacetanica*; *Stenaphorura quadrispina* ← *S. lubbocki*;
*Supraphorura furcifera* ← *S. chernovae*.

**Wrong measurement captured — 1 species.** *Neelus koseli*: head length, not body length.

**Recall misses — 2 species.** *Folsomia fimetaria* (0.8–1.4 mm, PMID 28310911 — a document
we already used for its trophic guild) and *Entomobrya unostrigata* (3.91 mm, Plazi
BF8EAF45DE025E92A6EBEE16636CD03).

### Habitat (13 species)

**Geography read as ecology — 7 species.** The largest class and the one Matteo raises as
a matter of agreed criteria. A locality, coordinate or altitude is not a habitat
description. *Anurida granulata* (Savoy, 950–2150 m → alpine_glacier; the only ecological
statement in the source is "sol acide"), *Deutonura gibbosa* (alpine_glacier from
localities), *D. provincialis* (holm-oak forest litter → cave | marine_coastal),
*Lathriopyga longiseta* (Corsica → marine_coastal), *Parisotoma agrelli* (Roscoff →
marine_coastal), *Bilobella aurantiaca* (decaying wood and moss → marine_coastal),
*Hemisotoma thermophila* (grassland and soil supported; freshwater and marine_coastal not —
salt-land pasture is a terrestrial saline environment).

**Periodic flooding read as aquatic — 1 species.** *Anurida tullbergi* is described as
terrestrial, dominant in floodplains, surviving inundation at the egg stage. Not freshwater.

**Experimental substrate read as habitat — 1 species.** *Folsomia fimetaria*: agricultural
and sandy_dune come from a study run in sandy agricultural soil.

**Source carries no ecological information — 3 species.** Distribution records and
barcoding data only. *Desoria fennica, Deutonura caerulescens, D. stachi.*

**Source is about another species — 1 species.** *Bilobella braunerae*: the source concerns
*B. aurantiaca* and mentions *braunerae* only as a doubtful record the authors attribute to
an aberrant *aurantiaca* specimen.

## Proposed v3

### 1. Sentence-scoped, subject-bound extraction

Attribute a value only when the target binomial is the subject of the sentence carrying it,
or — for Plazi treatments, where measurements sit under a species heading — when the nearest
preceding taxon heading is the target. Resolves all 13 congeneric body-size cases,
*Bilobella braunerae*, and the general-Collembola cases.

### 2. Evidence-type classification

Classify the sentence supporting each value, and keep the class in the output:

| Class | Cues | Effect on trophic guild |
|---|---|---|
| `direct` | feeds on, gut contents, stable isotope, field diet | assign |
| `experimental` | was fed, microcosm, laboratory culture, feeding-preference trial, bait | assign **with a note** |
| `co_occurrence` | found in, collected from, occurs in, associated with | **reject** |
| `prey_of` | preyed upon by, prey of, consumed by | **reject** |
| `non_specific` | subject is Collembola / springtails / the genus | **reject**, flag |

Classes A, B, C and D fall out of this directly. It is also the note Matteo has now asked
for twice — in the meeting ("when experiments it needs to be noted") and in this document.

### 3. Habitat must come from an ecological descriptor, not a place

A label requires a habitat word, not a toponym. Concretely: filter placenames, coordinates
and elevations out of the matching text; require `alpine_glacier` to rest on
glacier/glacial/nival/supraglacial used ecologically rather than on an alpine locality;
require `marine_coastal` to rest on intertidal/littoral/shore/seaweed/rock-pool rather than
on an island or coastal town; treat floodplain and periodic inundation as terrestrial.
Resolves 9 of the 13 habitat cases.

### 4. Two-tier output instead of one column

This answers the precision-versus-recall question I put to the partners in the meeting, and
Matteo's review has effectively answered it: assign only on explicit, species-specific
statements. But discarding the indirect evidence loses information that is useful for other
purposes, so keep it rather than drop it:

- `trophic_guild` — explicit, species-specific, direct or noted-experimental evidence.
- `trophic_guild_indirect` — inferred, with the reason recorded (`substrate`, `congeneric`,
  `genus_level`, `general_collembola`).

Same shape for habitat. Precision in the primary column, recall preserved beside it, both
traceable.

New columns per trait: `*_evidence_type`, `*_note`, `*_species_specific`, and `*_life_stage`
(requested in the meeting).

### 5. Things that are not a mining problem at all

Geography, collection date and life stage were all requested in the meeting, and all three
are already in `data/bold_collembola_180226.csv` per specimen (`coord`, `elev`,
`collection_date_start`, `life_stage`, plus `biome`, `ecoregion`, `country.ocean`). These
are a join, not a QA task.

BOLD also carries its own per-specimen `habitat` field. That is an independent reference
against which our literature-mined habitat categories can be scored — a free quantitative
evaluation, and the answer to Savvas's request for quantitative material, without waiting
on further manual annotation.

## Expected effect

Trophic guild will fall from 40 to roughly 15–20 in the primary column, with the remainder
moving to the indirect column rather than vanishing. Body size drops to about 12 verified,
plus the 2 recovered recall misses. This is the same trade as the July fix: fewer values,
each one defensible.

## This review is now an evaluation set

56 adjudicated species-trait pairs with expert reasoning attached. That is the gold standard
for measuring whether v3 actually fixes anything, and it should be encoded as a test fixture
rather than read as prose.
