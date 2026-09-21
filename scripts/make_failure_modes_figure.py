"""Slide graphic: the two failure modes, side by side."""
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import textwrap

SURFACE="#fcfcfb"; INK="#0b0b0b"; SEC="#52514e"; ACCENT="#0d366b"; TINT="#cde2fb"; RULE="#c3c2b7"
plt.rcParams.update({"font.family":"DejaVu Sans"})

def it(s):                      # italic species name via mathtext
    return r"$\it{" + s.replace(" ", r"\ ") + "}$"

fig = plt.figure(figsize=(12, 6.4), dpi=200, facecolor=SURFACE)
ax = fig.add_axes([0,0,1,1]); ax.set_xlim(0,1); ax.set_ylim(0,1); ax.axis("off")

ax.text(0.04, 0.93, "Two ways a literature-mined trait goes wrong",
        fontsize=23, weight="bold", color=INK, va="top")

COLS = [
    dict(x=0.045, w=0.425, num="1",
         head="Retrieval matched the epithet alone",
         sub="The wrong organism",
         bullets=[f"{it('Anurida polaris')}  \u2192  {it('Arcynopteryx polaris')}, a stonefly",
                  f"{it('Ceratophysella gibbosa')}  \u2192  {it('Chilina gibbosa')}, a snail",
                  f"{it('Entomobrya intermedia')}  \u2192  {it('Ephedra intermedia')}, a plant"],
         fix="Require genus + epithet as an adjacent phrase"),
    dict(x=0.53, w=0.425, num="2",
         head="The document was right, the sentence was not",
         sub="The wrong claim",
         bullets=[f"Source: \"1330 µm ... However, this measurement\nrefers to {it('Stenaphorura lubbocki')}\"",
                  f"Recorded for {it('Stenaphorura quadrispina')}\nanyway",
                  "Same class: found in leaf litter, recorded\nas a detritivore"],
         fix="Bind every value to the sentence that asserts it"),
]

for c in COLS:
    x, w = c["x"], c["w"]
    ax.plot([x, x+w], [0.845, 0.845], color=RULE, lw=1.2)
    ax.text(x, 0.815, c["num"], fontsize=30, weight="bold", color=TINT, va="top")
    ax.text(x+0.045, 0.823, c["sub"].upper(), fontsize=10.5, color=SEC, va="top")
    ax.text(x+0.045, 0.787, "\n".join(textwrap.wrap(c["head"], 34)),
            fontsize=15.5, weight="bold", color=ACCENT, va="top", linespacing=1.35)
    y = 0.66
    for b in c["bullets"]:
        ax.text(x+0.012, y, "•", fontsize=13, color=ACCENT, va="top")
        lines = b.split("\n")
        # Never wrap a line holding mathtext: textwrap would split the $...$ pair.
        wrapped = b if ("$" in b or len(lines) > 1) else "\n".join(textwrap.wrap(b, 52))
        ax.text(x+0.042, y, wrapped, fontsize=11.5, color=INK, va="top", linespacing=1.5)
        y -= 0.078 + 0.056*(wrapped.count("\n"))
    # fix strip
    fy = 0.205
    ax.add_patch(FancyBboxPatch((x, fy), w, 0.085, boxstyle="round,pad=0.006,rounding_size=0.012",
                                linewidth=0, facecolor=TINT, mutation_aspect=0.5))
    ax.text(x+0.022, fy+0.043, "FIX", fontsize=9.5, weight="bold", color=ACCENT, va="center")
    ax.text(x+0.072, fy+0.043, c["fix"], fontsize=12.5, color=INK, va="center")

ax.plot([0.045, 0.955], [0.135, 0.135], color=RULE, lw=1.2)
ax.text(0.045, 0.085,
        "Getting the right document is necessary but not sufficient.",
        fontsize=15, weight="bold", color=INK, va="center")
ax.text(0.045, 0.036,
        "Provenance has to reach the claim, not just the paper.",
        fontsize=15, color=SEC, va="center")

out="/home/egaillac/collembola-trait-mining/results/figures/fig_failure_modes.png"
fig.savefig(out, facecolor=SURFACE, bbox_inches="tight")
print("wrote", out)
