import httpx
import numpy as np
import pytest

from watertrace.pair_search import asset_url, plan_pair
from scripts.prepare_watertrace_pair import linear_to_db, search, save_bytes


def item(identifier='before', day='02'):
    transform = [.0002, 0, 34, 0, -.0002, -19]
    return {'id': identifier, 'collection': 's1_rtc', 'properties': {
        'datetime': f'2019-03-{day}T03:08:40Z', 'platform': 'sentinel-1a',
        'sat:relative_orbit': 6, 'sat:orbit_state': 'descending', 'sar:instrument_mode': 'IW',
        'sar:polarizations': ['VV', 'VH'], 'proj:epsg': 4326,
        'proj:shape': [5000, 5000], 'proj:transform': transform,
    }, 'assets': {band: {
        'href': f's3://deafrica-sentinel-1/s1_rtc/S20E034/2019/03/{day}/02EB31/s1_rtc_02EB31_S20E034_2019_03_{day}_{band.upper()}.tif',
        'proj:shape': [5000, 5000], 'proj:transform': transform,
        'raster:bands': [{'unit': '1'}],
    } for band in ('vv', 'vh', 'mask')}}


def test_cutoff_excludes_already_affected_nearest_observation():
    result = plan_pair([item(), item('nearer', '14'), item('current', '26')], 'current', '2019-03-09')
    assert result['selected_id'] == 'before'
    assert result['next_action'] == 'request_download_approval'
    assert result['trace'][1]['reason'] == 'not_before_baseline_cutoff'


@pytest.mark.parametrize('key,value', [
    ('sat:relative_orbit', 174), ('sat:orbit_state', 'ascending'), ('platform', 'sentinel-1b'),
    ('sar:polarizations', ['VV']), ('sar:instrument_mode', None), ('proj:epsg', 3857),
    ('proj:transform', [.0002, 0, 35, 0, -.0002, -19]),
    ('proj:shape', [4000, 5000]), ('datetime', '2019-03-02T03:08:40'),
])
def test_incompatible_or_missing_metadata_abstains(key, value):
    earlier = item()
    earlier['properties'][key] = value
    result = plan_pair([earlier, item('current', '26')], 'current', '2019-03-09')
    assert result['selected_id'] is None
    assert result['next_action'] == 'request_different_search_window'


@pytest.mark.parametrize('href', ['file:///etc/passwd', 'https://localhost/test.tif',
    's3://deafrica-sentinel-1/../../x', 's3://other/s1_rtc/a',
    item()['assets']['vv']['href'] + '?token=secret', item()['assets']['vv']['href'] + '\n'])
def test_asset_allowlist(href):
    with pytest.raises(ValueError):
        asset_url(href)


def test_mixed_acquisition_assets_and_unknown_units_are_rejected():
    earlier = item()
    earlier['assets']['vh'] = item(day='14')['assets']['vh']
    result = plan_pair([earlier, item('current', '26')], 'current', '2019-03-09')
    assert result['selected_id'] is None
    earlier = item()
    earlier['assets']['vv']['raster:bands'][0]['unit'] = 'dB'
    assert plan_pair([earlier, item('current', '26')], 'current', '2019-03-09')['selected_id'] is None


def test_duplicates_and_bad_current_fail_closed():
    with pytest.raises(ValueError):
        plan_pair([item(), item()], 'before', '2019-03-01')
    with pytest.raises(ValueError):
        plan_pair([item()], 'absent', '2019-03-01')
    bad = item('current', '26');del bad['properties']['sat:relative_orbit']
    with pytest.raises(ValueError):
        plan_pair([item(), bad], 'current', '2019-03-09')


@pytest.mark.parametrize('bad_value', [None, [], {'vv': None}, {'vv': {'raster:bands': []}}])
def test_malformed_assets_abstain(bad_value):
    before = item();before['assets'] = bad_value
    assert plan_pair([before, item('current', '26')], 'current', '2019-03-09')['selected_id'] is None


def test_linear_conversion_preserves_quality_mask_and_invalid_values():
    vv = np.array([[.01, .1, 0, -1, np.nan, np.inf, .01, .01]], np.float32)
    vh = np.full(vv.shape, .001, np.float32)
    mask = np.array([[1, 1, 1, 1, 1, 1, 0, 2]], np.uint8)
    converted = linear_to_db(vv, vh, mask)
    np.testing.assert_allclose(converted[:, 0, :2], [[-20, -10], [-30, -30]], atol=1e-5)
    assert np.all(converted[:, :, 2:] == -9999)
    with pytest.raises(ValueError):
        linear_to_db(vv, vh[:, :2], mask)


@pytest.mark.parametrize('kind', ['truncated', 'oversized', 'http_error', 'success'])
def test_bounded_catalog(kind):
    def respond(request):
        assert request.url.host == 'explorer.digitalearth.africa'
        if kind == 'oversized':
            return httpx.Response(200, content=b' ' * (4 * 1024 * 1024 + 1))
        if kind == 'http_error':
            return httpx.Response(503)
        return httpx.Response(200, json={'features': [item()], 'links': [{'rel': 'next', 'href': 'http://localhost'}] if kind == 'truncated' else []})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        if kind == 'success':
            assert search(client)[0]['id'] == 'before'
        else:
            with pytest.raises((ValueError, httpx.HTTPError)):
                search(client)


def test_crop_publication_never_overwrites_and_is_private(tmp_path):
    output = tmp_path / 'crop.tif'
    save_bytes(output, b'first')
    assert output.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        save_bytes(output, b'second')
    assert output.read_bytes() == b'first'
    assert list(tmp_path.iterdir()) == [output]


def test_default_cli_only_plans_without_raster_reads_or_files(monkeypatch, tmp_path):
    from scripts import prepare_watertrace_pair as cli
    monkeypatch.setattr(cli, 'search', lambda client: [item(), item(cli.CURRENT, '26')])
    monkeypatch.setattr(cli, 'crop', lambda *args: pytest.fail('No approval: must not fetch imagery'))
    output = tmp_path / 'pair'
    assert cli.main(['--output', str(output)]) == 0
    assert not output.exists()


def test_actual_crop_conversion_checks_headers_and_preserves_provider_mask(monkeypatch):
    from scripts import prepare_watertrace_pair as cli
    from watertrace.engine import read_raster
    class Source:
        count = 1
        shape = (5000, 5000)
        crs = cli.rasterio.crs.CRS.from_epsg(4326)
        transform = cli.Affine(.0002, 0, 34, 0, -.0002, -19)
        def __init__(self, url):
            self.url = url
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def window_transform(self, window):
            return self.transform @ cli.Affine.translation(window.col_off, window.row_off)
        def read(self, band, *, window, masked):
            assert window == cli.WINDOW and masked
            values = np.full((512, 512), 1 if '_MASK' in self.url else .01, np.float32)
            if '_MASK' in self.url:
                values[0, :10] = 2
            return np.ma.array(values, mask=False)
    monkeypatch.setattr(cli.rasterio, 'open', Source)
    raw, meta = cli.crop(item())
    result = read_raster(raw)
    assert not result.valid[0, :10].any()
    assert result.valid[1:].all()
    assert result.bands[0, 10, 10] == pytest.approx(-20)
    assert meta['sha256'] == result.sha256
    assert meta['window_col_row_width_height'] == [3500, 3500, 512, 512]
    Source.shape = (5000, 4000)
    with pytest.raises(ValueError, match='header'):
        cli.crop(item())
