"""Local, no-overwrite evidence reports; never sends imagery to a remote service."""
import argparse
import json
import os
from pathlib import Path
import sys
from tempfile import NamedTemporaryFile

from fieldwatch.engine import InvalidRaster, MAX_BYTES
from fieldwatch.exports import geojson_export
from fieldwatch.service import export_report, run_analysis
from fieldwatch.zone_input import load_zones, MAX_ZONE_BYTES


def bounded_read(path, limit):
    with path.open('rb') as source:
        content=source.read(limit+1)
    if len(content)>limit:
        raise InvalidRaster('Input exceeds the supported byte limit.')
    return content


def save_report(path, payload):
    """Publish complete bytes exclusively; clean up private staging on failure."""
    # Same-directory staging keeps the hard link on one filesystem. Linking is
    # atomic and refuses existing destinations, including dangling symlinks.
    with NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                            prefix='.fieldwatch-', suffix='.tmp') as staging:
        staging.write(payload)
        staging.flush()
        os.fsync(staging.fileno())
        os.link(staging.name, path)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('current',type=Path)
    parser.add_argument('--date',required=True)
    parser.add_argument('--reference',type=Path)
    parser.add_argument('--reference-date')
    parser.add_argument('--same-orbit',action='store_true',help='Confirm matching orbit, direction, polarization and calibration.')
    parser.add_argument('--zones',type=Path,help='Longitude/latitude GeoJSON FeatureCollection.')
    parser.add_argument('--format',choices=('json','geojson'),default='json',help='Evidence report (default) or geographic review-zone handoff; neither contains imagery.')
    parser.add_argument('--output',type=Path,required=True,help='New private JSON file; existing files are never replaced.')
    args=parser.parse_args(argv)
    try:
        zones=load_zones(bounded_read(args.zones,MAX_ZONE_BYTES)) if args.zones else None
        result=run_analysis(bounded_read(args.current,MAX_BYTES),observed_on=args.date,
            reference_raw=bounded_read(args.reference,MAX_BYTES) if args.reference else None,
            reference_on=args.reference_date,same_orbit=args.same_orbit,zones=zones)
        exported=geojson_export(result) if args.format=='geojson' else export_report(result)
        payload=json.dumps(exported,indent=2,allow_nan=False)+'\n'
        save_report(args.output, payload)
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
