import hashlib
import json

import pytest

from scripts import prepare_watertrace_pair as cli
from test_watertrace import tif
from watertrace.service import export_report, run_analysis


@pytest.fixture
def prepared(tmp_path):
    raw = tif()
    for role in ('current', 'earlier'):
        (tmp_path / (role + '.tif')).write_bytes(raw)
    report = export_report(run_analysis(raw, name='Beira historical pair — unvalidated change',
                           observed_on='2019-03-26', reference_raw=raw,
                           reference_on='2019-03-02', same_orbit=True))
    manifest = {'case': 'beira-2019-pipeline-case'}
    for role, day in (('current', '26'), ('earlier', '02')):
        manifest[role] = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
                          'properties': {'datetime': f'2019-03-{day}T03:08:40Z'}}
    (tmp_path / 'provenance.json').write_text(json.dumps(manifest))
    (tmp_path / 'report.json').write_text(json.dumps(report))
    return tmp_path


def test_offline_verification_replays_all_evidence_without_writing(prepared, monkeypatch):
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in prepared.iterdir()}
    monkeypatch.setattr(cli, 'search', lambda *args: pytest.fail('Verification must be offline'))
    monkeypatch.setattr(cli.httpx, 'Client', lambda *args, **kwargs: pytest.fail('No network client'))
    assert cli.main(['--verify', '--output', str(prepared)]) == 0
    assert {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in prepared.iterdir()} == before


@pytest.mark.parametrize('role', ['current', 'earlier'])
def test_corrupt_crop_is_not_silently_repaired(prepared, role):
    path = prepared / (role + '.tif')
    path.write_bytes(b'corrupted')
    result = cli.verify_pair(prepared)
    assert not result['passed'] and result['report'] == 'not_checked'
    assert next(x for x in result['objects'] if x['key'] == path.name)['status'] == 'mismatch'
    assert path.read_bytes() == b'corrupted'


def test_missing_crop_is_reported_without_download(prepared):
    (prepared / 'earlier.tif').unlink()
    result = cli.verify_pair(prepared)
    assert not result['passed'] and result['objects'][1]['status'] == 'missing'


@pytest.mark.parametrize('target', ['current.tif', 'provenance.json', 'report.json'])
def test_symlink_inputs_are_rejected(prepared, target):
    path = prepared / target
    moved = prepared / ('original-' + target)
    path.rename(moved);path.symlink_to(moved)
    assert cli.main(['--verify', '--output', str(prepared)]) in (1, 2)


@pytest.mark.parametrize('field', ['measurement', 'date', 'policy', 'extra'])
def test_changed_report_is_detected_without_repair(prepared, field):
    path = prepared / 'report.json'
    report = json.loads(path.read_text())
    if field == 'measurement':
        report['summary']['water_observed_ha'] += 1
    elif field == 'date':
        report['source']['observed_on'] = '2019-03-25'
    elif field == 'policy':
        report['engine']['policy'] = 'another-model'
    else:
        report['extra_unverified_evidence'] = True
    path.write_text(json.dumps(report));before = path.read_bytes()
    result = cli.verify_pair(prepared)
    assert not result['passed'] and result['report'] == 'mismatch'
    assert path.read_bytes() == before


def test_runtime_timing_changes_are_not_evidence_mismatches(prepared):
    path = prepared / 'report.json'
    report = json.loads(path.read_text())
    report['generated_at'] = 'another run';report['elapsed_ms'] = 999
    path.write_text(json.dumps(report))
    assert cli.verify_pair(prepared)['passed']


@pytest.mark.parametrize('content', ['{}', '[]', '{"case":1,"case":2}', '{"x":NaN}',
    '[' * 2000 + '0' + ']' * 2000, ' ' * (4 * 1024 * 1024 + 1)])
def test_malformed_or_oversized_manifest_is_bounded(prepared, content):
    (prepared / 'provenance.json').write_text(content)
    assert cli.main(['--verify', '--output', str(prepared)]) == 2


def test_verify_and_download_flags_are_mutually_exclusive():
    with pytest.raises(SystemExit) as exc:
        cli.main(['--verify', '--approve-download'])
    assert exc.value.code == 2


def test_crop_changed_after_fingerprinting_is_rejected(prepared, monkeypatch):
    original = cli.inspect_object
    def inspect_then_change(root, key, expected):
        result = original(root, key, expected)
        if key == 'current.tif':
            (root / key).write_bytes(b'changed after hashing')
        return result
    monkeypatch.setattr(cli, 'inspect_object', inspect_then_change)
    with pytest.raises(ValueError, match='changed while'):
        cli.verify_pair(prepared)


@pytest.mark.parametrize('size,digest', [(True, 'a' * 64), (0, 'a' * 64),
    (cli.MAX_BYTES + 1, 'a' * 64), (10, '../not-a-digest'), (10, None)])
def test_invalid_fingerprints_fail_before_raster_reads(prepared, size, digest):
    path = prepared / 'provenance.json'
    manifest = json.loads(path.read_text())
    manifest['current'].update(bytes=size, sha256=digest)
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='fingerprint'):
        cli.verify_pair(prepared)
