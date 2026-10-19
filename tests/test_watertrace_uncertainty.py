import importlib.util
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[1] / 'scripts/audit_watertrace_uncertainty.py'
spec = importlib.util.spec_from_file_location('uncertainty_audit', PATH)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def counts(**changes):
    result = dict(tp=3, fp=1, fn=2, tn=4, labeled=10, assessed=7, unknown_water=1)
    result.update(changes)
    return result


def case(event, image, values=None):
    return dict(event=event, image=image, **{m: dict(values or counts()) for m in audit.METHODS})


def test_selective_error_keeps_abstentions_out_but_full_recall_keeps_misses():
    result = audit.scores(counts())
    assert result['selective_error'] == 2 / 7
    assert result['recall'] == 3 / 5
    assert result['coverage'] == .7
    assert result['water_abstention_fraction'] == .2


def test_all_abstaining_is_not_perfect_accuracy():
    result = audit.scores(counts(tp=0, fp=0, fn=5, tn=5, assessed=0, unknown_water=5))
    assert result['selective_error'] is None
    assert result['coverage'] == 0 and result['recall'] == 0
    assert result['precision'] is None


@pytest.mark.parametrize('changes', [dict(tp=True), dict(fp=-1), dict(labeled=11),
    dict(assessed=11), dict(unknown_water=3), dict(assessed=1), dict(assessed=10)])
def test_invalid_counts_rejected(changes):
    with pytest.raises(ValueError):
        audit.scores(counts(**changes))


def test_bootstrap_reproducible_and_groups_all_chips_by_event():
    report = {'cases': [case('A', 'a'), case('A', 'b'), case('B', 'c')]}
    first = audit.audit(report, replicates=30)
    assert first == audit.audit(report, replicates=30)
    assert first['events'] == 2 and first['chips'] == 3
    assert first['intervals']['watertrace']['coverage']['percentile_95'] == [.7, .7]
    assert first['pooled']['watertrace'] == audit.scores(counts())


def test_single_event_has_no_interval_and_undefined_replicates_are_counted():
    zero = dict.fromkeys(audit.KEYS, 0)
    result = audit.audit({'cases': [case('A', 'a', zero)]}, replicates=10)
    assert result['intervals']['watertrace']['coverage'] == {
        'percentile_95': None, 'defined_replicates': 0}


@pytest.mark.parametrize('cases', [[], [case('A', 'a'), case('A', 'a')], [case('', 'b')]])
def test_missing_or_duplicate_cases_rejected(cases):
    with pytest.raises(ValueError):
        audit.audit({'cases': cases}, replicates=2)


def test_mismatched_method_denominators_rejected():
    row = case('A', 'a')
    row['vh_otsu'] = counts(tn=5, labeled=11)
    with pytest.raises(ValueError, match='denominators'):
        audit.audit({'cases': [row]}, replicates=2)


def test_event_resampling_retains_differently_sized_groups():
    import numpy as np
    perfect = counts(tp=5, fp=0, fn=0, tn=5, assessed=10, unknown_water=0)
    wrong = counts(tp=0, fp=5, fn=5, tn=0, assessed=10, unknown_water=0)
    report = {'cases': [case('A', 'a', perfect), case('A', 'b', perfect), case('B', 'c', wrong)]}
    result = audit.audit(report, replicates=200)
    draws = np.random.default_rng(20261019).integers(0, 2, size=(200, 2))
    expected = []
    for draw in draws:
        good = int((draw == 0).sum()) * 20
        bad = int((draw == 1).sum()) * 10
        expected.append(bad / (good + bad))
    assert result['pooled']['watertrace']['selective_error'] == 1 / 3
    assert result['intervals']['watertrace']['selective_error']['percentile_95'] == np.quantile(expected, [.025, .975]).tolist()


def test_cli_refuses_to_overwrite_prior_evidence(tmp_path):
    import json
    import subprocess
    import sys
    source, target = tmp_path / 'report.json', tmp_path / 'audit.json'
    source.write_text(json.dumps({'cases': [case('A', 'a'), case('B', 'b')]}))
    target.write_text('previous evidence')
    run = subprocess.run([sys.executable, str(PATH), str(source), '--output', str(target)], capture_output=True)
    assert run.returncode == 2
    assert target.read_text() == 'previous evidence'
