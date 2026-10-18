"""Renaming must reach runtime surfaces without changing scientific evidence."""
from pathlib import Path

from fastapi.testclient import TestClient

from inundra import __version__
from inundra.exports import geojson_export
from inundra.lab import run_case
from inundra.main import app


ROOT = Path(__file__).resolve().parents[1]


def test_http_branding_and_static_module_are_consistent():
    with TestClient(app) as client:
        html = client.get('/').text
        assert '<title>Inundra — Satellite evidence. Grounded decisions.</title>' in html
        assert 'aria-label="Inundra home"' in html
        assert 'FieldWatch' not in html
        assert client.get('/openapi.json').json()['info']['title'] == 'Inundra'
        assert client.get('/api/health').json()['version'] == __version__ == '0.8.0'
        assert 'root.InundraModel=api' in client.get('/static/model.js').text
        assert 'window.InundraModel' in client.get('/static/app.js').text


def test_report_and_geographic_metadata_use_versioned_new_identity():
    report = run_case('missing-earlier')
    assert report['engine']['name'] == 'Inundra'
    assert report['engine']['policy'] == 'surface-water-screen-v1'
    exported = geojson_export(report)
    assert 'fieldwatch' not in exported
    assert exported['inundra']['schema_version'] == 'geojson-review-v2'
    assert exported['inundra']['engine'] == report['engine']


def test_renamed_runtime_entrypoints_and_container_references_exist():
    for file in ('inundra/main.py', 'inundra/cli.py', 'scripts/check_inundra_lab.py',
                 'scripts/fetch_inundra_data.py', 'scripts/evaluate_inundra.py',
                 'scripts/smoke_inundra.py', 'tests/inundra.test.cjs',
                 'docs/benchmarks/inundra-v1.json'):
        assert (ROOT / file).is_file()
    docker = (ROOT / 'Dockerfile').read_text()
    assert 'COPY inundra ./inundra' in docker
    assert 'inundra.main:app' in docker
    assert 'INUNDRA_DATA=/data' in docker
    workflow = (ROOT / '.github/workflows/verify.yml').read_text()
    assert 'name: Verify Inundra' in workflow
    assert 'scripts/check_inundra_lab.py' in workflow
    assert 'fieldwatch' not in workflow.lower()
