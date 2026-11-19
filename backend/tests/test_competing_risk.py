"""Oracle checks for the competing-risk estimator.

The Aalen-Johansen estimate is recomputed independently, term by term, from
the raw specimen records, so a change in the optimised implementation is
caught even if it agrees with itself.
"""

import math
import random

import pytest

from src.services.competing_risk import (
    AnalysisRefused,
    calculate_competing_risk,
)


def specimen(group, entry, leak=None, **outcome):
    broken=outcome.get('break', outcome.get('broken'))
    loss=outcome.get('loss')
    return {'source_key': 'x', 'values': {'group': group, 'entry': entry,
            'leak': leak, 'break': broken, 'loss': loss}}


def reference(items, day):
    """Direct O(n^2) Aalen-Johansen with the agreed same-instant ordering."""
    entries = [e for e, _ in items]
    outc = [o[0] for _, o in items if o is not None]
    events = {}
    for _, o in items:
        if o is None or o[1] == 'loss':
            continue
        events.setdefault(o[0], [0, 0])[0 if o[1] == 'leak' else 1] += 1
    survival, cif = 1.0, 0.0
    for t in sorted(events):
        if t > day:
            break
        n = sum(1 for e in entries if e <= t) - sum(1 for o in outc if o < t)
        d = sum(events[t])
        cif += survival * events[t][0] / n
        survival *= 1 - d / n
    at_risk = sum(1 for e in entries if e <= day) - sum(1 for o in outc if o < day)
    return cif, at_risk


def random_batch(seed, n_per_group=60):
    rng = random.Random(seed)
    rows = []
    for group in ('A', 'B'):
        for _ in range(n_per_group):
            entry = 0.0 if rng.random() < 0.6 else rng.uniform(1, 40)
            end = rng.choice(['leak', 'break', 'loss', 'none'])
            if end == 'none':
                rows.append(specimen(group, entry))
            else:
                day = entry + rng.uniform(0, 120)
                rows.append(specimen(group, entry, **{end: round(day, 6)}))
    return rows


@pytest.mark.parametrize('seed', [1, 7, 42, 99])
def test_matches_direct_aalen_johansen(seed):
    rows = random_batch(seed)
    for day in (0, 10, 25.5, 60, 120):
        result = calculate_competing_risk(rows, {'day': day})
        for group, label in (('A', 'A组漏封累计发生率'), ('B', 'B组漏封累计发生率')):
            items = []
            for row in rows:
                v = row['values']
                if v['group'] != group:
                    continue
                if v['leak'] is not None:
                    items.append((v['entry'], (v['leak'], 'leak')))
                elif v['break'] is not None:
                    items.append((v['entry'], (v['break'], 'break')))
                elif v['loss'] is not None:
                    items.append((v['entry'], (v['loss'], 'loss')))
                else:
                    items.append((v['entry'], None))
            expected, at_risk = reference(items, day)
            assert result['metrics'][label] == pytest.approx(expected, abs=1e-12)
            assert result['metrics'][f'{group}组指定日在险试件'] == at_risk


def test_risk_difference_is_b_minus_a():
    rows = [specimen('A', 0, leak=10), specimen('A', 0, leak=10), specimen('A', 0),
            specimen('B', 0, leak=10), specimen('B', 0), specimen('B', 0)]
    result = calculate_competing_risk(rows, {'day': 10})
    assert result['metrics']['A组漏封累计发生率'] == pytest.approx(2 / 3)
    assert result['metrics']['B组漏封累计发生率'] == pytest.approx(1 / 3)
    assert result['metrics']['B减A漏封风险差'] == pytest.approx(1 / 3 - 2 / 3)


def test_break_is_competing_event_not_leak():
    rows = [specimen('A', 0, broken=5), specimen('A', 0, broken=5),
            specimen('B', 0, leak=5), specimen('B', 0)]
    result = calculate_competing_risk(rows, {'day': 5})
    assert result['metrics']['A组漏封累计发生率'] == 0
    assert result['metrics']['B组漏封累计发生率'] == pytest.approx(0.5)
    assert result['metrics']['B减A漏封风险差'] == pytest.approx(0.5)


def test_delayed_entry_joins_risk_set_before_same_day_event():
    # The late specimen enters on day 10 and leaks that day; it belongs to the
    # day-10 denominator, so the risk is 1/2 rather than 1/1.
    rows = [specimen('A', 0, loss=50), specimen('A', 10, leak=10), specimen('B', 0, leak=100)]
    result = calculate_competing_risk(rows, {'day': 10})
    assert result['metrics']['A组漏封累计发生率'] == pytest.approx(0.5)
    assert result['metrics']['A组指定日在险试件'] == 2


