"""Table: epithet-only retrieval pulled unrelated organisms. Cases reported by the reviewers."""
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

SURFACE="#fcfcfb"; INK="#0b0b0b"; SEC="#52514e"; HEAD="#0d366b"
RULE="#c3c2b7"; HAIR="#e1e0d9"; BAND="#f2f1ec"
plt.rcParams.update({"font.family":"DejaVu Sans"})

def it(s): return r"$\it{" + s.replace(" ", r"\ ") + "}$"

ROWS = [
    ("Anurida polaris",          "Arcynopteryx polaris",  "stonefly",         "body length"),
    ("Anurophorus atlanticus",   "Sphecodes atlanticus",  "bee",              "body length"),
    ("Ceratophysella gibbosa",   "Chilina gibbosa",       "freshwater snail", "habitat"),
    ("Ceratophysella longispina","Daphnia longispina",    "water flea",       "habitat"),
    ("Ceratophysella sigillata", "Hilarempis sigillata",  "dance fly",        "trophic guild"),
    ("Deutonura gibbosa",        "Anoplolepis gibbosa",   "ant",              "trophic guild"),
    ("Dicyrtoma aurata",         "Desmoxytes aurata",     "millipede",        "trophic guild"),
    ("Entomobrya intermedia",    "Ephedra intermedia",    "plant",            "trophic guild"),
]
HEADERS = ["COLLEMBOLA SPECIES", "DOCUMENT WAS ABOUT", "WHICH IS A", "TRAIT AFFECTED"]
X = [0.025, 0.315, 0.605, 0.790]

fig = plt.figure(figsize=(12, 4.5), dpi=200, facecolor=SURFACE)
ax = fig.add_axes([0,0,1,1]); ax.set_xlim(0,1); ax.set_ylim(0,1); ax.axis("off")

y_head, dy = 0.915, 0.098
for x, h in zip(X, HEADERS):
    ax.text(x, y_head, h, fontsize=10.5, weight="bold", color=HEAD, va="center")
ax.plot([0.02, 0.975], [y_head-0.045]*2, color=RULE, lw=1.4)

for i, (target, got, group, trait) in enumerate(ROWS):
    y = y_head - 0.105 - i*dy
    if i % 2 == 1:
        ax.add_patch(plt.Rectangle((0.02, y-dy/2+0.006), 0.955, dy-0.012,
                                   facecolor=BAND, edgecolor="none"))
    ax.text(X[0], y, it(target), fontsize=12.5, color=INK, va="center")
    ax.text(X[1], y, it(got),    fontsize=12.5, color=INK, va="center")
    ax.text(X[2], y, group,      fontsize=12.5, color=SEC,  va="center")
    ax.text(X[3], y, trait,      fontsize=12.5, color=SEC,  va="center")
    if i < len(ROWS)-1:
        ax.plot([0.02, 0.975], [y-dy/2]*2, color=HAIR, lw=0.7)

out="/home/egaillac/collembola-trait-mining/results/figures/fig_epithet_table.png"
fig.savefig(out, facecolor=SURFACE, bbox_inches="tight")
print("wrote", out)
