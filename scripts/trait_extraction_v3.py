"""
Claim-level trait extraction.

v2 ran keyword maps over the whole QA answer, so any token anywhere in an on-target
document could produce a label. The September 2026 partner review rejected 68% of trophic
guilds and 56% of body sizes that way.

v3 works sentence by sentence and asks three questions of each candidate value:

  1. Is the target species the subject of this sentence, or is it another taxon?
  2. Does the sentence assert the value, or hedge / deny it?
  3. What kind of evidence is it - direct observation, laboratory experiment,
     co-occurrence, or a predation relationship running the other way?

Values that survive go in the primary column. Values that fail go in an indirect column
with the reason, rather than being discarded.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Sentence segmentation and cue sets
# ---------------------------------------------------------------------------

_SENT_SPLIT = re.compile(r'(?<=[.!?])\s+(?=[A-Z*"“])')


def sentences(text: str) -> list[str]:
    if not text:
        return []
    text = re.sub(r'\s+', ' ', text).strip()
    return [s.strip() for s in _SENT_SPLIT.split(text) if s.strip()]


def _any(patterns: list[str]) -> re.Pattern:
    return re.compile("|".join(patterns), re.I)


# The answer says the information is absent. Anything after this in the same answer is
# reconstruction by the model, not a claim from the literature.
ABSENCE = _any([
    r"no (?:explicit |specific |direct |detailed )?(?:mention|information|data|evidence|details?|reference)",
    r"not (?:explicitly |specifically |directly )?(?:mentioned|stated|reported|described|provided|available|specified|detailed|given)",
    r"remains? (?:undocumented|unknown|unclear|unspecified)",
    r"(?:does|do) not (?:mention|provide|specify|describe|report|contain|include|indicate)",
    r"(?:is|are) (?:lacking|absent|not documented)",
    r"cannot be (?:determined|confirmed|established)",
    r"without (?:additional|direct|specific) (?:data|measurement|information)",
    r"further research would be needed",
    r"no information (?:regarding|about|on)",
])

# The sentence proposes rather than reports.
HEDGE = _any([
    r"\bsuggest(?:s|ing|ed)?\b", r"\bmay\b", r"\bmight\b", r"\blikely\b", r"\bprobabl\w*\b",
    r"\bcould\b", r"\bpresumabl\w*\b", r"\b(?:can be |be )?inferred\b", r"\bcomparable\b",
    r"\bappears? to\b", r"\bit is possible\b", r"\bpotentiall\w*\b", r"\bassumed\b",
    r"\bsuggestive\b", r"\bsuppos\w+\b", r"\bsuspect\w*\b", r"\bimpl(?:y|ies|ied)\b",
    r"\bsuch as .{0,30}\bwhich may\b", r"\bthough this cannot\b", r"\bwould be needed\b",
    r"\bsimilar to other species\b", r"\bcommon for springtails\b",
])

# The species is being eaten, not eating. Disqualifying for trophic guild.
PREY_OF = _any([
    r"\brole as prey\b", r"\bas prey\b", r"\bis prey\b", r"\bare prey\b",
    r"\bpart of the diet (?:for|of)\b", r"\bpreyed (?:upon|on)\b", r"\bprey (?:of|for|to|item)\b",
    r"\bconsumed by\b", r"\bfed upon by\b", r"\beaten by\b", r"\bpredators? such as\b",
    r"\bdiet (?:for|of) (?:predators?|spiders?|beetles?|mites?)\b", r"\bpredation on\b",
    r"\bcaptured by\b", r"\bfood (?:source |item )?for\b",
])

# Feeding shown under controlled conditions. Keep the label, mark the evidence.
EXPERIMENTAL = _any([
    r"\b(?:was|were|are|is|been) fed\b", r"\bexperimental\w*\b", r"\blaborator\w+\b",
    r"\bmicrocosm\w*\b", r"\bmesocosm\w*\b", r"\bin vitro\b", r"\bcultur(?:e|ed|ing|es)\b",
    r"\bexposed to\b", r"\bfeeding (?:preference|trial|experiment|test|choice)\w*\b",
    r"\bbait(?:ed)?\b", r"\brear(?:ed|ing)\b", r"\bbioassay\w*\b", r"\bchoice test\w*\b",
    r"\boffered\b", r"\bunder (?:controlled|experimental) conditions\b",
    r"\bgrowth (?:rate|test)\w*\b", r"\bsurviv\w+ on\b",
    r"\bsterile conditions\b", r"\bgrown under\b", r"\baxenic\b",
    r"\bsupport(?:s|ed)? the growth\b", r"\btoxic to\b", r"\bdietary preference\w*\b",
])

# Attracting or trapping an animal shows where it goes, not what it eats.
TRAPPING = _any([
    r"\battract(?:ed|ion)? to\b", r"\bbait(?:ed|s)?\b", r"\btrapp?(?:ed|ing)\b",
    r"\bpitfall\b", r"\bcaught (?:in|with|using)\b", r"\blured\b",
])

# Where the animal was, not what it ate. Valid habitat evidence, invalid diet evidence.
CO_OCCURRENCE = _any([
    r"\bfound (?:in|on|among|under|beneath)\b", r"\bcollected (?:from|in|at|on)\b",
    r"\brecorded (?:in|from|at|on)\b", r"\boccurs? (?:in|on)\b", r"\boccurrence\b",
    r"\bpresent in\b", r"\bdistributed (?:in|across|throughout)\b", r"\bassociated with\b",
    r"\blives? (?:in|on)\b", r"\bwas found\b", r"\bwere found\b", r"\bdwell\w*\b",
    r"\bin the debris\b", r"\bpresence of\b", r"\bsampled (?:in|from)\b",
])

# Statement is about springtails at large, not this species.
GENERIC_SUBJECT = _any([
    r"\bcollembola(?:ns?)?\b", r"\bspringtails?\b", r"\bsoil (?:fauna|invertebrates?|mesofauna)\b",
    r"\bthese (?:animals|organisms|species|insects)\b", r"\bin general\b",
    r"\bmany species\b", r"\bmost species\b", r"\bcommon for\b",
])

def answer_denies(answer: str) -> bool:
    """True if the answer states anywhere that the information is not in the sources.

    Answers frequently assert a value and then retract it - *Stenaphorura quadrispina*
    gives 1330 um, then says the measurement belongs to *S. lubbocki* and that the target's
    length is not stated. v2 read the first sentence only. A denial anywhere means nothing
    in the answer may be promoted to the primary column.
    """
    return any(ABSENCE.search(s) for s in sentences(answer))


_TAXON_RE = re.compile(r'\*?\b([A-Z][a-z]{2,})\s+([a-z]{3,})\b\*?')
_ABBREV_RE = re.compile(r'\*?\b([A-Z])\.\s*([a-z]{3,})\b\*?')

# Capitalised words that are not taxa and not places; keeps the geography filter honest.
_NOT_A_PLACE = {
    "Based", "However", "Additionally", "Therefore", "This", "These", "The", "Document",
    "Documents", "Further", "In", "It", "Although", "While", "Both", "Their", "Its",
    "According", "Such", "Other", "Species", "Also", "Moreover", "Furthermore", "Thus",
    "Specifically", "Overall", "Finally", "There", "They", "Some", "One", "Two", "DNA",
    # Geographic and descriptive adjectives that precede a lowercase noun and would
    # otherwise parse as a binomial ("East European tundra", "Mediterranean forest").
    "European", "African", "Asian", "American", "Australian", "Arctic", "Antarctic",
    "Atlantic", "Pacific", "Mediterranean", "Alpine", "Nordic", "Boreal", "Northern",
    "Southern", "Eastern", "Western", "Central", "East", "West", "North", "South",
    "British", "French", "German", "Italian", "Spanish", "Swiss", "Russian", "Chinese",
    "Japanese", "Korean", "Polish", "Czech", "Dutch", "Danish", "Swedish", "Norwegian",
}


def taxa_in(sentence: str) -> list[str]:
    """Binomials mentioned in a sentence, in order of appearance."""
    out = []
    for m in _TAXON_RE.finditer(sentence):
        genus, epithet = m.group(1), m.group(2)
        if genus in _NOT_A_PLACE:
            continue
        out.append((m.start(), f"{genus} {epithet}"))
    for m in _ABBREV_RE.finditer(sentence):
        out.append((m.start(), f"{m.group(1)}. {m.group(2)}"))
    return [name for _, name in sorted(out)]


def _matches_target(mention: str, target: str) -> bool:
    """True if a taxon mention refers to the target binomial (incl. 'F. candida')."""
    t_genus, _, t_epithet = target.partition(" ")
    m_genus, _, m_epithet = mention.partition(" ")
    if m_epithet != t_epithet:
        return False
    if m_genus == t_genus:
        return True
    return m_genus.rstrip(".") == t_genus[0]  # abbreviated genus


def classify(sentence: str, target: str) -> dict:
    """Describe what kind of claim a sentence makes and about whom."""
    mentions = taxa_in(sentence)
    on_target = any(_matches_target(m, target) for m in mentions)
    others = [m for m in mentions if not _matches_target(m, target)]
    t_genus = target.split()[0]
    congeneric = [m for m in others if m.split()[0].rstrip(".") in (t_genus, t_genus[0])]

    return {
        "text": sentence,
        "absence": bool(ABSENCE.search(sentence)),
        "hedged": bool(HEDGE.search(sentence)),
        "prey_of": bool(PREY_OF.search(sentence)),
        "experimental": bool(EXPERIMENTAL.search(sentence)),
        "co_occurrence": bool(CO_OCCURRENCE.search(sentence)),
        "generic": bool(GENERIC_SUBJECT.search(sentence)) and not on_target,
        "on_target": on_target,
        "other_taxa": others,
        "congeneric": congeneric,
        "no_taxon": not mentions,
    }


# ---------------------------------------------------------------------------
# Trophic guild
# ---------------------------------------------------------------------------

GUILD_KEYWORDS = {
    "fungivore":   ["fung", "hyphae", "hypha", "mycelium", "mycorrhiz", "spore", "yeast",
                    "mold", "mould", "mushroom", "oomycete", "ergosterol", "mycophag"],
    "bacterivore": ["bacteri", "prokaryote", "archaea"],
    "microbivore": ["microbial feeder", "microbivor", "microorganism", "microbe",
                    "microbial communit"],
    "algivore":    ["alga", "algae", "diatom", "cyanobacteri", "microalga", "biofilm"],
    "herbivore":   ["plant root", "root hair", "pollen", "seed", "moss", "lichen",
                    "liverwort", "bryophyte", "plant tissue", "vascular plant", "lettuce",
                    "plant material", "leaf tissue"],
    "predator":    ["prey on", "preys on", "preying on", "predat", "hunt", "nematode",
                    "rotifer", "protozoa", "tardigrade", "enchytraeid"],
    "detritivore": ["detritus", "decompos", "organic matter", "humus", "carrion",
                    "dead plant", "dead wood", "decaying"],
    "omnivore":    ["omnivor", "generalist", "opportunistic", "mixed diet",
                    "multiple food source", "various food"],
}
_GUILD_PAT = {g: [re.compile(k, re.I) for k in ks] for g, ks in GUILD_KEYWORDS.items()}

# Verbs that make a sentence an actual statement about diet.
_DIET_VERB = _any([
    r"\bfeed(?:s|ing)? (?:on|upon)\b", r"\bfeeds\b", r"\bdiet\b", r"\bconsum(?:e|es|ed|ption)\b",
    r"\bingest\w*\b", r"\bgraz(?:e|es|ing)\b", r"\bgut content\w*\b", r"\bstable isotope\w*\b",
    r"\bfeeder\b", r"\btrophic (?:niche|level|position)\b", r"\bfood (?:source|resource)\w*\b",
    r"\bnutrition\w*\b", r"\bfed\b", r"\bpredat\w*\b", r"\bprey\w*\b", r"\bmycophag\w*\b",
])


def _guilds_in(text: str) -> list[str]:
    scores = {g: sum(1 for p in pats if p.search(text)) for g, pats in _GUILD_PAT.items()}
    return sorted([g for g, s in scores.items() if s > 0], key=lambda g: -scores[g])


def extract_trophic(answer: str, target: str) -> dict:
    """Return primary guilds, indirect guilds, evidence type and a note."""
    primary: list[str] = []
    indirect: list[str] = []
    evidence: set[str] = set()
    notes: list[str] = []
    denied = answer_denies(answer)
    if denied:
        notes.append("the sources contain no explicit statement about this species' diet")

    for s in sentences(answer):
        c = classify(s, target)
        guilds = _guilds_in(s)
        if not guilds:
            continue

        # The species is the one being eaten.
        if c["prey_of"]:
            if "predator" in guilds:
                guilds = [g for g in guilds if g != "predator"]
                notes.append("predation relationship runs the other way; species is the prey")
            if not guilds:
                continue

        # A claim about a congener. Other taxa in the sentence are food items, not rival
        # subjects, so only a same-genus name displaces the target.
        if c["congeneric"] and not c["on_target"]:
            indirect += guilds
            notes.append(f"diet statement concerns {c['congeneric'][0]}, not the target species")
            continue

        # A claim about Collembola at large.
        if c["generic"]:
            indirect += guilds
            notes.append("statement refers to Collembola in general, not to this species")
            continue

        # Absent or hedged: the model is reconstructing, not reporting.
        if c["absence"] or c["hedged"]:
            indirect += guilds
            notes.append("no explicit diet statement in the sources; value inferred")
            continue

        # Occurrence in a substrate is not evidence of eating it.
        if c["co_occurrence"] and not _DIET_VERB.search(s):
            indirect += guilds
            notes.append("based on the substrate the species was found in, not on observed feeding")
            continue

        # Bait and traps show attraction, not consumption.
        if TRAPPING.search(s) and not _DIET_VERB.search(s):
            indirect += guilds
            notes.append("attraction to bait or traps is not evidence of consumption")
            continue

        # Needs to be about feeding; a feeding trial qualifies even without a diet verb.
        if not _DIET_VERB.search(s) and not c["experimental"]:
            indirect += guilds
            continue

        if c["experimental"]:
            evidence.add("experimental")
            notes.append("evidence from laboratory feeding experiments; "
                         "may not reflect the diet in the field")
            primary += guilds
            continue

        if denied:
            indirect += guilds
            continue

        evidence.add("direct")
        primary += guilds

    primary = list(dict.fromkeys(primary))
    indirect = [g for g in dict.fromkeys(indirect) if g not in primary]

    ev = "direct" if "direct" in evidence else ("experimental" if evidence else "")
    return {
        "guilds": primary,
        "guilds_indirect": indirect,
        "evidence_type": ev,
        "note": "; ".join(dict.fromkeys(notes)),
    }


# ---------------------------------------------------------------------------
# Body size
# ---------------------------------------------------------------------------

_SIZE_RE = re.compile(
    r'(\d+(?:[.,]\d+)?)\s*(?:(?:[-–—]|to)\s*(\d+(?:[.,]\d+)?)\s*)?'
    r'(mm|millimet(?:er|re)s?|µm|μm|um|microns?|micromet(?:er|re)s?)\b',
    re.I,
)

# A measurement of something that is not the whole body.
_BODY_PART = _any([
    r"\bhead\b", r"\bantenn\w*\b", r"\bfurca\w*\b", r"\bunguis\b", r"\bclaw\w*\b", r"\bmucro\w*\b",
    r"\bdens\b", r"\bmanubri\w*\b", r"\bwidth\b", r"\bocell\w*\b", r"\bseta\w*\b", r"\bsetae\b",
    r"\btibiotars\w*\b", r"\beye\w*\b", r"\bdiameter\b", r"\bthorax\b", r"\babdomen\b",
    r"\bsegment\w*\b", r"\bspine\w*\b", r"\bsensill\w*\b", r"\bapical\b", r"\belevation\w*\b",
    r"\baltitude\w*\b", r"\bdepth\b",
])
_BODY_LENGTH = _any([r"\bbody length\b", r"\blength of the body\b", r"\btotal length\b",
                     r"\bbody size\b", r"\bbody measur\w*\b"])


def _to_mm(value: float, unit: str) -> float:
    unit = unit.lower()
    if unit.startswith(("µ", "μ", "u", "micron", "micromet")):
        return value / 1000.0
    return value


def extract_body_size(answer: str, target: str) -> dict:
    """Only accept measurements asserted of the target species' body length."""
    primary: list[float] = []
    indirect: list[float] = []
    notes: list[str] = []
    denied = answer_denies(answer)

    for s in sentences(answer):
        c = classify(s, target)
        for m in _SIZE_RE.finditer(s):
            vals = [_to_mm(float(m.group(1).replace(",", ".")), m.group(3))]
            if m.group(2):
                vals.append(_to_mm(float(m.group(2).replace(",", ".")), m.group(3)))
            vals = [v for v in vals if 0.1 <= v <= 15.0]
            if not vals:
                continue

            # What does the text immediately before the number describe?
            context = s[max(0, m.start() - 80):m.start()]
            if _BODY_PART.search(context) and not _BODY_LENGTH.search(context):
                notes.append(f"nearest measurement in the source is a body part, not body length "
                             f"({m.group(0).strip()})")
                continue

            # Whose measurement is it? Use the nearest taxon named before the number.
            preceding = [t for t in taxa_in(s[:m.start()])]
            owner = preceding[-1] if preceding else None
            if owner and not _matches_target(owner, target):
                indirect += vals
                notes.append(f"body size of the target species not available; "
                             f"the value reported in the source is for {owner}")
                continue

            if c["absence"] or c["hedged"]:
                indirect += vals
                if c["congeneric"]:
                    notes.append(f"body size of the target species not available; "
                                 f"the value reported in the source is for {c['congeneric'][0]}")
                else:
                    notes.append("no explicit body length for this species; value inferred")
                continue

            if not c["on_target"] and c["other_taxa"]:
                indirect += vals
                notes.append(f"measurement concerns {c['other_taxa'][0]}")
                continue

            if denied:
                indirect += vals
                notes.append("body length of this species is not stated in the sources")
                continue

            primary += vals

    def rng(vals: list[float]) -> str:
        if not vals:
            return ""
        lo, hi = min(vals), max(vals)
        return f"{lo:g}" if lo == hi else f"{lo:g}-{hi:g}"

    return {
        "range_mm": rng(primary),
        "range_indirect_mm": rng(indirect) if not primary else "",
        "evidence_type": "direct" if primary else "",
        "note": "; ".join(dict.fromkeys(notes)) if not primary else "",
    }


