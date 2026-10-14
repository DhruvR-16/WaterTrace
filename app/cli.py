"""Local batch chart audits: python -m app.cli chart.png [more-images ...]."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

from app.privacy import display_filename, inspection_report
from app.upload_limits import MAX_UPLOAD
from app.vision import InvalidImage, analyze

MAX_FILES = 100


def inspect_file(path: Path) -> tuple[dict | None, dict | None]:
    name = display_filename(path.name)

    def error(code, message):
        return None, {"filename": name, "code": code, "message": message}

    try:
        if not path.is_file():
            return error("unreadable_file", "Choose a readable regular file.")
        with path.open("rb") as file:
            raw = file.read(MAX_UPLOAD + 1)
    except OSError:
        return error("unreadable_file", "Could not read this file.")
    if len(raw) > MAX_UPLOAD:
        return error("file_too_large", "Use an image up to 8 MiB.")
    try:
        return inspection_report(analyze(raw, name)), None
    except InvalidImage as exc:
        return error("invalid_image", str(exc))
    except Exception:
        return error("inspection_failed", "Inspection failed; no result was produced.")


def main(argv=None, *, out=None, err=None) -> int:
    out = sys.stdout if out is None else out
    err = sys.stderr if err is None else err
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", nargs="+", type=Path, help="Explicit image paths; no recursive scanning.")
    parser.add_argument("--output", type=Path, help="Write a private JSON report to a new file; never overwrite.")
    parser.add_argument("--fail-on-findings", action="store_true", help="Exit 1 if any image is flagged or needs review.")
    args = parser.parse_args(argv)
    if len(args.images) > MAX_FILES:
        parser.error(f"Inspect at most {MAX_FILES} files per batch.")
    if args.output and (args.output.exists() or args.output.is_symlink()):
        print("Output already exists. Choose a new report path; nothing was overwritten.", file=err)
        return 2
    report = {"schema_version": "1.0", "generated_at": datetime.now(timezone.utc).isoformat(),
              "scope": "Pixel-based design audit; not source-data verification. Reports may contain sensitive OCR text.",
              "inspections": [], "errors": []}
    for index, path in enumerate(args.images, start=1):
        result, error = inspect_file(path)
        report["errors" if error else "inspections"].append({**(error or result), "input_index": index})
    report["summary"] = {"requested": len(args.images), "completed": len(report["inspections"]),
                         "errors": len(report["errors"]),
                         **{status: sum(r["status"] == status for r in report["inspections"])
                            for status in ("clear", "flagged", "review")}}
    try:
        if args.output:
            # O_EXCL also protects against symlinks/races after the early check.
            descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                json.dump(report, output, indent=2, ensure_ascii=False, allow_nan=False)
                output.write("\n")
        else:
            json.dump(report, out, indent=2, ensure_ascii=False, allow_nan=False)
            out.write("\n")
    except (OSError, ValueError):
        print("Could not write the report. Check the output location and available space.", file=err)
        return 2
    if report["errors"]:
        return 2
    if args.fail_on_findings and any(r["status"] != "clear" for r in report["inspections"]):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
