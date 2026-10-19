"""Renaming must reach runtime surfaces without changing scientific evidence."""
from pathlib import Path

from fastapi.testclient import TestClient

from watertrace import __version__
from watertrace.exports import geojson_export
from watertrace.lab import run_case
from watertrace.main import app


ROOT = Path(__file__).resolve().parents[1]


def test_http_branding_and_static_module_are_consistent():
    with TestClient(app) as client:
        html = client.get('/').text
        assert '<title>WaterTrace — Satellite evidence. Grounded decisions.</title>' in html
        assert 'aria-label="WaterTrace home"' in html
        assert 'FieldWatch' not in html
        assert 'Inundra' not in html
        assert client.get('/openapi.json').json()['info']['title'] == 'WaterTrace'
        assert client.get('/api/health').json()['version'] == __version__
        assert 'root.WaterTraceModel=api' in client.get('/static/model.js').text
        assert 'window.WaterTraceModel' in client.get('/static/app.js').text


def test_report_and_geographic_metadata_use_versioned_new_identity():
    report = run_case('missing-earlier')
    assert report['engine']['name'] == 'WaterTrace'
    assert report['engine']['policy'] == 'surface-water-screen-v1'
    exported = geojson_export(report)
    assert 'fieldwatch' not in exported
    assert 'inundra' not in exported
    assert exported['watertrace']['schema_version'] == 'geojson-review-v3'
    assert exported['watertrace']['engine'] == report['engine']


def test_renamed_runtime_entrypoints_and_container_references_exist():
    for file in ('watertrace/main.py', 'watertrace/cli.py', 'scripts/check_watertrace_lab.py',
                 'scripts/fetch_watertrace_data.py', 'scripts/evaluate_watertrace.py',
                 'scripts/smoke_watertrace.py', 'tests/watertrace.test.cjs',
                 'docs/benchmarks/watertrace-v1.json'):
        assert (ROOT / file).is_file()
    docker = (ROOT / 'Dockerfile').read_text()
    assert 'COPY watertrace ./watertrace' in docker
    assert 'watertrace.main:app' in docker
    assert 'WATERTRACE_DATA=/data' in docker
    workflow = (ROOT / '.github/workflows/verify.yml').read_text()
    assert 'name: Verify WaterTrace' in workflow
    assert 'scripts/check_watertrace_lab.py' in workflow
    assert 'fieldwatch' not in workflow.lower()
