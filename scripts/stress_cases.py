"""Independent Pillow-rendered challenge images, never imported by the app.

These are synthetic regression cases, not an external or held-out benchmark.
"""
from io import BytesIO
import math
from pathlib import Path

import matplotlib
from PIL import Image, ImageDraw, ImageFont


def chart_bytes(values, *, limits=(0, 100), ticks=(0, 20, 40, 60, 80, 100),
                colors=("#3479a1",), label_format=None, positions=None,
                stacked=False, logarithmic=False, width=76):
    image = Image.new("RGB", (960, 640), "white")
    draw = ImageDraw.Draw(image)
    font_path = Path(matplotlib.get_data_path()) / "fonts" / "ttf" / "DejaVuSans.ttf"
    font = ImageFont.truetype(str(font_path), 18)
    title_font = ImageFont.truetype(str(font_path), 23)
    left, right, top, bottom = 150, 880, 100, 520

    def pixel(value):
        low, high = limits
        if logarithmic:
            low, high, value = map(math.log10, (low, high, value))
        return round(bottom - (value-low)/(high-low)*(bottom-top))

    draw.text((left, 38), "Independent chart rendering", fill="#28343b", font=title_font)
    for tick in ticks:
        y = pixel(tick)
        draw.line((left, y, right, y), fill="#e8e8e8", width=1)
        label = label_format(tick) if label_format else f"{tick:g}"
        draw.text((left-15, y), label, fill="#333333", font=font, anchor="rm")
    draw.line((left, top, left, bottom), fill="#aaaaaa", width=1)
    draw.line((left, bottom, right, bottom), fill="#aaaaaa", width=1)
    baseline = max(0, min(limits)) if not logarithmic else min(limits)
    xs = positions if positions is not None else [240 + i * 175 for i in range(len(values))]
    for i, (x, value) in enumerate(zip(xs, values)):
        y0, y1 = sorted((pixel(baseline), pixel(value)))
        draw.rectangle((x-width//2, y0, x+width//2, y1), fill=colors[i % len(colors)])
        if stacked:
            draw.rectangle((x-width//2, y0, x+width//2, (y0+y1)//2), fill="#d77631")
        draw.text((x, bottom+22), ["North", "South", "East", "West"][i], fill="#333333", font=font, anchor="mt")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def cases():
    specs = [
        dict(id="independent-blue", values=[22, 44, 61, 78], expected="clear"),
        dict(id="independent-orange", values=[18, 31, 52, 69], colors=("#b95720",), expected="clear"),
        dict(id="grayscale", values=[12, 26, 38, 44], limits=(0, 50), ticks=(0, 10, 20, 30, 40, 50), colors=("#555555",), expected="clear"),
        dict(id="black-truncated", values=[108, 110, 113, 116], limits=(100, 120), ticks=(100, 105, 110, 115, 120), colors=("#222222",), expected="flagged"),
        dict(id="mixed-color-gray", values=[22, 44, 61, 78], colors=("#3479a1", "#555555"), expected="clear"),
        dict(id="compact-currency", values=[1200, 1800, 2600, 3200], limits=(0, 4000), ticks=(0, 1000, 2000, 3000, 4000), label_format=lambda v: f"${v/1000:g}k", expected="clear"),
        dict(id="fractional", values=[.12, .27, .35, .42], limits=(0, .5), ticks=(0, .1, .2, .3, .4, .5), expected="clear"),
        dict(id="narrow-bars", values=[22, 44, 61, 78], width=40, expected="clear"),
        dict(id="inverted", values=[21, 39, 47, 65], limits=(80, 0), ticks=(0, 20, 40, 60, 80), expected="flagged"),
        dict(id="equal-inverted", values=[40, 40, 40, 40], limits=(80, 0), ticks=(0, 20, 40, 60, 80), expected="flagged"),
        dict(id="missing-scale", values=[22, 44, 61, 78], ticks=(), expected="review"),
        dict(id="logarithmic", values=[8, 30, 100, 500], limits=(1, 1000), ticks=(1, 10, 100, 1000), logarithmic=True, expected="review"),
        dict(id="grouped-spacing", values=[22, 44, 61, 78], positions=(225, 315, 620, 710), width=45, expected="review"),
        dict(id="stacked-colors", values=[22, 44, 61, 78], stacked=True, expected="review"),
        dict(id="negative-mixed", values=[-20, 35, -40, 60], limits=(-60, 80), ticks=(-60, -40, -20, 0, 20, 40, 60, 80), expected="review"),
    ]
    for spec in specs:
        options = {k: v for k, v in spec.items() if k not in {"id", "expected"}}
        issue = "truncated_axis" if spec["id"] == "black-truncated" else "inverted_axis" if spec["id"] in {"inverted", "equal-inverted"} else None
        yield {"id": spec["id"], "expected": spec["expected"], "expected_issue": issue, "values": spec["values"], "image": chart_bytes(**options)}
