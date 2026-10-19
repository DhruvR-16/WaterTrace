"""Reproduce a bounded Beira historical pair. Default: metadata plan, no raster download."""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import sys
from tempfile import NamedTemporaryFile

import httpx
import numpy as np
import rasterio
from affine import Affine
from rasterio.io import MemoryFile
from rasterio.windows import Window

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from watertrace.cli import bounded_read, save_report
from watertrace.data_integrity import cache_path, inspect_object, unique_object
from watertrace.engine import MAX_BYTES, read_raster
from watertrace.pair_search import asset_url, plan_pair, signature
from watertrace.service import export_report, run_analysis

CATALOG = 'https://explorer.digitalearth.africa/stac/search'
CURRENT = '9188a45d-a054-50d5-bd8f-c0f334cf0860'
QUERY = {'collections': 's1_rtc', 'bbox': '34.7,-19.8024,34.8024,-19.7',
         'datetime': '2019-03-01/2019-03-31', 'limit': 100}
WINDOW = Window(3500, 3500, 512, 512)


def search(client):
    # No arbitrary endpoints, redirects, pagination or unbounded JSON bodies.
    with client.stream('GET', CATALOG, params=QUERY) as response:
        response.raise_for_status()
        body = bytearray()
        for chunk in response.iter_bytes():
            body.extend(chunk)
            if len(body) > 4 * 1024 * 1024:
                raise ValueError('Catalog response exceeds 4 MiB.')
    catalog = json.loads(body)
    if not isinstance(catalog, dict) or not isinstance(catalog.get('features'), list) or not isinstance(catalog.get('links', []), list):
        raise ValueError('Malformed catalog response.')
    if any(not isinstance(link, dict) or link.get('rel') == 'next' for link in catalog.get('links', [])):
        raise ValueError('Search is truncated; do not silently select from an incomplete catalog.')
    return catalog['features']


def linear_to_db(vv, vh, mask):
    if vv.shape != vh.shape or vv.shape != mask.shape or vv.ndim != 2:
        raise ValueError('Band and quality-mask dimensions must match.')
    valid = (mask == 1) & np.isfinite(vv) & np.isfinite(vh) & (vv > 0) & (vh > 0)
    out = np.full((2, *vv.shape), -9999, np.float32)
    for i, band in enumerate((vv, vh)):
        out[i, valid] = 10 * np.log10(band[valid])
    return out


def crop(item):
    signature(item)
    expected = Affine(*item['properties']['proj:transform'])
    arrays, urls = [], []
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR', GDAL_HTTP_TIMEOUT='30',
                      GDAL_HTTP_MAX_RETRY='0', GDAL_CACHEMAX=16 * 1024 * 1024):
        for band in ('vv', 'vh', 'mask'):
            url = asset_url(item['assets'][band]['href'])
            with rasterio.open(url) as src:
                if src.count != 1 or src.shape != (5000, 5000) or src.crs is None or src.crs.to_epsg() != 4326 or src.transform != expected:
                    raise ValueError('Remote raster header disagrees with catalog metadata.')
                arrays.append(src.read(1, window=WINDOW, masked=True))
                transform = src.window_transform(WINDOW)
            urls.append(url)
    vv, vh = (a.astype(np.float32).filled(np.nan) for a in arrays[:2])
    mask = arrays[2].filled(0)
    out = linear_to_db(vv, vh, mask)
    with MemoryFile() as memory:
        with memory.open(driver='GTiff', width=512, height=512, count=2, dtype='float32',
                         crs='EPSG:4326', transform=transform, nodata=-9999, compress='deflate') as dest:
            dest.write(out)
        raw = memory.read()
    read_raster(raw)  # Apply exactly the same input checks as uploads.
    return raw, {'stac_id': item['id'], 'properties': item['properties'], 'assets': urls,
                 'window_col_row_width_height': list(WINDOW.flatten()),
                 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}


def save_bytes(path, raw):
    with NamedTemporaryFile(dir=path.parent, prefix='.watertrace-', suffix='.tmp') as staging:
        staging.write(raw)
        staging.flush()
        os.fsync(staging.fileno())
        os.link(staging.name, path)


def load_pair_json(root, filename):
    path = cache_path(root, filename)
    if not path.is_file():
        raise ValueError('Expected a regular manifest or report file.')
    def reject_constant(value):
        raise ValueError('Non-finite JSON is unsupported.')
    try:
        result = json.loads(bounded_read(path, 4 * 1024 * 1024),
                            object_pairs_hook=unique_object, parse_constant=reject_constant)
    except (UnicodeError, RecursionError):
        raise ValueError('Invalid bounded JSON.') from None
    if not isinstance(result, dict):
        raise ValueError('Expected a JSON object.')
    return result


