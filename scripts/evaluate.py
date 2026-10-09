"""Reproducible synthetic evaluation; never claim public-dataset accuracy."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.vision import analyze


def score_case(case, result):
    expected = case["expected"]
    expected_issue = case.get("expected_issue")
    decision_correct = result["status"] == expected and (
        expected_issue is None or expected_issue in {f["kind"] for f in result["findings"]})
    expects_values = expected != "review"
    count_correct = len(result["bars"]) == (len(case["values"]) if expects_values else 0)
    errors = [abs(bar["value"]-value) for bar, value in zip(result["bars"], case["values"])] if count_correct and expects_values else []
    numeric_correct = bool(errors) and max(errors) <= max(1e-8, max(abs(v) for v in case["values"]) * .015) if expects_values else count_correct
    reconstruction_correct = bool(result["reconstruction"]) == expects_values
    return dict(case=case["id"], expected=expected, actual=result["status"],
                decision_correct=decision_correct, value_count_correct=count_correct,
                reconstructed=bool(result["reconstruction"]),
                correct=decision_correct and count_correct and numeric_correct and reconstruction_correct,
                mean_absolute_error=sum(errors)/len(errors) if errors else None,
                max_absolute_error=max(errors) if errors else None,
                processing_ms=result["processing_ms"], trace_steps=len(result["trace"]))


def demo_cases():
    truth = json.loads((ROOT / "tests" / "fixtures" / "truth.json").read_text())
    for case in truth:
        original_expected = case["expected"]
        yield {**case,
               "expected": "review" if original_expected == "review" else "clear" if original_expected == "clear" else "flagged",
               "expected_issue": case.get("expected_issue") or {"truncated": "truncated_axis", "inverted": "inverted_axis"}.get(original_expected),
               "image": (ROOT / "app" / "static" / "samples" / f"{case['id']}.png").read_bytes()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=("demo", "stress", "all"), default="demo")
    args = parser.parse_args()
    selected = list(demo_cases()) if args.suite in {"demo", "all"} else []
    if args.suite in {"stress", "all"}:
        from scripts.stress_cases import cases
        selected.extend({**case, "id": "stress/"+case["id"]} for case in cases())
    records = [score_case(case, analyze(case["image"], "evaluation.png")) for case in selected]
    supported = [r for r in records if r["expected"] != "review"]
    unsupported = [r for r in records if r["expected"] == "review"]
    report = dict(
        scope="Self-authored synthetic regression cases; not an external or held-out benchmark.",
        suite=args.suite, cases=records, correct=sum(r["correct"] for r in records), total=len(records),
        supported_reconstruction_rate=sum(r["reconstructed"] for r in supported)/len(supported) if supported else None,
        unsupported_refusal_rate=sum(r["actual"] == "review" for r in unsupported)/len(unsupported) if unsupported else None,
        clean_false_flags=sum(r["actual"] == "flagged" for r in records if r["expected"] == "clear"),
    )
    print(json.dumps(report, indent=2))
    return 0 if all(r["correct"] for r in records) else 1


if __name__ == "__main__":
    raise SystemExit(main())
