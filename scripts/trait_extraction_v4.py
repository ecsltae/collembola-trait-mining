"""
Claim-level trait extraction, v4.

v4 changes over v3, all from the curators' v3 review (September 2026):
  - Habitat is two axes: EUNIS level-1 macrohabitat, and microhabitat/substrate.
    v3's single "forest_wood" label merged a habitat (forest) with a substrate (wood),
    so a species recorded in a forest was labelled as wood-associated.
  - Habitat terms negated in the text ("very rare in steppes") are not assigned.
  - Riparian and river-bank terms no longer imply inland water.
  - Dispersion values (standard deviation, ±) are not parsed as measurements.
  - Body-size notes name the congener a demoted value belongs to.

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
    r"no (?:explicit |specific |direct |detailed )?(?:mention|information|data|evidence|details?|reference|measurements?)",
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


# Text announcing a spread around a measurement rather than a measurement.
# "1.5 mm with a standard deviation of 0.1 mm" was reported as a 0.1-1.5 mm range.
_DISPERSION = _any([
    r"\bstandard deviation\b", r"\bstandard error\b", r"\bstd\.? dev", r"±", r"\+/-",
    r"\bvariance\b", r"\bs\.d\.", r"\(\s*SD\b", r"\bSD\s*[=:]",
])


def congeners_in(answer: str, target: str) -> list[str]:
    """Same-genus taxa other than the target, named anywhere in the answer.

    Answers typically give a value in one sentence and only say whose it is in the next
    ("reported as 1330 micrometers. However, this measurement refers to S. lubbocki").
    A sentence-scoped lookup misses the second sentence.
    """
    t_genus = target.split()[0]
    found = []
    for sent in sentences(answer):
        for m in taxa_in(sent):
            genus = m.split()[0].rstrip(".")
            if genus in (t_genus, t_genus[0]) and not _matches_target(m, target):
                found.append(m)
    return list(dict.fromkeys(found))


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
            if _DISPERSION.search(s[max(0, m.start() - 40):m.start()]):
                continue    # a spread, not a size
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
                cong = congeners_in(answer, target)
                if cong:
                    notes.append("body size of the target species not available; the value "
                                 "reported in the source is for " + ", ".join(cong[:2]))
                else:
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

# Two axes, because they answer different questions.
#
# MACROHABITAT is the landscape the species occurs in, classified on EUNIS level 1 (2012
# letter codes), the vocabulary the curators asked for. MICROHABITAT is the substrate it
# lives in or on. A springtail in leaf litter in a beech forest is G (forest) at the macro
# level and leaf_litter at the micro level. v3 had one axis, so "forest" and "dead wood"
# collapsed into a single forest_wood label and every forest record read as
# wood-associated.

EUNIS_MACRO = {
    "G_woodland_forest": ["forest", "woodland", "wooded", "coniferous", "deciduous"],
    "E_grassland":       ["grassland", "meadow", "pasture", "steppe", "prairie", "lawn"],
    "F_heath_scrub":     ["heath", "heathland", "scrub", "shrubland", "maquis", "garrigue",
                          "tundra"],
    "D_mire_bog_fen":    ["bog", "fen", "mire", "peatbog", "peat bog", "peatland", "marsh"],
    "C_inland_water":    ["freshwater", "stream", "river", "pond", "lake", "water pool",
                          "pools of water", "water bod"],
    "B_coastal":         ["intertidal", "seashore", "supralittoral", "littoral", "salt marsh",
                          "saltmarsh", "beach", "shore", "shoreline", "dune", "estuar",
                          "mudflat", "mud flat", "rockpool", "rock pool", "seaweed", "coastal"],
    "A_marine":          ["marine"],
    "H_cave_ice_scree":  ["cave", "cavern", "troglo", "hypogean", "glacier", "glacial", "nival",
                          "supraglacial", "cryoconite", "firn", "snow", "scree", "ice-dwelling"],
    "I_agricultural":    ["agricultural", "crop", "cropland", "cultivated", "arable", "orchard",
                          "vineyard", "farmland", "garden"],
    "J_artificial":      ["urban", "greenhouse", "domestic", "building"],
}
EUNIS_LABEL = {
    "A_marine": "A Marine", "B_coastal": "B Coastal", "C_inland_water": "C Inland surface waters",
    "D_mire_bog_fen": "D Mires, bogs and fens", "E_grassland": "E Grasslands",
    "F_heath_scrub": "F Heathland, scrub and tundra", "G_woodland_forest": "G Woodland and forest",
    "H_cave_ice_scree": "H Inland unvegetated (caves, ice, scree)",
    "I_agricultural": "I Cultivated and agricultural", "J_artificial": "J Constructed and artificial",
}

MICROHABITAT = {
    "soil":          ["soil", "edaphic", "subterranean", "underground", "belowground"],
    "leaf_litter":   ["leaf litter", "litter", "humus", "decaying leaves", "leaf-litter"],
    "moss_lichen":   ["moss", "bryophyte", "lichen", "liverwort"],
    "deadwood":      ["dead wood", "deadwood", "rotten wood", "rotted wood", "rotting wood",
                      "decaying wood", "decomposing wood", "log", "stump", "fallen trunk",
                      "wood debris"],
    "bark":          ["bark", "tree trunk"],
    "water_surface": ["water surface", "surface of water", "surface of the water", "water film"],
    "under_stones":  ["under stones", "beneath stones", "under rocks"],
    "dung_compost":  ["dung", "manure", "compost"],
}


def _kw(term: str) -> re.Pattern:
    """Start-anchored pattern; short single words also take a plural and an end anchor.

    v3 matched bare substrings, so "fen" hit "fence", "bog" hit "bogus", and a short word
    like "log" would hit "biology". Long stems such as "troglo" stay prefix matches so
    they still reach "troglobiont".
    """
    pat = r"\b" + re.escape(term)
    if term.isalpha() and len(term) <= 5:
        pat += r"(?:e?s)?\b"
    return re.compile(pat, re.I)


_MACRO_PAT = {h: [_kw(k) for k in ks] for h, ks in EUNIS_MACRO.items()}
_MICRO_PAT = {h: [_kw(k) for k in ks] for h, ks in MICROHABITAT.items()}

# Categories that must rest on a specific descriptor, not a general word. "Coastal" or
# "marine" alone usually restates a collection locality (Parisotoma agrelli, Roscoff).
_STRONG_ONLY = {
    "B_coastal": ["intertidal", "seashore", "supralittoral", "littoral", "salt marsh",
                  "saltmarsh", "beach", "shore", "dune", "estuar", "mudflat", "mud flat",
                  "rockpool", "rock pool", "seaweed"],
    "A_marine":  ["intertidal", "littoral", "seaweed", "rockpool", "rock pool"],
}
_STRONG_PAT = {h: [_kw(k) for k in ks] for h, ks in _STRONG_ONLY.items()}


def _strong_cue(text: str, habitat: str) -> bool:
    return any(p.search(text) for p in _STRONG_PAT.get(habitat, []))


# A habitat named only to say the species is rare or absent there is not its habitat.
# "Very rare in steppes" was being assigned grassland.
_NEGATED_SPANS = [
    re.compile(r"\b(?:very |extremely |only )?rare(?:ly)?(?: found| recorded| observed)?"
               r" (?:in|on|at)\b[^,.;]{0,60}", re.I),
    re.compile(r"\b(?:absent|missing) (?:from|in)\b[^,.;]{0,60}", re.I),
    re.compile(r"\bnot (?:found|recorded|present|observed|known) (?:in|on|from)\b[^,.;]{0,60}",
               re.I),
    re.compile(r"\bavoids?\b[^,.;]{0,60}", re.I),
]

# Terrestrial margins of water bodies. A riparian or floodplain species lives on land that
# is next to or periodically covered by water; that is not inland surface water.
_WATER_MARGIN = re.compile(
    r"\b(?:riparian|river ?banks?|stream ?banks?|banks? of (?:the )?(?:river|stream)"
    r"|flood ?plains?|inundat\w*|periodic(?:al)?(?:ly)? flood\w*)", re.I)

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


def strip_negations(sentence: str) -> str:
    for pat in _NEGATED_SPANS:
        sentence = pat.sub(" ", sentence)
    return sentence


def _hits(text: str, patterns: dict) -> list[str]:
    scores = {h: sum(1 for p in pats if p.search(text)) for h, pats in patterns.items()}
    return sorted([h for h, n in scores.items() if n > 0], key=lambda h: -scores[h])


def _macro_in(text: str) -> list[str]:
    found = _hits(text, _MACRO_PAT)
    # "Salt marsh" is coastal, not a freshwater mire.
    if "B_coastal" in found and re.search(r"\bsalt ?marsh", text, re.I):
        found = [h for h in found if h != "D_mire_bog_fen"]
    # A water margin is land. "River bank" also contains "river".
    if _WATER_MARGIN.search(text):
        found = [h for h in found if h != "C_inland_water"]
    return found


def _micro_in(text: str) -> list[str]:
    return _hits(text, _MICRO_PAT)


def extract_habitat(answer: str, target: str) -> dict:
    """Macrohabitat (EUNIS level 1) and microhabitat, from ecological statements only."""
    macro: list[str] = []
    micro: list[str] = []
    macro_ind: list[str] = []
    micro_ind: list[str] = []
    notes: list[str] = []
    denied = answer_denies(answer)
    if denied:
        notes.append("the sources give no explicit habitat description for this species")

    for s in sentences(answer):
        c = classify(s, target)
        cleaned = strip_negations(strip_geography(s, target))
        here_ma, here_mi = _macro_in(cleaned), _micro_in(cleaned)

        dropped = [h for h in _macro_in(s) if h not in here_ma]
        if dropped:
            macro_ind += dropped
            notes.append("categories resting on a locality, an altitude, or a statement of "
                         "rarity were not retained: " + ", ".join(dropped))
        if _WATER_MARGIN.search(s) and _hits(s, {"w": _MACRO_PAT["C_inland_water"]}):
            notes.append("riparian or floodplain habitat: terrestrial, not inland water")

        if not (here_ma or here_mi):
            continue

        reason = None
        if c["other_taxa"] and not c["on_target"]:
            reason = f"habitat statement concerns {c['other_taxa'][0]}, not the target species"
        elif c["absence"] or c["hedged"]:
            reason = "no explicit habitat description in the sources; value inferred"
        elif c["experimental"]:
            reason = "habitat reflects an experimental substrate, not the natural habitat"
        elif denied:
            reason = ""
        if reason is not None:
            macro_ind += here_ma
            micro_ind += here_mi
            if reason:
                notes.append(reason)
            continue

        weak = [h for h in here_ma if h in _STRONG_ONLY and not _strong_cue(cleaned, h)]
        if weak:
            macro_ind += weak
            notes.append("resting only on a general term rather than an ecological "
                         "description: " + ", ".join(weak))
            here_ma = [h for h in here_ma if h not in weak]
        macro += here_ma
        micro += here_mi

    def _dedup(keep, demoted):
        keep = list(dict.fromkeys(keep))
        return keep, [h for h in dict.fromkeys(demoted) if h not in keep]

    macro, macro_ind = _dedup(macro, macro_ind)
    micro, micro_ind = _dedup(micro, micro_ind)
    return {
        "eunis": macro,
        "eunis_indirect": macro_ind,
        "microhabitat": micro,
        "microhabitat_indirect": micro_ind,
        "evidence_type": "direct" if (macro or micro) else "",
        "note": "; ".join(dict.fromkeys(notes)),
    }
