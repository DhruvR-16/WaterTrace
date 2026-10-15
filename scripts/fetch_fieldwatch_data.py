"""Download explicit public Sen1Floods11 subsets; never ship benchmark labels in the app.

Usage: python scripts/fetch_fieldwatch_data.py --split demo|valid|test
Data stays in ignored data/fieldwatch. No cloud credentials are needed.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
import hashlib
import io
import json
from pathlib import Path
import sys

import httpx

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://storage.googleapis.com/sen1floods11/v1.1/"
FOLDER = "data/flood_events/HandLabeled/"
DATA = ROOT / "data" / "fieldwatch"


def fetch(client, key):
    target = DATA / key
    if target.is_file():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    # Bounded public dataset download; no arbitrary host or path from user input.
    with client.stream("GET", BASE + key) as response:
        response.raise_for_status()
        raw = bytearray()
        for chunk in response.iter_bytes():
            raw.extend(chunk)
            if len(raw) > 32 * 1024 * 1024:
                raise ValueError("Dataset object exceeded 32 MiB.")
    temp = target.with_suffix(target.suffix + ".partial")
    temp.write_bytes(raw)
    temp.replace(target)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=["demo", "valid", "test"], default="demo")
    args = parser.parse_args()
    with httpx.Client(timeout=60, follow_redirects=False) as client:
        split = "train" if args.split == "demo" else args.split
        split_path = fetch(client, f"splits/flood_handlabeled/flood_{split}_data.csv")
        rows = list(csv.reader(io.StringIO(split_path.read_text())))
        pairs = [(Path(row[0]).name, Path(row[1]).name) for row in rows if len(row) == 2]
        if args.split == "demo":
            # Deterministic examples from training split, never select on test performance.
            pairs = [next(p for p in pairs if p[0].startswith(country + "_")) for country in ("Spain", "India", "USA")]
        keys = [FOLDER + layer + "/" + name for image, label in pairs
                for layer, name in [("S1Hand", image), ("LabelHand", label)]]
        if args.split == "demo":
            keys += [FOLDER + "S2Hand/" + image.replace("S1Hand", "S2Hand") for image, _ in pairs]
        keys += ["Sen1Floods11_Metadata.geojson"]
        with ThreadPoolExecutor(max_workers=4) as pool:
            paths = list(pool.map(lambda key: fetch(client, key), keys))
        manifest = {"dataset": "Sen1Floods11 v1.1", "split": args.split,
                    "source": "https://github.com/cloudtostreet/Sen1Floods11",
                    "pairs": pairs, "objects": [{"key": str(p.relative_to(DATA)),
                        "sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "bytes": p.stat().st_size} for p in paths]}
        (DATA / (args.split + "-manifest.json")).write_text(json.dumps(manifest, indent=2) + "\n")
        print(json.dumps({"split": args.split, "chips": len(pairs), "objects": len(paths), "bytes": sum(p.stat().st_size for p in paths)}))


if __name__ == "__main__":
    try:
        main()
    except (httpx.HTTPError, OSError, ValueError, StopIteration) as exc:
        print(f"Dataset download failed ({type(exc).__name__}); rerun to resume.", file=sys.stderr)
        raise SystemExit(2)
