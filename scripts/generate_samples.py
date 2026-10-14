"""Self-authored chart fixtures. Numerical truth is for evaluation, never inference."""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "app" / "static" / "samples"


def make_chart(path, values, labels, limits, title, ylabel="Approval (%)", color="#426983", ticks=None):
    fig, ax = plt.subplots(figsize=(9, 6), dpi=140)
    fig.patch.set_facecolor("#ffffff")
    ax.set_facecolor("#ffffff")
    ax.bar(labels, values, width=.53, color=color, zorder=3)
    ax.set_ylim(*limits)
    if ticks is not None:
        ax.set_yticks(ticks)
    ax.set_title(title, loc="left", fontsize=19, weight="bold", pad=30, color="#233241")
    ax.set_ylabel(ylabel, fontsize=12, labelpad=18, color="#536371")
    ax.tick_params(axis="both", labelsize=12, length=0, pad=12, colors="#536371")
    ax.grid(axis="y", color="#e6e9eb", linewidth=.7, zorder=0)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("bottom", "left"):
        ax.spines[side].set_color("#a4acb3")
    fig.subplots_adjust(left=.16, right=.95, top=.79, bottom=.17)
    fig.savefig(path, facecolor="white")
    plt.close(fig)


def main():
    SAMPLES.mkdir(parents=True, exist_ok=True)
    specs = [
        dict(id="truncated", name="The growth illusion", subtitle="Same numbers. A very different impression.",
             title="Customer approval, by quarter", values=[92, 94, 96, 98], labels=["Q1", "Q2", "Q3", "Q4"],
             limits=[90, 100], ticks=[90, 92, 94, 96, 98, 100], expected="truncated"),
        dict(id="honest", name="A fair comparison", subtitle="A chart that should pass the axis checks.",
             title="Customer approval, by quarter", values=[62, 68, 73, 79], labels=["Q1", "Q2", "Q3", "Q4"],
             limits=[0, 100], ticks=[0, 20, 40, 60, 80, 100], expected="clear"),
        dict(id="inverted", name="An upside-down story", subtitle="The axis reverses the visual ranking.",
             title="Support requests, by month", values=[35, 50, 65, 80], labels=["Jan", "Feb", "Mar", "Apr"],
             limits=[100, 0], ticks=[0, 20, 40, 60, 80, 100], ylabel="Requests", color="#9270ad", expected="inverted"),
        dict(id="unreadable", name="Missing context", subtitle="When the image cannot support a conclusion.",
             title="The numbers behind the claim", values=[92, 94, 96, 98], labels=["A", "B", "C", "D"],
             limits=[90, 100], ticks=[], expected="review"),
        dict(id="grayscale", name="Beyond color", subtitle="A grayscale chart inspected through luminance.",
             title="Orders fulfilled, by region", values=[32, 47, 56, 71], labels=["North", "South", "East", "West"],
             limits=[0, 80], ticks=[0, 20, 40, 60, 80], ylabel="Orders", color="#555555", expected="clear"),
        dict(id="vanishing", name="The vanishing value", subtitle="A category with no measurable bar must not disappear.",
             title="Orders fulfilled, by region", values=[0, 44, 61, 78], labels=["North", "South", "East", "West"],
             limits=[0, 100], ticks=[0, 20, 40, 60, 80, 100], ylabel="Orders", expected="review", expected_issue="incomplete_categories"),
    ]
    for spec in specs:
        opts = {k: spec[k] for k in ("values", "labels", "limits", "title", "ticks")}
        for k in ("ylabel", "color"):
            if k in spec:
                opts[k] = spec[k]
        make_chart(SAMPLES / f"{spec['id']}.png", **opts)
    # Keep numeric truth away from the served app and API.
    public = [{k: s[k] for k in ("id", "name", "subtitle")} for s in specs]
    (SAMPLES / "index.json").write_text(json.dumps(public, indent=2) + "\n")
    truth_dir = ROOT / "tests" / "fixtures"
    truth_dir.mkdir(parents=True, exist_ok=True)
    (truth_dir / "truth.json").write_text(json.dumps(specs, indent=2) + "\n")
    print(f"Generated {len(specs)} self-authored examples in {SAMPLES}")


if __name__ == "__main__":
    main()
