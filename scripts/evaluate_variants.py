"""Measure safe abstention versus incorrect acceptance after image transforms.

Self-authored regression images only, not a held-out or real-world benchmark.
An abstention on a supported input is safe but lowers reconstruction coverage.
"""
import argparse
from io import BytesIO
import json
from pathlib import Path
import sys

from PIL import Image, ImageFilter, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.vision import analyze
from scripts.evaluate import demo_cases, score_case


def variants(raw):
    with Image.open(BytesIO(raw)) as source:
        image = source.convert("RGB")
    transforms = [
        ("jpeg-q50", image, "JPEG", {"quality": 50}),
        ("webp-q60", image, "WEBP", {"quality": 60}),
        ("resize-two-thirds", image.resize((round(image.width*2/3), round(image.height*2/3)), Image.Resampling.LANCZOS), "PNG", {}),
        ("blur-0.6px", image.filter(ImageFilter.GaussianBlur(.6)), "PNG", {}),
        ("white-padding-40px", ImageOps.expand(image, border=40, fill="white"), "PNG", {}),
    ]
    orientation = Image.Exif()
    orientation[274] = 6  # Stored counterclockwise; EXIF instructs clockwise display.
    transforms.append(("exif-rotated-jpeg", image.transpose(Image.Transpose.ROTATE_90), "JPEG", {"quality": 80, "exif": orientation}))
    for name, transformed, fmt, options in transforms:
        buffer = BytesIO()
        transformed.save(buffer, fmt, **options)
        yield name, buffer.getvalue()


def score_variant(case, result):
    score = score_case(case, result)
    clean_refusal = result["status"] == "review" and not result["bars"] and result["reconstruction"] is None
    return {**score, "safe": score["correct"] or clean_refusal,
            "refused": clean_refusal, "accepted": result["status"] != "review",
            "issues": [finding["kind"] for finding in result["findings"]]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=("demo", "stress", "all"), default="demo")
    parser.add_argument("--summary", action="store_true", help="Omit per-case records, retaining failures and coverage.")
    args = parser.parse_args()
    selected = list(demo_cases()) if args.suite in {"demo", "all"} else []
    if args.suite in {"stress", "all"}:
        from scripts.stress_cases import cases
        selected.extend({**case, "id": "stress/" + case["id"]} for case in cases())
    records = []
    for case in selected:
        for transform, raw in variants(case["image"]):
            variant = {**case, "id": case["id"] + "/" + transform}
            records.append({**score_variant(variant, analyze(raw, "unknown-image")), "transform": transform})
    supported = [r for r in records if r["expected"] != "review"]
    unsupported = [r for r in records if r["expected"] == "review"]
    report = dict(
        scope="Transformed self-authored regression images, not independent real-world accuracy.",
        policy="A correct acceptance or a clean refusal is safe. Refusal is not successful recovery.",
        suite=args.suite, total=len(records), safe=sum(r["safe"] for r in records),
        unsafe_acceptances=sum(not r["safe"] for r in records),
        supported_total=len(supported), supported_correct_reconstructions=sum(r["correct"] for r in supported),
        supported_refusals=sum(r["refused"] for r in supported),
        supported_reconstruction_rate=sum(r["correct"] for r in supported)/len(supported) if supported else None,
        unsupported_total=len(unsupported), unsupported_refusals=sum(r["refused"] for r in unsupported),
        refusal_reasons={issue: sum(issue in r["issues"] for r in supported if r["refused"])
                         for issue in sorted({issue for r in supported if r["refused"] for issue in r["issues"]})},
        coverage_by_transform={transform: {
            "supported": sum(r["transform"] == transform for r in supported),
            "reconstructed": sum(r["transform"] == transform and r["correct"] for r in supported),
        } for transform in sorted({r["transform"] for r in records})},
        failures=[r for r in records if not r["safe"]],
    )
    if not args.summary:
        report["cases"] = records
    print(json.dumps(report, indent=2))
    return 0 if all(r["safe"] for r in records) else 1


if __name__ == "__main__":
    raise SystemExit(main())
