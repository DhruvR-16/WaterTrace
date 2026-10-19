"""Check downloaded objects offline without modifying files or contacting a server."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from watertrace.data_integrity import SPLITS, verify_dataset


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--split', choices=SPLITS, default='demo')
    parser.add_argument('--data', type=Path, default=ROOT / 'data/watertrace')
    args = parser.parse_args(argv)
    try:
        report = verify_dataset(args.data, args.split)
    except (OSError, ValueError):
        print('Cannot verify: manifest is missing, unreadable or invalid. No files were changed.', file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