# ---------------------------------------------------------------------------
# Habitat
# ---------------------------------------------------------------------------

HABITAT_KEYWORDS = {
    "soil":            ["soil", "edaphic", "subterranean", "underground", "belowground"],
    "leaf_litter":     ["leaf litter", "litter", "humus", "decaying leaves", "leaf-litter"],
    "moss_lichen":     ["moss", "bryophyte", "lichen", "liverwort"],
    "cave":            ["cave", "cavern", "troglo", "hypogean"],
    "forest_wood":     ["forest", "woodland", "tree trunk", "bark", "canopy", "deadwood",
                        "dead wood", "rotten wood", "rotted wood", "decaying wood", "coniferous"],
    "grassland":       ["grassland", "meadow", "pasture", "steppe"],
    "freshwater":      ["freshwater", "stream", "pond", "lake", "riparian", "wetland", "bog", "fen",
                        "peatbog", "peat bog", "marsh"],
    "marine_coastal":  ["intertidal", "tidal", "seashore", "littoral", "seaweed", "supralittoral",
                        "rockpool", "rock pool", "salt marsh", "saltmarsh", "estuar", "mudflat",
                        "mud flat", "marine", "coastal"],
    "alpine_glacier":  ["glacier", "glacial", "nival", "supraglacial", "cryoconite", "firn",
                        "ice-dwelling", "snow"],
    "agricultural":    ["agricultural", "crop", "cultivated", "greenhouse", "arable", "orchard",
                        "vineyard", "farmland"],
    "synanthropic":    ["compost", "garden", "urban", "domestic", "manure", "dung"],
    "sandy_dune":      ["dune", "sandy soil", "sand"],
    "floodplain":      ["flood plain", "floodplain", "inundation", "periodic flooding",
                        "periodically flooded"],
}
_HAB_PAT = {h: [re.compile(re.escape(k), re.I) for k in ks] for h, ks in HABITAT_KEYWORDS.items()}

