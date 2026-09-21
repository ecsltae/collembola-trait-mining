"""Two slide figures for the TDWG talk. Palette: validated blue ordinal ramp + muted neutral."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

SURFACE="#fcfcfb"; INK="#0b0b0b"; SEC="#52514e"; MUTED="#898781"; GRID="#e1e0d9"
EXPLICIT="#0d366b"; INDIRECT="#2a78d6"; LIGHT="#86b6ef"; NEUTRAL="#898781"
plt.rcParams.update({"font.family":"DejaVu Sans","figure.facecolor":SURFACE,"axes.facecolor":SURFACE})

def style(ax):
    for s in ("top","right","left"): ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color("#c3c2b7")
    ax.tick_params(colors=MUTED, labelsize=11, length=0)
    ax.xaxis.grid(True, color=GRID, lw=0.8); ax.set_axisbelow(True)

GAP = 1.2   # ~2px surface gap between stacked segments

# ---------------------------------------------------------------- Figure 2
traits = ["Trophic guild", "Body size", "Habitat"]
v2      = [40, 27, 221]
explicit= [15, 15, 149]
indirect= [23, 11, 92]

fig, ax = plt.subplots(figsize=(10, 4.6), dpi=200)
y = range(len(traits)); h = 0.34
for i in y:
    ax.barh(i + h/2 + 0.03, v2[i], height=h, color=NEUTRAL)
    ax.text(v2[i] + 4, i + h/2 + 0.03, str(v2[i]), va="center", fontsize=11, color=SEC)
    ax.barh(i - h/2 - 0.03, explicit[i], height=h, color=EXPLICIT)
    ax.barh(i - h/2 - 0.03, indirect[i], height=h, left=explicit[i] + GAP, color=LIGHT)
    ax.text(explicit[i]/2, i - h/2 - 0.03, str(explicit[i]), va="center", ha="center",
            fontsize=11, color="white", weight="bold")
    xi = explicit[i] + GAP + indirect[i]
    if indirect[i] >= 40:
        ax.text(explicit[i] + GAP + indirect[i]/2, i - h/2 - 0.03, f"+{indirect[i]}",
                va="center", ha="center", fontsize=11, color=INK, weight="bold")
    else:
        ax.text(xi + 4, i - h/2 - 0.03, f"+{indirect[i]}", va="center",
                fontsize=10.5, color=SEC)
ax.set_yticks(list(y)); ax.set_yticklabels(traits, fontsize=12, color=INK)
ax.invert_yaxis()
ax.set_xlim(0, 258); ax.set_xlabel("species with a value  (of 330)", fontsize=11, color=SEC)
style(ax)
ax.set_title("Expert review removed most values; none were thrown away",
             fontsize=15, color=INK, weight="bold", loc="left", pad=36)
ax.text(0, 1.04, "Before and after claim-level extraction",
        transform=ax.transAxes, fontsize=11.5, color=SEC)
ax.legend(handles=[Patch(color=NEUTRAL, label="Before review"),
                   Patch(color=EXPLICIT, label="Explicit, species-specific evidence"),
                   Patch(color=LIGHT,   label="Indirect, reason recorded")],
          loc="upper center", bbox_to_anchor=(0.5, -0.20), ncol=3,
          frameon=False, fontsize=10.5, labelcolor=SEC)
fig.tight_layout()
fig.savefig("/home/egaillac/collembola-trait-mining/results/figures/fig_before_after.png",
            facecolor=SURFACE, bbox_inches="tight")
print("wrote fig_before_after.png")

# ---------------------------------------------------------------- Figure 3
seg_labels = ["Explicit statement", "Indirect evidence",
              "Species named, trait not described", "No literature found"]
colors     = [EXPLICIT, INDIRECT, LIGHT, NEUTRAL]
data = {"Trophic guild": [15, 20, 255, 40],
        "Body size":     [15, 11, 264, 40],
        "Habitat":       [149, 63, 78, 40]}

fig, ax = plt.subplots(figsize=(10, 4.3), dpi=200)
names = list(data)
for i, t in enumerate(names):
    left = 0
    for v, c in zip(data[t], colors):
        ax.barh(i, v, left=left, height=0.5, color=c)
        if v >= 38:
            ax.text(left + v/2, i, str(v), va="center", ha="center", fontsize=11,
                    color="white" if c in (EXPLICIT, INDIRECT, NEUTRAL) else INK,
                    weight="bold")
        left += v + GAP
ax.set_yticks(range(len(names))); ax.set_yticklabels(names, fontsize=12, color=INK)
ax.set_xlim(0, 340); ax.set_xlabel("Collembola species", fontsize=11, color=SEC)
style(ax); ax.invert_yaxis()
ax.set_title("The limit is the literature, not the method",
             fontsize=15, color=INK, weight="bold", loc="left", pad=36)
ax.text(0, 1.04, "Most species are named in the literature without their traits being described",
        transform=ax.transAxes, fontsize=11.5, color=SEC)
ax.legend(handles=[Patch(color=c, label=l) for c, l in zip(colors, seg_labels)],
          loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=2,
          frameon=False, fontsize=10.5, labelcolor=SEC)
fig.tight_layout()
fig.savefig("/home/egaillac/collembola-trait-mining/results/figures/fig_evidence_coverage.png",
            facecolor=SURFACE, bbox_inches="tight")
print("wrote fig_evidence_coverage.png")
