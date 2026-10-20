"""Offline, event-clustered audit of an existing trusted evaluation report.

No downloads, inference changes, parameter selection or unseen-data claim.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from watertrace.cli import save_report

KEYS = ('tp', 'fp', 'fn', 'tn', 'labeled', 'assessed', 'unknown_water')
METHODS = ('watertrace', 'vh_otsu', 'filtered_vh_otsu', 'filtered_dual_otsu')


def validate_counts(counts):
    if not isinstance(counts, dict) or any(type(counts.get(k)) is not int or
                                          counts[k] < 0 for k in KEYS):
        raise ValueError('Expected nonnegative integer confusion counts.')
    tp, fp, fn, tn, total, assessed, unknown = (counts[k] for k in KEYS)
    if (tp + fp + fn + tn != total or assessed > total or unknown > fn or
            unknown > total - assessed or tp + fp + fn - unknown > assessed or
            total - assessed - unknown > tn):
        raise ValueError('Inconsistent assessment/confusion counts.')


def scores(counts):
    validate_counts(counts)
    tp, fp, fn, _, total, assessed, unknown = (counts[k] for k in KEYS)
    def ratio(a, b):
        return a / b if b else None
    return {
        'coverage': ratio(assessed, total),
        'selective_error': ratio(fp + fn - unknown, assessed),
        'precision': ratio(tp, tp + fp),
        'recall': ratio(tp, tp + fn),
        'iou': ratio(tp, tp + fp + fn),
        'water_abstention_fraction': ratio(unknown, tp + fn),
    }


def aggregate(rows):
    return {key: sum(row[key] for row in rows) for key in KEYS}


def audit(report, *, replicates=2000, seed=20261019):
    if type(replicates) is not int or not 1 <= replicates <= 10000:
        raise ValueError('Use 1–10000 replicates.')
    cases = report.get('cases')
    if not isinstance(cases, list) or not cases:
        raise ValueError('Expected nonempty evaluation cases.')
    seen = set()
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get('event'), str) or not case['event']:
            raise ValueError('Every case needs an event group.')
        image = case.get('image')
        if not isinstance(image, str) or not image or image in seen:
            raise ValueError('Expected unique image identifiers.')
        seen.add(image)
        for method in METHODS:
            validate_counts(case.get(method))
        if len({case[m]['labeled'] for m in METHODS}) != 1:
            raise ValueError('Methods must share labeled-pixel denominators.')
    events = sorted({case['event'] for case in cases})
    grouped = {event: {method: aggregate([c[method] for c in cases if c['event'] == event])
                       for method in METHODS} for event in events}
    pooled = {method: scores(aggregate([c[method] for c in cases])) for method in METHODS}
    intervals = {method: {} for method in METHODS}
    rng = np.random.default_rng(seed)
    # Use the same event draws for all methods; never sample pixels independently.
    draws = rng.integers(0, len(events), size=(replicates, len(events)))
    for method in METHODS:
        samples = [scores(aggregate([grouped[events[i]][method] for i in draw])) for draw in draws]
        for metric in pooled[method]:
            values = [s[metric] for s in samples if s[metric] is not None]
            bounds = np.quantile(values, [.025, .975]).tolist() if values and len(events) >= 2 else None
            intervals[method][metric] = {'percentile_95': bounds, 'defined_replicates': len(values)}
    return {
        'schema': 'watertrace-uncertainty-audit-v1', 'source_policy': report.get('policy'),
        'events': len(events), 'chips': len(cases), 'seed': seed, 'replicates': replicates,
        'scope': 'Exploratory exposed-set audit. Different assessed subsets; not causal, calibrated, or unseen-event validation.',
        'interval_method': 'Whole-event cluster bootstrap; pooled ratios; percentile 2.5/97.5. Undefined ratios omitted and counted. Fewer than two events: no interval.',
        'pooled': pooled,
        'by_event': {e: {m: scores(grouped[e][m]) for m in METHODS} for e in events},
        'intervals': intervals,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path, help='Trusted evaluate_watertrace.py --experiments JSON')
    parser.add_argument('--output', type=Path, required=True, help='New output path; never overwrite')
    args = parser.parse_args()
    try:
        with args.report.open('rb') as source:
            raw = source.read(16 * 1024 * 1024 + 1)
        if len(raw) > 16 * 1024 * 1024:
            raise ValueError('Evaluation report exceeds 16 MiB.')
        result = audit(json.loads(raw))
        result['source_report_sha256'] = hashlib.sha256(raw).hexdigest()
        encoded = json.dumps(result, indent=2, allow_nan=False) + '\n'
        save_report(args.output, encoded)
    except (OSError, ValueError, TypeError, AttributeError, RecursionError) as exc:
        parser.exit(2, f'Audit failed: {exc}\n')
    print(json.dumps({'events': result['events'], 'chips': result['chips'], 'pooled': result['pooled']}, indent=2))


if __name__ == '__main__':
    main()