# Categories that must rest on a specific ecological descriptor. "Coastal" and "marine" on
# their own usually restate where a specimen was collected; "intertidal" or "seaweed"
# describe an environment. Same for a bare "marsh", which may be a salt marsh.
_WEAK_ONLY = {
    "marine_coastal": ["intertidal", "tidal", "seashore", "littoral", "seaweed",
                       "supralittoral", "rockpool", "rock pool", "salt marsh", "saltmarsh",
                       "estuar", "mudflat", "mud flat"],
    "freshwater":     ["freshwater", "stream", "pond", "lake", "riparian", "wetland",
                       "bog", "fen", "peatbog", "peat bog"],
}
_STRONG_PAT = {h: [re.compile(re.escape(k), re.I) for k in ks] for h, ks in _WEAK_ONLY.items()}


def _strong_cue(text: str, habitat: str) -> bool:
    return any(p.search(text) for p in _STRONG_PAT.get(habitat, []))

# Spans that name a place rather than describe an environment.
_GEO_SPANS = [
    re.compile(r'"[^"]{0,120}"'),
    re.compile(r'“[^”]{0,120}”'),
    re.compile(r'\b(?:at |between |ranging from |from )?(?:elevations?|altitudes?)\b[^.,;]{0,60}', re.I),
    re.compile(r'\b\d+(?:[.,]\d+)?\s*(?:[-–]|to)\s*\d+(?:[.,]\d+)?\s*(?:m|meters?|metres?)\b', re.I),
    re.compile(r'\b(?:region|regions|Massif|Mountains?|Mts\.?|Reservoir|Island|Islands|'
               r'Peninsula|Valley|National Park|Province|County|District)\b', re.I),
    re.compile(r'\bmountainous (?:areas?|regions?)\b', re.I),
]
_PLACE_WORD = re.compile(r'\b[A-Z][\wÀ-ſ\'’-]{2,}\b')


