"""Offline cache consistency checks, not upstream authenticity verification."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

SPLITS = ('demo', 'lab', 'valid', 'test')
MAX_OBJECT_BYTES = 32 * 1024 * 1024
MAX_MANIFEST_BYTES = 4 * 1024 * 1024


class IntegrityError(ValueError):
    pass


def cache_path(root, key):
    """Refuse traversal and symlink components, including dangling links."""
    if (not isinstance(key, str) or not key or '\\' in key
            or '\x00' in key or ':' in key or key.startswith('/')
            or any(part in ('', '.', '..') for part in key.split('/'))):
        raise IntegrityError('Unsafe cache object path.')
    path = Path(root)
    if path.is_symlink():
        raise IntegrityError('Cache root must not be a symlink.')
    for part in PurePosixPath(key).parts:
        path = path / part
        if path.is_symlink():
            raise IntegrityError(f'Cache path contains a symlink: {key}')
    return path


def fingerprint(path):
    if not path.is_file():
        raise IntegrityError('Cache object is not a regular file.')
    digest, size = hashlib.sha256(), 0
    with path.open('rb') as source:
        while chunk := source.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_OBJECT_BYTES:
                raise IntegrityError('Cache object exceeds 32 MiB.')
            digest.update(chunk)
    return {'bytes': size, 'sha256': digest.hexdigest()}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise IntegrityError('Manifest contains duplicate JSON keys.')
        result[key] = value
    return result


def load_manifest(root, split):
    if split not in SPLITS:
        raise IntegrityError('Unsupported dataset split.')
    path = cache_path(root, split + '-manifest.json')
    try:
        with path.open('rb') as source:
            raw = source.read(MAX_MANIFEST_BYTES + 1)
        if len(raw) > MAX_MANIFEST_BYTES:
            raise IntegrityError('Manifest exceeds 4 MiB.')
        manifest = json.loads(raw, object_pairs_hook=unique_object)
        if not isinstance(manifest, dict) or manifest.get('split') != split or manifest.get('dataset') != 'Sen1Floods11 v1.1':
            raise IntegrityError('Manifest dataset or split does not match.')
        objects = manifest.get('objects')
        if not isinstance(objects, list) or not 1 <= len(objects) <= 10000:
            raise IntegrityError('Manifest must list 1–10000 objects.')
        records = {}
        for row in objects:
            if not isinstance(row, dict):
                raise IntegrityError('Invalid manifest object.')
            key, size, digest = row.get('key'), row.get('bytes'), row.get('sha256')
            cache_path(root, key)
            if (key in records or type(size) is not int or not 0 < size <= MAX_OBJECT_BYTES
                    or not isinstance(digest, str) or not re.fullmatch('[a-f0-9]{64}', digest)):
                raise IntegrityError('Invalid or duplicate manifest object record.')
            records[key] = {'bytes': size, 'sha256': digest}
        return records
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise IntegrityError('Manifest is not valid bounded JSON.') from exc


def inspect_object(root, key, expected):
    try:
        path = cache_path(root, key)
        if not path.exists():
            return {'key': key, 'status': 'missing'}
        actual = fingerprint(path)
        return {'key': key, 'status': 'ok' if actual == expected else 'mismatch'}
    except (OSError, IntegrityError):
        return {'key': key, 'status': 'unreadable_or_unsafe'}


def verify_dataset(root, split):
    records = load_manifest(root, split)
    objects = [inspect_object(root, key, expected) for key, expected in records.items()]
    return {'split': split, 'passed': all(row['status'] == 'ok' for row in objects),
            'scope': 'Local files versus a locally recorded manifest; not proof of upstream authenticity, raster validity or scientific accuracy.',
            'checked': len(objects), 'objects': objects}


def recorded_objects(root):
    """Build a consistent ledger before any download or manifest replacement."""
    records = {}
    for split in SPLITS:
        path = cache_path(root, split + '-manifest.json')
        if not path.exists():
            continue
        for key, expected in load_manifest(root, split).items():
            if key in records and records[key] != expected:
                raise IntegrityError(f'Conflicting manifests for {key}; retain the files and reconcile them before downloading.')
            records[key] = expected
    for key, expected in records.items():
        result = inspect_object(root, key, expected)
        if result['status'] not in ('ok', 'missing'):
            raise IntegrityError(f'Cached object failed integrity checks: {key}. Preserve or move it aside before downloading again.')
    return records