def verify_pair(root):
    """Check local byte consistency and reproduce the report, never repairing it.

    A local manifest is not signed upstream provenance. Agreement cannot verify
    original acquisition metadata, agricultural relevance or flood accuracy.
    """
    manifest = load_pair_json(root, 'provenance.json')
    if manifest.get('case') != 'beira-2019-pipeline-case':
        raise ValueError('Unsupported pair case.')
    objects = []
    for role in ('current', 'earlier'):
        record = manifest.get(role)
        if not isinstance(record, dict):
            raise ValueError('Missing crop record.')
        size, digest = record.get('bytes'), record.get('sha256')
        if (type(size) is not int or not 0 < size <= MAX_BYTES or
                not isinstance(digest, str) or re.fullmatch('[a-f0-9]{64}', digest) is None):
            raise ValueError('Invalid crop fingerprint.')
        objects.append(inspect_object(root, role + '.tif', {'bytes': size, 'sha256': digest}))
    result = {'passed': False, 'objects': objects, 'report': 'not_checked',
              'scope': 'Local manifest consistency and report replay with this installed engine. Not signed upstream authenticity, independent metadata verification or flood-change accuracy.'}
    if any(row['status'] != 'ok' for row in objects):
        return result
    saved = load_pair_json(root, 'report.json')
    raw, earlier = (bounded_read(cache_path(root, role + '.tif'), MAX_BYTES) for role in ('current', 'earlier'))
    # Check the exact in-memory bytes too: a file may change after fingerprinting.
    if any(hashlib.sha256(content).hexdigest() != manifest[role]['sha256']
           for role, content in (('current', raw), ('earlier', earlier))):
        raise ValueError('Crop changed while being verified.')
    dates = []
    for role in ('current', 'earlier'):
        properties = manifest[role].get('properties')
        if not isinstance(properties, dict) or not isinstance(properties.get('datetime'), str):
            raise ValueError('Missing recorded acquisition date.')
        dates.append(properties['datetime'][:10])
    fresh = export_report(run_analysis(raw, name='Beira historical pair — unvalidated change',
                         observed_on=dates[0], reference_raw=earlier, reference_on=dates[1], same_orbit=True))
    # Geometry tuples become JSON arrays on disk. Compare the serialized schema,
    # not Python tuple/list implementation details.
    fresh = json.loads(json.dumps(fresh, allow_nan=False))
    # Runtime timing is intentionally variable; all evidence and policy fields are checked.
    stable = lambda report: {k: v for k, v in report.items() if k not in ('generated_at', 'elapsed_ms')}
    result['report'] = 'reproduced' if stable(saved) == stable(fresh) else 'mismatch'
    result['passed'] = result['report'] == 'reproduced'
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--approve-download', action='store_true', help='Approve public COG window reads and local processing; no AWS account is used.')
    mode.add_argument('--verify', action='store_true', help='Offline crop consistency and report replay only; no downloads or file changes.')
    parser.add_argument('--output', type=Path, default=ROOT / 'data/watertrace-pairs/beira-2019')
    args = parser.parse_args(argv)
    try:
        if args.verify:
            verification = verify_pair(args.output)
            print(json.dumps(verification, indent=2, allow_nan=False))
            return 0 if verification['passed'] else 1
        if args.approve_download and (args.output.exists() or args.output.is_symlink()):
            raise ValueError('Output directory already exists; choose a new path. Nothing overwritten.')
        with httpx.Client(timeout=45, follow_redirects=False) as client:
            items = search(client)
        plan = plan_pair(items, CURRENT, '2019-03-09')
        print(json.dumps(plan, indent=2, allow_nan=False))
        if not args.approve_download:
            return 0
        if not plan['selected_id']:
            raise ValueError('No eligible earlier observation; no download attempted.')
        current = next(i for i in items if i['id'] == CURRENT)
        earlier = next(i for i in items if i['id'] == plan['selected_id'])
        raw, current_meta = crop(current)
        previous, earlier_meta = crop(earlier)
        current_date, earlier_date = (i['properties']['datetime'][:10] for i in (current, earlier))
        report = run_analysis(raw, name='Beira historical pair — unvalidated change', observed_on=current_date,
                              reference_raw=previous, reference_on=earlier_date, same_orbit=True)
        manifest = {'case': 'beira-2019-pipeline-case', 'catalog': CATALOG, 'query': QUERY, 'plan': plan,
                    'current': current_meta, 'earlier': earlier_meta,
                    'conversion': 'Linear gamma0 to dB: 10*log10; only provider mask==1 and finite positive VV/VH retained.',
                    'attribution': 'Contains modified Copernicus Sentinel data (2019), processed by Digital Earth Africa / Sinergise.',
                    'validation': 'Pipeline replay only. No date-matched independent reference, no measured flood-change accuracy. Not verified agricultural boundaries.'}
        args.output.mkdir(parents=True, mode=0o700, exist_ok=False)
        save_bytes(args.output / 'current.tif', raw)
        save_bytes(args.output / 'earlier.tif', previous)
        save_report(args.output / 'provenance.json', json.dumps(manifest, indent=2, allow_nan=False))
        save_report(args.output / 'report.json', json.dumps(export_report(report), indent=2, allow_nan=False))
        print('Saved private local crops, provenance and report. Not a validation result.')
        return 0
    except (ValueError, KeyError, TypeError, OSError, httpx.HTTPError, rasterio.errors.RasterioError) as exc:
        print(f'Pair preparation stopped: {type(exc).__name__}. Check catalog availability, metadata and output path. No existing output is replaced.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
