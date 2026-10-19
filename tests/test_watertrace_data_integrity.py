"""Offline integrity and download recovery; all HTTP responses are local mocks."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sys

import httpx
import pytest

from scripts import fetch_watertrace_data as downloader
from scripts.verify_watertrace_data import main as verify_main
from watertrace.data_integrity import (IntegrityError, cache_path, fingerprint,
                                      load_manifest, recorded_objects, verify_dataset)


KEY = 'data/flood_events/HandLabeled/S1Hand/India_sample.tif'
RAW = b'original sample bytes'


def record(raw=RAW):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def manifest(root, split='demo', objects=None):
    value = {'dataset': 'Sen1Floods11 v1.1', 'split': split,
             'objects': objects if objects is not None else [{'key': KEY, **record()}]}
    path = root / (split + '-manifest.json')
    path.write_text(json.dumps(value))
    return path


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setattr(downloader, 'DATA', tmp_path)
    target = tmp_path / KEY
    target.parent.mkdir(parents=True)
    target.write_bytes(RAW)
    manifest(tmp_path)
    return tmp_path


def client(raw=RAW):
    return httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=raw)))


def test_offline_verification_does_not_change_files(cache, capsys):
    before = {p: p.read_bytes() for p in cache.rglob('*') if p.is_file()}
    assert verify_main(['--data', str(cache), '--split', 'demo']) == 0
    report = json.loads(capsys.readouterr().out)
    assert report['passed'] and report['checked'] == 1
    assert report['objects'] == [{'key': KEY, 'status': 'ok'}]
    assert 'not proof of upstream authenticity' in report['scope']
    assert before == {p: p.read_bytes() for p in cache.rglob('*') if p.is_file()}


@pytest.mark.parametrize('action,status', [('remove', 'missing'), ('edit', 'mismatch'), ('directory', 'unreadable_or_unsafe')])
def test_checker_distinguishes_missing_changed_and_unreadable(cache, capsys, action, status):
    target = cache / KEY
    target.unlink()
    if action == 'edit':
        target.write_bytes(b'X' + RAW[1:])  # Same size; hash must catch it.
        assert target.stat().st_size == len(RAW)
    elif action == 'directory':
        target.mkdir()
    assert verify_main(['--data', str(cache)]) == 1
    assert json.loads(capsys.readouterr().out)['objects'][0]['status'] == status


@pytest.mark.parametrize('key', ['../secret', '/secret', 'a/../secret', './secret', 'a//b', 'a\\b', 'C:/secret', '', None, 'a\x00b'])
def test_manifest_paths_cannot_escape_cache(tmp_path, key):
    manifest(tmp_path, objects=[{'key': key, **record()}])
    with pytest.raises(IntegrityError):
        load_manifest(tmp_path, 'demo')


@pytest.mark.parametrize('updates', [{'bytes': True}, {'bytes': -1}, {'bytes': 33*1024*1024}, {'sha256': 'bad'}, {'bytes': 0}])
def test_bad_manifest_records_rejected(tmp_path, updates):
    manifest(tmp_path, objects=[{'key': KEY, **record(), **updates}])
    with pytest.raises(IntegrityError):
        load_manifest(tmp_path, 'demo')


def test_missing_invalid_duplicate_and_conflicting_manifests(tmp_path, capsys):
    assert verify_main(['--data', str(tmp_path)]) == 2
    assert 'No files were changed' in capsys.readouterr().err
    path = manifest(tmp_path)
    path.write_text('{"split":"demo","split":"test"}')
    with pytest.raises(IntegrityError):
        load_manifest(tmp_path, 'demo')
    manifest(tmp_path, objects=[{'key': KEY, **record()}]*2)
    with pytest.raises(IntegrityError):
        load_manifest(tmp_path, 'demo')
    manifest(tmp_path)
    manifest(tmp_path, 'test', [{'key': KEY, **record(b'different')}])
    with pytest.raises(IntegrityError, match='Conflicting'):
        recorded_objects(tmp_path)


@pytest.mark.parametrize('mode', ['object', 'parent', 'manifest'])
def test_symlinks_are_not_followed(tmp_path, mode):
    root = tmp_path / 'cache'; root.mkdir()
    outside = tmp_path / 'private'; outside.write_bytes(RAW)
    manifest(root)
    if mode == 'manifest':
        (root/'demo-manifest.json').unlink()
        (root/'demo-manifest.json').symlink_to(outside)
    elif mode == 'parent':
        (root/'data').symlink_to(tmp_path, target_is_directory=True)
    else:
        target = root / KEY; target.parent.mkdir(parents=True)
        target.symlink_to(outside)
    with pytest.raises(IntegrityError, match='symlink'):
        load_manifest(root, 'demo')
    assert outside.read_bytes() == RAW


def test_fingerprint_has_a_hard_byte_limit(tmp_path, monkeypatch):
    target = tmp_path / 'large'; target.write_bytes(b'0123456789')
    monkeypatch.setattr('watertrace.data_integrity.MAX_OBJECT_BYTES', 5)
    with pytest.raises(IntegrityError, match='32 MiB'):
        fingerprint(target)


def test_known_cache_is_checked_offline_and_corruption_never_reblessed(cache):
    assert downloader.fetch(None, KEY, record()) == cache / KEY
    (cache / KEY).write_bytes(b'corrupt')
    before = (cache/'demo-manifest.json').read_bytes()
    with pytest.raises(IntegrityError, match='changed'):
        downloader.fetch(None, KEY, record())
    with pytest.raises(IntegrityError, match='failed integrity'):
        recorded_objects(cache)
    assert (cache/'demo-manifest.json').read_bytes() == before
    assert (cache / KEY).read_bytes() == b'corrupt'


def test_missing_objects_are_redownloadable_but_must_match_record(cache):
    (cache / KEY).unlink()
    assert recorded_objects(cache)[KEY] == record()
    with client(b'new upstream content') as remote, pytest.raises(IntegrityError, match='does not match'):
        downloader.fetch(remote, KEY, record())
    assert not (cache / KEY).exists()
    with client() as remote:
        downloader.fetch(remote, KEY, record())
    assert verify_dataset(cache, 'demo')['passed']
    assert not list(cache.rglob('.watertrace-*.tmp'))


def test_unrecorded_cache_requires_remote_match_and_never_overwrites(cache):
    with client() as remote:
        assert downloader.fetch(remote, KEY) == cache / KEY
    with client(b'different') as remote, pytest.raises(IntegrityError, match='Unrecorded cache'):
        downloader.fetch(remote, KEY)
    assert (cache / KEY).read_bytes() == RAW


def test_download_failure_leaves_no_partial_target(cache):
    (cache / KEY).unlink()
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(503))) as remote:
        with pytest.raises(httpx.HTTPStatusError):
            downloader.fetch(remote, KEY, record())
    assert not (cache / KEY).exists()
    assert not list(cache.rglob('.watertrace-*.tmp'))


def test_interrupted_stream_keeps_manifest_and_destination_untouched(cache):
    class Interrupted(httpx.SyncByteStream):
        def __iter__(self):
            yield b'partial'
            raise httpx.ReadError('Disconnected')
    (cache / KEY).unlink()
    before = (cache / 'demo-manifest.json').read_bytes()
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=Interrupted()))) as remote:
        with pytest.raises(httpx.ReadError):
            downloader.fetch(remote, KEY, record())
    assert not (cache / KEY).exists()
    assert (cache / 'demo-manifest.json').read_bytes() == before
    assert not list(cache.rglob('.watertrace-*.tmp'))


def test_competing_different_writer_is_never_overwritten(cache, monkeypatch):
    (cache / KEY).unlink()
    def competing_link(source, destination):
        Path(destination).write_bytes(b'other writer')
        raise FileExistsError()
    monkeypatch.setattr(downloader.os, 'link', competing_link)
    with client() as remote, pytest.raises(IntegrityError, match='Another writer'):
        downloader.fetch(remote, KEY, record())
    assert (cache / KEY).read_bytes() == b'other writer'
    assert not list(cache.rglob('.watertrace-*.tmp'))


def test_concurrent_identical_downloads_publish_one_complete_file(cache):
    (cache / KEY).unlink()
    with client() as remote, ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: downloader.fetch(remote, KEY, record()), range(2)))
    assert results == [cache / KEY, cache / KEY]
    assert (cache / KEY).read_bytes() == RAW
    assert not list(cache.rglob('.watertrace-*.tmp'))


def prepare_download(tmp_path, monkeypatch):
    monkeypatch.setattr(downloader, 'DATA', tmp_path)
    monkeypatch.setattr(sys, 'argv', ['fetch_watertrace_data.py', '--split', 'demo'])
    csv = '\n'.join(f'{country}_1_S1Hand.tif,{country}_1_LabelHand.tif' for country in ('Spain','India','USA')).encode()
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=csv if request.url.path.endswith('.csv') else RAW))
    remote = httpx.Client(transport=transport)
    monkeypatch.setattr(downloader.httpx, 'Client', lambda **kwargs: remote)


def test_full_downloader_writes_verifiable_manifest_and_records_split(tmp_path, monkeypatch):
    prepare_download(tmp_path, monkeypatch)
    downloader.main()
    report = verify_dataset(tmp_path, 'demo')
    assert report['passed'] and report['checked'] == 11
    assert 'splits/flood_handlabeled/flood_train_data.csv' in load_manifest(tmp_path, 'demo')
    assert not list(tmp_path.rglob('.watertrace-*.tmp'))


def test_manifest_publication_failure_preserves_previous_ledger(cache, monkeypatch):
    prepare_download(cache, monkeypatch)
    before = (cache / 'demo-manifest.json').read_bytes()
    def fail(*args):
        raise OSError('Simulated publication failure')
    monkeypatch.setattr(downloader.os, 'replace', fail)
    with pytest.raises(OSError):
        downloader.main()
    assert (cache / 'demo-manifest.json').read_bytes() == before
    assert not list(cache.rglob('.watertrace-*.tmp'))