def strip_geography(sentence: str, target: str) -> str:
    """Remove place names, coordinates and altitudes so they cannot become habitats."""
    s = sentence
    for pat in _GEO_SPANS:
        s = pat.sub(" ", s)
    # Drop capitalised tokens that are neither taxon names nor ordinary sentence openers.
    target_words = set(target.split())
    keep = _NOT_A_PLACE | target_words
    parts, first = [], True
    for tok in s.split():
        bare = tok.strip('*.,;:()"“”')
        if not first and _PLACE_WORD.fullmatch(bare) and bare not in keep:
            first = False
            continue
        first = False
        parts.append(tok)
    return " ".join(parts)


def _habitats_in(text: str) -> list[str]:
    scores = {h: sum(1 for p in pats if p.search(text)) for h, pats in _HAB_PAT.items()}
    found = sorted([h for h, s in scores.items() if s > 0], key=lambda h: -scores[h])
    # A terrestrial species in a floodplain is not a freshwater species.
    if "floodplain" in found and "freshwater" in found:
        found = [h for h in found if h != "freshwater"]
    return found


def extract_habitat(answer: str, target: str) -> dict:
    """Habitat must rest on an ecological description, not on a collection locality."""
    primary: list[str] = []
    indirect: list[str] = []
    notes: list[str] = []
    denied = answer_denies(answer)
    if denied:
        notes.append("the sources give no explicit habitat description for this species")

    for s in sentences(answer):
        c = classify(s, target)
        cleaned = strip_geography(s, target)
        here = _habitats_in(cleaned)
        dropped = [h for h in _habitats_in(s) if h not in here]

        if dropped:
            indirect += dropped
            notes.append("categories inferred from locality, coordinates or altitude were "
                         "not retained: " + ", ".join(dropped))
        if not here:
            continue

        if c["other_taxa"] and not c["on_target"]:
            indirect += here
            notes.append(f"habitat statement concerns {c['other_taxa'][0]}, not the target species")
            continue
        if c["absence"] or c["hedged"]:
            indirect += here
            notes.append("no explicit habitat description in the sources; value inferred")
            continue
        if c["experimental"]:
            indirect += here
            notes.append("habitat reflects an experimental substrate, not the natural habitat")
            continue
        if denied:
            indirect += here
            continue

        # Categories resting only on a vague term ("coastal", "marine") rather than on a
        # real ecological descriptor are exactly the marine_coastal false positives the
        # reviewers flagged for Parisotoma agrelli, Bilobella aurantiaca and Lathriopyga
        # longiseta. Keep them, but not in the primary column.
        weak = [h for h in here if h in _WEAK_ONLY and not _strong_cue(cleaned, h)]
        if weak:
            indirect += weak
            notes.append("categories resting only on a general term rather than an "
                         "ecological description: " + ", ".join(weak))
            here = [h for h in here if h not in weak]
        primary += here

    primary = list(dict.fromkeys(primary))
    indirect = [h for h in dict.fromkeys(indirect) if h not in primary]
    return {
        "habitats": primary,
        "habitats_indirect": indirect,
        "evidence_type": "direct" if primary else "",
        "note": "; ".join(dict.fromkeys(notes)),
    }
