"""Local, no-overwrite evidence reports; never sends imagery to a remote service."""
import argparse
import json
import os
from pathlib import Path
import sys

from fieldwatch.engine import InvalidRaster, MAX_BYTES
from fieldwatch.service import export_report, run_analysis


def bounded_read(path, limit):
    with path.open('rb') as source:
        content=source.read(limit+1)
    if len(content)>limit:
        raise InvalidRaster('Input exceeds the supported byte limit.')
    return content


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('current',type=Path)
    parser.add_argument('--date',required=True)
    parser.add_argument('--reference',type=Path)
    parser.add_argument('--reference-date')
    parser.add_argument('--same-orbit',action='store_true',help='Confirm matching orbit, direction, polarization and calibration.')
    parser.add_argument('--zones',type=Path,help='Longitude/latitude GeoJSON FeatureCollection.')
    parser.add_argument('--output',type=Path,required=True,help='New private JSON file; existing files are never replaced.')
    args=parser.parse_args(argv)
    try:
        zones=json.loads(bounded_read(args.zones,200_000)) if args.zones else None
        if args.zones and (not isinstance(zones, dict) or zones.get('type') != 'FeatureCollection'):
            raise InvalidRaster('Zones must be a GeoJSON FeatureCollection.')
        result=run_analysis(bounded_read(args.current,MAX_BYTES),observed_on=args.date,
            reference_raw=bounded_read(args.reference,MAX_BYTES) if args.reference else None,
            reference_on=args.reference_date,same_orbit=args.same_orbit,zones=zones)
        payload=json.dumps(export_report(result),indent=2,allow_nan=False)+'\n'
        descriptor=os.open(args.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(descriptor,'w') as output:output.write(payload)
        print('Evidence report saved. This is not a flood-damage or safety assessment.')
        return 0
    except (InvalidRaster, ValueError) as exc:
        print(str(exc) if isinstance(exc,InvalidRaster) else 'Zones must contain valid JSON.',file=sys.stderr)
        return 2
    except FileExistsError:
        print('Output already exists; choose a new path.',file=sys.stderr)
        return 3
    except OSError:
        print('Could not read input or create output. Check paths and permissions.',file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())
