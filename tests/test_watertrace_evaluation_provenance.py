import hashlib
import json

import numpy as np
import pytest
from rasterio.io import MemoryFile

from scripts import evaluate_watertrace as evaluator
from test_watertrace import tif
from watertrace import cli


@pytest.fixture
def evaluation_data(tmp_path):
    base = tmp_path / 'data/flood_events/HandLabeled'
    image, label = base / 'S1Hand/Event_1.tif', base / 'LabelHand/Event_1.tif'
    image.parent.mkdir(parents=True)
    label.parent.mkdir(parents=True)
    image.write_bytes(tif())
    with MemoryFile(image.read_bytes()) as memory, memory.open() as src:
        profile = src.profile
        shape = src.shape
    profile.update(count=1, dtype='int16', nodata=-1)
    with MemoryFile() as memory:
        with memory.open(**profile) as dst:
            dst.write(np.zeros(shape, dtype=np.int16), 1)
        label.write_bytes(memory.read())
    manifest = tmp_path / 'test-manifest.json'
    manifest.write_text(json.dumps({'pairs': [[image.name, label.name]]}))
    return tmp_path, image, label, manifest


def test_evaluation_hashes_exact_decoded_bytes_and_records_runtime(evaluation_data, monkeypatch):
    root, image, label, manifest = evaluation_data
    original = {p: p.read_bytes() for p in (image, label, manifest)}
    original_memory = evaluator.MemoryFile

    def change_disk_after_read(raw):
        # Mutate both disk rasters after evaluator has loaded them. The report
        # must describe the retained bytes, not hash or decode a later version.
        image.write_bytes(b'changed after read')
        label.write_bytes(b'changed after read')
        manifest.write_text('{"pairs":[]}')
        return original_memory(raw)

    monkeypatch.setattr(evaluator, 'MemoryFile', change_disk_after_read)
    report = evaluator.evaluate(root, 'test', experiments=True)
    row = report['cases'][0]
    assert row['sha256'] == hashlib.sha256(original[image]).hexdigest()
    assert row['label_sha256'] == hashlib.sha256(original[label]).hexdigest()
    assert row['label'] == label.name
    assert report['manifest_sha256'] == hashlib.sha256(original[manifest]).hexdigest()
    assert row['watertrace']['labeled'] > 0
    assert set(report['runtime']) == {'python', 'opencv', 'numpy', 'rasterio', 'gdal'}
    assert all(isinstance(value, str) and value for value in report['runtime'].values())


def test_empty_evaluation_is_explicit_error(tmp_path):
    (tmp_path / 'test-manifest.json').write_text('{"pairs":[]}')
    with pytest.raises(ValueError, match='at least one'):
        evaluator.evaluate(tmp_path, 'test')


@pytest.mark.parametrize('existing', ['file', 'dangling_symlink'])
def test_evaluation_cli_never_replaces_prior_output(tmp_path, monkeypatch, existing):
    output = tmp_path / 'report.json'
    if existing == 'file':
        output.write_text('prior evidence')
    else:
        output.symlink_to(tmp_path / 'missing.json')
    monkeypatch.setattr(evaluator, 'evaluate', lambda *a, **kw: {'cases': [], 'policy': 'test'})
    with pytest.raises(SystemExit) as error:
        evaluator.main(['--output', str(output)])
    assert error.value.code == 2
    if existing == 'file':
        assert output.read_text() == 'prior evidence'
    else:
        assert output.is_symlink() and not (tmp_path / 'missing.json').exists()
    assert not list(tmp_path.glob('.watertrace-*.tmp'))


def test_evaluation_publication_failure_leaves_no_partial_report(tmp_path, monkeypatch):
    output = tmp_path / 'report.json'
    monkeypatch.setattr(evaluator, 'evaluate', lambda *a, **kw: {'cases': [], 'policy': 'test'})

    def fail_link(*args):
        raise OSError('simulated publication failure')

    monkeypatch.setattr(cli.os, 'link', fail_link)
    with pytest.raises(SystemExit) as error:
        evaluator.main(['--output', str(output)])
    assert error.value.code == 2
    assert not output.exists()
    assert not list(tmp_path.glob('.watertrace-*.tmp'))


def test_evaluation_cli_writes_private_complete_json(tmp_path, monkeypatch):
    output = tmp_path / 'report.json'
    monkeypatch.setattr(evaluator, 'evaluate', lambda *a, **kw: {'cases': [], 'policy': 'test'})
    evaluator.main(['--output', str(output)])
    assert json.loads(output.read_text()) == {'cases': [], 'policy': 'test'}
    assert output.stat().st_mode & 0o777 == 0o600
    assert not list(tmp_path.glob('.watertrace-*.tmp'))
