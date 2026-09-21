"""Grouped table: both failure modes, with the cases the reviewers reported."""
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import textwrap

SURFACE="#fcfcfb"; INK="#0b0b0b"; SEC="#52514e"; HEAD="#0d366b"
CAT1="#0d366b"; CAT2="#2a78d6"; RULE="#c3c2b7"; HAIR="#e1e0d9"; BAND="#f2f1ec"
plt.rcParams.update({"font.family":"DejaVu Sans"})

def it(s): return r"$\it{" + s.replace(" ", r"\ ") + "}$"

GROUPS = [
    dict(label="WRONG ORGANISM", color=CAT1,
         cause="Retrieval matched the specific epithet alone",
         fix="Fix: require genus + epithet as an adjacent phrase",
         rows=[("Anurida polaris",          f"{it('Arcynopteryx polaris')}, a stonefly",        "body length"),
               ("Ceratophysella gibbosa",   f"{it('Chilina gibbosa')}, a freshwater snail",     "habitat"),
               ("Ceratophysella longispina",f"{it('Daphnia longispina')}, a water flea",        "habitat"),
               ("Entomobrya intermedia",    f"{it('Ephedra intermedia')}, a plant",             "trophic guild")]),
    dict(label="WRONG CLAIM", color=CAT2,
         cause="The document was right, the sentence was not",
         fix="Fix: bind every value to the sentence that asserts it",
         rows=[("Stenaphorura quadrispina", f"{it('Stenaphorura lubbocki')}, a congener",        "body length"),
               ("Friesea truncata",         f"{it('Friesea major')}, a congener",                "body length"),
               ("Folsomia candida",         "a spider that preys on it",                        "trophic guild"),
               ("Anurida granulata",        "an alpine collection locality",                    "habitat")]),
]
X = [0.025, 0.245, 0.500, 0.845]
HEADERS = ["", "COLLEMBOLA SPECIES", "WHAT THE SOURCE ACTUALLY DESCRIBED", "TRAIT AFFECTED"]

fig = plt.figure(figsize=(12.6, 4.4), dpi=200, facecolor=SURFACE)
ax = fig.add_axes([0,0,1,1]); ax.set_xlim(0,1); ax.set_ylim(0,1); ax.axis("off")

for x, h in zip(X, HEADERS):
    if h: ax.text(x, 0.945, h, fontsize=10.5, weight="bold", color=HEAD, va="center")
ax.plot([0.02, 0.978], [0.905]*2, color=RULE, lw=1.4)

dy, y = 0.095, 0.800
i = 0
for g in GROUPS:
    top = y + dy/2
    for target, described, trait in g["rows"]:
        if i % 2 == 1:
            ax.add_patch(plt.Rectangle((0.215, y-dy/2+0.005), 0.763, dy-0.010,
                                       facecolor=BAND, edgecolor="none"))
        ax.text(X[1], y, it(target),  fontsize=12, color=INK, va="center")
        ax.text(X[2], y, described,   fontsize=12, color=INK, va="center")
        ax.text(X[3], y, trait,       fontsize=12, color=SEC, va="center")
        y -= dy; i += 1
    bottom = y + dy/2
    # category rail + label, spanning the group
    ax.add_patch(plt.Rectangle((0.022, bottom+0.012), 0.005, top-bottom-0.024,
                               facecolor=g["color"], edgecolor="none"))
    mid = (top + bottom) / 2
    ax.text(0.042, mid+0.105, g["label"], fontsize=11.5, weight="bold",
            color=g["color"], va="center")
    ax.text(0.042, mid+0.032, "\n".join(textwrap.wrap(g["cause"], 26)),
            fontsize=10, color=SEC, va="center", linespacing=1.4)
    ax.text(0.042, mid-0.098, "\n".join(textwrap.wrap(g["fix"], 26)),
            fontsize=10, color=g["color"], va="center", linespacing=1.4, style="italic")
    y -= 0.035   # gap between groups

out="/home/egaillac/collembola-trait-mining/results/figures/fig_epithet_table.png"
fig.savefig(out, facecolor=SURFACE, bbox_inches="tight")
print("wrote", out)
