"""Unknown earlier evidence must not masquerade as zero water change."""
from copy import deepcopy
import itertools
import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from fieldwatch.decisions import review_decision
from fieldwatch.engine import temporal_summary
from fieldwatch.exports import geojson_export
from fieldwatch.lab import encode, run_case, synthetic_inputs
from fieldwatch.main import app
from fieldwatch.service import run_analysis


@pytest.mark.parametrize('current,earlier', itertools.product(range(3), repeat=2))
def test_every_pair_state_has_explicit_support(current, earlier):
    result = temporal_summary(np.array([[current]]), np.array([[earlier]]), np.array([[2.5]]))
    assessed = current != 0 and earlier != 0
    assert result['paired_assessed_ha'] == (2.5 if assessed else 0)
    assert result['paired_uncertain_ha'] == (0 if assessed else 2.5)
    assert result['paired_assessed_fraction'] == int(assessed)
    assert result['water_without_baseline_ha'] == (2.5 if current == 2 and earlier == 0 else 0)
    assert result['observed_water_baseline_complete'] is (earlier != 0 if current == 2 else None)
    assert result['observed_water_baseline_fraction'] == (int(earlier != 0) if current == 2 else None)


def test_weighted_area_and_selected_mask_not_pixel_counts():
    current = np.array([[2, 2, 2, 0, 1]])
    earlier = np.array([[0, 1, 2, 1, 0]])
    area = np.array([[1., 3., 6., 10., 20.]])
    result = temporal_summary(current, earlier, area)
    assert result['paired_assessed_ha'] == 9
    assert result['paired_uncertain_ha'] == 31
    assert result['paired_assessed_fraction'] == .225
    assert result['observed_water_baseline_fraction'] == .9
    assert result['observed_water_baseline_complete'] is False
    selected = temporal_summary(current, earlier, area, np.array([[False, True, True, False, False]]))
    assert selected['paired_assessed_ha'] == 9
    assert selected['paired_assessed_fraction'] == 1
    assert selected['water_without_baseline_ha'] == 0
    assert selected['observed_water_baseline_complete'] is True


def test_unpaired_is_unavailable_not_zero():
    raw, _ = synthetic_inputs('new-water')
    report = run_analysis(raw)
    assert report['temporal_support'] is None
    assert all(z['temporal_support'] is None for z in report['zones'])
    exported = geojson_export(report)
    assert exported['fieldwatch']['temporal_support'] is None
    for feature in exported['features']:
        for key in ('water_without_baseline_ha', 'paired_assessed_fraction', 'observed_water_baseline_complete'):
            assert feature['properties'][key] is None


def center(report):
    return next(z for z in report['zones'] if z['id'] == 'sector-5')


def test_missing_baseline_keeps_current_coverage_but_withholds_change_interpretation():
    report = run_case('missing-earlier')
    zone = center(report)
    support = zone['temporal_support']
    assert zone['coverage'] == 1
    assert support['paired_assessed_fraction'] == 0
    assert support['water_without_baseline_ha'] == zone['water_observed_ha'] > 0
    assert zone['new_water_candidate_ha'] == zone['repeat_water_observed_ha'] == 0
    assert zone['decision']['level'] == 'baseline_required'
    assert zone['decision']['policy'] == 'review-gates-v3'
    assert any('unknown earlier state' in reason for reason in zone['decision']['reasons'])
    assert any(step['action'] == 'account_for_paired_support' for step in report['trace'])


@pytest.mark.parametrize('identifier', ['new-water', 'repeat-water', 'missing-earlier'])
def test_pipeline_accounting_partitions_current_water_and_scene_overlap(identifier):
    report = run_case(identifier)
    support = report['temporal_support']
    assert support['paired_assessed_ha'] + support['paired_uncertain_ha'] == pytest.approx(report['summary']['scene_area_ha'], abs=.0011)
    for zone in report['zones']:
        support = zone['temporal_support']
        assert zone['new_water_candidate_ha'] + zone['repeat_water_observed_ha'] + support['water_without_baseline_ha'] == pytest.approx(zone['water_observed_ha'], abs=.0016)
        assert support['paired_assessed_ha'] + support['paired_uncertain_ha'] == pytest.approx(zone['area_ha'], abs=.0011)
    json.dumps(report, allow_nan=False)


def test_mixed_baseline_preserves_partial_new_repeat_and_unknown_measurements():
    raw, options = synthetic_inputs('new-water')
    earlier = np.empty((2, 96, 96), np.float32)
    earlier[0] = -7; earlier[1] = -13
    earlier[:, :, :40] = -9999
    earlier[0, :, 50:] = -29; earlier[1, :, 50:] = -35
    options['reference_raw'] = encode(earlier)
    report = run_analysis(raw, **options)
    zone = center(report)
    assert zone['new_water_candidate_ha'] > 0
    assert zone['repeat_water_observed_ha'] > 0
    assert zone['temporal_support']['water_without_baseline_ha'] > 0
    assert 0 < zone['temporal_support']['observed_water_baseline_fraction'] < 1
    assert zone['decision']['level'] == 'baseline_required'
    exported = geojson_export(report, {'sector-5': {'outcome': 'water_confirmed'}})
    feature = next(f for f in exported['features'] if f['id'] == 'sector-5')
    assert feature['properties']['review_gate'] == 'baseline_required'
    assert feature['properties']['human_outcome'] == 'water_confirmed'


def test_tiny_missing_baseline_cannot_be_rounded_into_completeness():
    zone = deepcopy(center(run_case('repeat-water')))
    support = temporal_summary(np.array([[2, 2]]), np.array([[2, 0]]), np.array([[100., .000001]]))
    assert support['water_without_baseline_ha'] == 0
    assert support['observed_water_baseline_fraction'] == support['paired_assessed_fraction'] == 1
    assert support['observed_water_baseline_complete'] is False
    zone['temporal_support'] = support
    assert review_decision(zone, True)['level'] == 'baseline_required'


@pytest.mark.parametrize('change,expected', [
    ({'pixels': 4}, 'insufficient_evidence'),
    ({'coverage': .1}, 'insufficient_evidence'),
    ({'spatial_support': {'scene_clipped': True}}, 'insufficient_evidence'),
    ({'crop': 'rice'}, 'context_required'),
    ({'crop': 'paddy'}, 'context_required'),
])
def test_stronger_review_gates_keep_missing_baseline_reason(change, expected):
    zone = center(run_case('missing-earlier'))
    zone.update(change)
    decision = review_decision(zone, True)
    assert decision['level'] == expected
    assert any('unknown earlier state' in reason for reason in decision['reasons'])


def test_http_lab_report_exposes_temporal_accounting():
    with TestClient(app) as client:
        response = client.post('/api/lab/missing-earlier/run')
    assert response.status_code == 200
    report = response.json()
    assert report['temporal_support']['water_without_baseline_ha'] > 0
    assert center(report)['decision']['level'] == 'baseline_required'
