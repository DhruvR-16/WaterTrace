"""Reproducible fixture report. No claims about public dataset performance."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.vision import analyze

ROOT = Path(__file__).resolve().parents[1]

def main():
    truth = json.loads((ROOT / "tests" / "fixtures" / "truth.json").read_text())
    records = []
    for case in truth:
        result = analyze((ROOT / "app" / "static" / "samples" / f"{case['id']}.png").read_bytes())
        expected = "review" if case["expected"] == "review" else "clear" if case["expected"] == "clear" else "flagged"
        errors = [abs(b["value"] - v) for b, v in zip(result["bars"], case["values"])]
        records.append(dict(case=case["id"], expected=expected, actual=result["status"],
                            correct=result["status"] == expected, mean_absolute_error=sum(errors)/len(errors) if errors else None,
                            processing_ms=result["processing_ms"], trace_steps=len(result["trace"])))
    report = dict(scope="Four self-authored fixtures only; not an external benchmark.",
                  cases=records, correct=sum(r["correct"] for r in records), total=len(records))
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
