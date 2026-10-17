"""Run deterministic safety-contract exercises; not an accuracy benchmark."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fieldwatch.lab import CASES, run_case


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    results=[]
    for item in CASES:
        if item['kind']!='synthetic':continue
        result=run_case(item['id'])
        checks=result['lab']['checks']
        results.append({'id':item['id'],'passed':all(c['passed'] for c in checks),'checks':checks})
    report={'scope':'Synthetic contracts only; no real-world accuracy claim.','passed':all(r['passed'] for r in results),'cases':results}
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        with args.output.open('x') as out:json.dump(report,out,indent=2)
    print(json.dumps(report,indent=2))
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