def test_same_instant_loss_does_not_shrink_event_denominator():
    # One leak and one loss both on day 10 with two at risk: the loss is
    # removed after that instant's events, so the denominator stays 2.
    rows = [specimen('A', 0, leak=10), specimen('A', 0, loss=10), specimen('B', 0, leak=100)]
    result = calculate_competing_risk(rows, {'day': 10})
    assert result['metrics']['A组漏封累计发生率'] == pytest.approx(0.5)
    assert result['metrics']['A组指定日在险试件'] == 2


def test_leak_and_break_same_instant_are_counted_together():
    # Both events on day 10 leave zero event-free survival but the day's leak
    # still uses the pre-event denominator of 2.
    rows = [specimen('A', 0, leak=10), specimen('A', 0, broken=10), specimen('B', 0, leak=100)]
    result = calculate_competing_risk(rows, {'day': 10})
    assert result['metrics']['A组漏封累计发生率'] == pytest.approx(0.5)


def test_day_after_all_outcomes_is_refused():
    rows = [specimen('A', 0, leak=10), specimen('B', 0, leak=10)]
    with pytest.raises(AnalysisRefused, match='无在险观察'):
        calculate_competing_risk(rows, {'day': 40})


def test_day_inside_support_with_no_event_yet_is_answered():
    rows = [specimen('A', 0, leak=10), specimen('B', 0, leak=10)]
    result = calculate_competing_risk(rows, {'day': 9})
    assert result['metrics']['A组指定日在险试件'] == 1
    assert result['metrics']['A组漏封累计发生率'] == 0


def test_day_inside_an_unobserved_gap_is_refused():
    # A's risk set empties on day 5 and only resumes at a late entry on day 30.
    rows = [specimen('A', 0, loss=5), specimen('A', 30, loss=40),
            specimen('B', 0, loss=40)]
    with pytest.raises(AnalysisRefused, match='A组无在险观察'):
        calculate_competing_risk(rows, {'day': 20})
    # After observation resumes the estimate is defined again; the empty
    # stretch is not extrapolated but also does not poison later coverage.
    result = calculate_competing_risk(rows, {'day': 35})
    assert result['metrics']['A组指定日在险试件'] == 1


def test_day_before_first_entry_is_refused():
    rows = [specimen('A', 5, leak=6), specimen('B', 5, leak=6)]
    with pytest.raises(AnalysisRefused, match='最早入组日'):
        calculate_competing_risk(rows, {'day': 4})


def test_incomplete_outcome_combination_is_rejected():
    rows = [specimen('A', 0, leak=5, broken=6), specimen('B', 0, leak=5)]
    with pytest.raises(ValueError, match='只能记录'):
        calculate_competing_risk(rows, {'day': 5})


def test_outcome_before_entry_is_rejected():
    rows = [specimen('A', 5, leak=4), specimen('B', 0, leak=5)]
    with pytest.raises(ValueError, match='不得早于'):
        calculate_competing_risk(rows, {'day': 5})


def test_unknown_group_is_rejected():
    rows = [specimen('C', 0, leak=5), specimen('B', 0, leak=5)]
    with pytest.raises(ValueError, match='A/B'):
        calculate_competing_risk(rows, {'day': 5})


def test_empty_group_is_refused():
    rows = [specimen('A', 0, leak=5)]
    with pytest.raises(AnalysisRefused, match='B组没有试件'):
        calculate_competing_risk(rows, {'day': 5})


def test_negative_and_non_finite_days_are_rejected():
    rows = [specimen('A', -1, leak=5), specimen('B', 0, leak=5)]
    with pytest.raises(ValueError, match='不得为负'):
        calculate_competing_risk(rows, {'day': 5})
    rows = [specimen('A', 0, leak=5), specimen('B', 0, leak=5)]
    with pytest.raises(ValueError):
        calculate_competing_risk(rows, {'day': float('nan')})


def test_overrun_deadline_refuses():
    rows = random_batch(5, n_per_group=200)
    with pytest.raises(AnalysisRefused, match='时限'):
        calculate_competing_risk(rows, {'day': 30}, deadline=-1)


def test_hundred_thousand_specimens_finishes_within_five_seconds():
    import time
    rng = random.Random(2026)
    rows = []
    for i in range(100_000):
        group = 'A' if i % 2 else 'B'
        entry = rng.uniform(0, 10)
        pick = i % 11
        values = {'group': group, 'entry': entry, 'leak': None, 'break': None, 'loss': None}
        if pick == 0:
            values['break'] = entry
        elif pick == 1:
            values['loss'] = entry
        elif pick != 2:
            values['leak'] = rng.uniform(entry, 400)
        rows.append({'source_key': str(i), 'values': values})
    started = time.monotonic()
    result = calculate_competing_risk(rows, {'day': 30})
    elapsed = time.monotonic() - started
    assert elapsed < 5
    assert -1 <= result['metrics']['B减A漏封风险差'] <= 1
    assert result['metrics']['总试件数'] == 100_000
