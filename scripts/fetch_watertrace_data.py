"""Download explicit Sen1Floods11 subsets; labels are for evaluation, not inference.

Usage: python scripts/fetch_watertrace_data.py --split demo|lab|valid|test
Data stays in ignored data/watertrace. No cloud credentials are needed.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import sys
from tempfile import NamedTemporaryFile, mkstemp

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from watertrace.data_integrity import cache_path, fingerprint, recorded_objects, IntegrityError
BASE = "https://storage.googleapis.com/sen1floods11/v1.1/"
FOLDER = "data/flood_events/HandLabeled/"
DATA = ROOT / "data" / "watertrace"


def fetch(client, key, expected=None):
    target = cache_path(DATA, key)
    cached = fingerprint(target) if target.exists() else None
    if cached is not None and expected is not None:
        if cached != expected:
            raise IntegrityError(f'Cached object changed: {key}. Preserve or move it aside before retrying.')
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
    downloaded = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    if not raw or (expected is not None and downloaded != expected):
        raise IntegrityError(f'Download does not match the recorded object: {key}. No cache object was replaced.')
    if cached is not None:
        if cached != downloaded:
            raise IntegrityError(f'Unrecorded cache object differs from the download: {key}. Preserve or move it aside before retrying.')
        return target
    # Exclusive publication prevents competing downloads from overwriting one
    # another and avoids following a predictable .partial-file symlink.
    with NamedTemporaryFile(mode='wb', dir=target.parent, prefix='.watertrace-', suffix='.tmp') as temp:
        temp.write(raw)
        temp.flush()
        os.fsync(temp.fileno())
        try:
            os.link(temp.name, target)
        except FileExistsError:
            if fingerprint(cache_path(DATA, key)) != downloaded:
                raise IntegrityError(f'Another writer created different content: {key}. No file was replaced.') from None
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=["demo", "lab", "valid", "test"], default="demo")
    args = parser.parse_args()
    records = recorded_objects(DATA)
    with httpx.Client(timeout=60, follow_redirects=False) as client:
        split = "train" if args.split == "demo" else "test" if args.split == "lab" else args.split
        split_key = f"splits/flood_handlabeled/flood_{split}_data.csv"
        split_path = fetch(client, split_key, records.get(split_key))
        rows = list(csv.reader(io.StringIO(split_path.read_text())))
        pairs = [(Path(row[0]).name, Path(row[1]).name) for row in rows if len(row) == 2]
        if args.split == "demo":
            # Deterministic examples from training split, never select on test performance.
            pairs = [next(p for p in pairs if p[0].startswith(country + "_")) for country in ("Spain", "India", "USA")]
        if args.split == 'lab':
            sys.path.insert(0,str(ROOT))
            from watertrace.lab import CASES
            selected={item['chip']+'_S1Hand.tif' for item in CASES if item['kind']=='real_replay'}
            pairs=[p for p in pairs if p[0] in selected]
            if len(pairs)!=len(selected):raise ValueError('Lab case not found in the public test split.')
        keys = [FOLDER + layer + "/" + name for image, label in pairs
                for layer, name in [("S1Hand", image), ("LabelHand", label)]]
        if args.split == "demo":
            keys += [FOLDER + "S2Hand/" + image.replace("S1Hand", "S2Hand") for image, _ in pairs]
        keys += ["Sen1Floods11_Metadata.geojson"]
        with ThreadPoolExecutor(max_workers=4) as pool:
            paths = list(pool.map(lambda key: fetch(client, key, records.get(key)), keys))
        paths.append(split_path)
        manifest = {"dataset": "Sen1Floods11 v1.1", "split": args.split,
                    "source": "https://github.com/cloudtostreet/Sen1Floods11",
                    "pairs": pairs, "objects": [{"key": p.relative_to(DATA).as_posix(),
                        "sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "bytes": p.stat().st_size} for p in paths]}
        manifest_path = cache_path(DATA, args.split + '-manifest.json')
        descriptor, staging = mkstemp(dir=DATA, prefix='.watertrace-', suffix='.tmp')
        try:
            with os.fdopen(descriptor, 'w', encoding='utf-8') as temp:
                temp.write(json.dumps(manifest, indent=2) + '\n')
                temp.flush()
                os.fsync(temp.fileno())
            os.replace(staging, manifest_path)
        finally:
            Path(staging).unlink(missing_ok=True)
        print(json.dumps({"split": args.split, "chips": len(pairs), "objects": len(paths), "bytes": sum(p.stat().st_size for p in paths)}))


if __name__ == "__main__":
    try:
        main()
    except (httpx.HTTPError, OSError, ValueError, StopIteration) as exc:
        print(str(exc) if isinstance(exc, IntegrityError) else f"Dataset download failed ({type(exc).__name__}); rerun to resume.", file=sys.stderr)
        raise SystemExit(2)
