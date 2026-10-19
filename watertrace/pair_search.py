"""Conservative metadata-only baseline planning for Digital Earth Africa RTC.

Never establishes a dry baseline or fetches imagery. Missing metadata fails closed.
"""
from datetime import date, datetime
import re


ASSET = re.compile(r's3://deafrica-sentinel-1/s1_rtc/[NS]\d{2}[EW]\d{3}/\d{4}/\d{2}/\d{2}/[A-F0-9]+/s1_rtc_[A-F0-9]+_[NS]\d{2}[EW]\d{3}_\d{4}_\d{2}_\d{2}_(VV|VH|MASK)\.tif')


def asset_url(href):
    if not isinstance(href, str) or not ASSET.fullmatch(href):
        raise ValueError('Only canonical Digital Earth Africa RTC assets are supported.')
    return href.replace('s3://deafrica-sentinel-1/', 'https://deafrica-sentinel-1.s3.af-south-1.amazonaws.com/', 1)


def signature(item):
    try:
        return _signature(item)
    except (KeyError, TypeError, IndexError, AttributeError, ValueError):
        raise ValueError('Required acquisition metadata is malformed or unsupported.') from None


def _signature(item):
    p = item['properties']
    required = ['platform', 'sat:relative_orbit', 'sat:orbit_state', 'sar:instrument_mode',
                'sar:polarizations', 'proj:epsg', 'proj:shape', 'proj:transform']
    # STAC 1.1 uses proj:code instead of proj:epsg.
    p = dict(p)
    if 'proj:epsg' not in p and p.get('proj:code') == 'EPSG:4326':
        p['proj:epsg'] = 4326
    if item.get('collection') != 's1_rtc' or any(p.get(k) is None for k in required):
        raise ValueError('Required matching metadata is absent.')
    if (p['platform'] not in ('sentinel-1a', 'sentinel-1b') or
            type(p['sat:relative_orbit']) is not int or not 1 <= p['sat:relative_orbit'] <= 175 or
            p['sat:orbit_state'] not in ('ascending', 'descending') or
            p['sar:instrument_mode'] != 'IW' or sorted(p['sar:polarizations']) != ['VH', 'VV'] or
            p['proj:epsg'] != 4326 or p['proj:shape'] != [5000, 5000]):
        raise ValueError('Unsupported acquisition or grid metadata.')
    transform = p['proj:transform']
    if (not isinstance(transform, list) or len(transform) != 6 or
            transform[0] != .0002 or transform[1] != 0 or transform[3] != 0 or transform[4] != -.0002 or
            type(transform[2]) not in (int, float) or not -180 <= transform[2] <= 179 or
            type(transform[5]) not in (int, float) or not -89 <= transform[5] <= 90):
        raise ValueError('Unsupported raster grid.')
    for band in ('vv', 'vh', 'mask'):
        asset = item['assets'][band]
        asset_url(asset['href'])
        if not asset['href'].endswith('_' + band.upper() + '.tif'):
            raise ValueError('Asset polarization mismatch.')
        if asset.get('proj:shape') != p['proj:shape'] or asset.get('proj:transform') != transform:
            raise ValueError('Asset grid differs from item grid.')
        if asset['href'].rsplit('_', 1)[0] != item['assets']['vv']['href'].rsplit('_', 1)[0]:
            raise ValueError('Assets come from different acquisitions.')
        if band != 'mask' and asset.get('raster:bands', [{}])[0].get('unit') != '1':
            raise ValueError('Expected linear power units.')
    return tuple(str(sorted(p[k])) if k == 'sar:polarizations' else str(p[k]) for k in required)


def timestamp(item):
    value = item['properties']['datetime']
    if not isinstance(value, str):
        raise ValueError('Acquisition time must be a string.')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Acquisition time needs a timezone.')
    return result


def plan_pair(items, current_id, baseline_before):
    """Choose nearest matching observation strictly before an explicit event cutoff."""
    cutoff = date.fromisoformat(baseline_before)
    if not isinstance(items, list) or not 1 <= len(items) <= 100:
        raise ValueError('Expected 1–100 catalog items.')
    ids = [i.get('id') for i in items if isinstance(i, dict)]
    if len(ids) != len(items) or any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids):
        raise ValueError('Catalog item IDs must be present and unique.')
    matches = [i for i in items if i['id'] == current_id]
    if len(matches) != 1:
        raise ValueError('Current item not found in bounded search.')
    current = matches[0]
    try:
        key, acquired = signature(current), timestamp(current)
    except (KeyError, TypeError, ValueError):
        raise ValueError('Current acquisition metadata is unsupported or incomplete.') from None
    if cutoff > acquired.date():
        raise ValueError('Baseline cutoff must not follow the current acquisition.')
    eligible, trace = [], []
    for item in items:
        if item['id'] == current_id:
            continue
        try:
            when = timestamp(item)
            if when >= acquired or when.date() >= cutoff:
                reason = 'not_before_baseline_cutoff'
            elif signature(item) != key:
                reason = 'acquisition_or_grid_mismatch'
            else:
                reason = 'eligible_metadata_only'
                eligible.append(item)
        except (KeyError, TypeError, ValueError):
            reason = 'missing_or_unsupported_metadata'
        trace.append({'id': item['id'], 'reason': reason})
    eligible.sort(key=lambda i: (timestamp(i), i['id']), reverse=True)
    selected = eligible[0] if eligible else None
    return {'policy': 'deafrica-baseline-search-v1', 'current_id': current_id,
            'baseline_before': baseline_before, 'selected_id': selected['id'] if selected else None,
            'eligible_ids': [i['id'] for i in eligible], 'trace': trace,
            'next_action': 'request_download_approval' if selected else 'request_different_search_window',
            'limitations': ['Metadata match is not independent geolocation or calibration validation.',
                           'Earlier does not mean dry; prior floods and permanent water remain possible.',
                           'No imagery downloaded by this planner. No autonomous intervention.']}
