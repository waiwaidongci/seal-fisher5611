"""Competing-risk cumulative incidence for per-specimen shelf observations.

Target event: first seal leak (漏封).  Competing event: first package break
(破包); once a package has broken it can no longer be inspected for a leak.
Loss to follow-up (失访) is treated as non-informative right censoring.

Time origin is shelving (day 0).  Entry into observation may be delayed, so
the risk set is built with left truncation.  At any single instant the agreed
order is:

  1. specimens whose entry day equals the instant join the risk set,
  2. leaks and breaks at that instant are counted together,
  3. specimens lost to follow-up at that instant are removed.

Censoring therefore never reduces the denominator of an event happening at the
same instant.  The estimator is the Aalen-Johansen cumulative incidence

    CIF_k(t) = sum_{t_j <= t} S(t_j-) * d_kj / n_j

where n_j is the number at risk just before t_j (after entries at t_j) and
S(t_j-) is the event-free survival just before t_j.

A requested day with no specimen at risk is refused rather than answered by
carrying the last value forward, and computation is refused if it would
overrun the deadline.
"""

from bisect import bisect_left, bisect_right
import math
import time

DEFAULT_DEADLINE_SECONDS = 5.0
MAX_DAY = 1_000_000.0


class AnalysisRefused(ValueError):
    """The request cannot be answered without extrapolating or overrunning."""

    def __init__(self, reason):
        self.reason = reason
        super().__init__('拒绝出结论：' + reason)


def _check_deadline(start, deadline):
    if time.monotonic() - start > deadline:
        raise AnalysisRefused(f'计算超过{deadline:g}秒时限，未给出结果')


def _finite(value, label):
    if value is None or value == '':
        raise ValueError(f'{label}不得为空')
    if isinstance(value, bool):
        raise ValueError(f'{label}必须是数值')
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f'{label}必须是数值') from None
    if not math.isfinite(number):
        raise ValueError(f'{label}必须是数值')
    if number < 0:
        raise ValueError(f'{label}不得为负')
    if number > MAX_DAY:
        raise ValueError(f'{label}超出业务范围')
    return number


def _optional_day(value, label):
    if value is None or value == '':
        return None
    return _finite(value, label)


def _format_day(value):
    return str(int(value)) if float(value).is_integer() else f'{value:g}'


def _parse_snapshot(snapshot, start, deadline):
    """Parse rows into per-group (entry_day, first_outcome) pairs.

    Each specimen records at most one first outcome (leak / break / loss).
    An empty outcome means the specimen was still under observation when the
    batch was last recorded.
    """
    if not snapshot:
        raise ValueError('空批次无法分析')
    groups = {'A': [], 'B': []}
    for index, row in enumerate(snapshot):
        if index % 8192 == 0:
            _check_deadline(start, deadline)
        if not isinstance(row, dict) or not isinstance(row.get('values'), dict):
            raise ValueError('观测字段不完整')
        values = row['values']
        group = values.get('group')
        if group not in ('A', 'B'):
            raise ValueError('仅允许预定义工艺组A/B')
        entry = _finite(values.get('entry'), '补录入组日')
        leak = _optional_day(values.get('leak'), '首次漏封日')
        broken = _optional_day(values.get('break'), '首次破包日')
        loss = _optional_day(values.get('loss'), '首次失访日')
        recorded = [(day, kind) for day, kind in
                    ((leak, 'leak'), (broken, 'break'), (loss, 'loss'))
                    if day is not None]
        if len(recorded) > 1:
            raise ValueError('每件试件只能记录首次漏封、破包或失访之一')
        if recorded:
            when, kind = recorded[0]
            if when < entry:
                raise ValueError('首次结局日不得早于补录入组日')
            outcome = (when, kind)
        else:
            outcome = None
        groups[group].append((entry, outcome))
    return groups


def _analysable_day(entries, outcomes, day, label):
    """Return the number at risk at `day`, or refuse when none is at risk.

    The day is answerable only when at least one specimen is at risk then.
    Events exactly on the day count as at risk for that day's denominators,
    so a period with no at-risk observation is never carried forward.
    """
    if day < entries[0]:
        raise AnalysisRefused(
            f'指定日 {_format_day(day)} 早于{label}组最早入组日 '
            f'{_format_day(entries[0])}，该时段无在险观察，按规则不外推'
        )
    at_risk = bisect_right(entries, day) - bisect_left(outcomes, day)
    if at_risk <= 0:
        raise AnalysisRefused(
            f'指定日 {_format_day(day)} 在{label}组无在险观察，按规则不外推'
        )
    return at_risk


def _analyse_group(items, day, label, start, deadline):
    if not items:
        raise AnalysisRefused(f'{label}组没有试件记录，无法计算')

    entries = [entry for entry, _ in items]
    outcomes = [outcome[0] for _, outcome in items if outcome is not None]
    event_counts = {}
    for _, outcome in items:
        if outcome is None or outcome[1] == 'loss':
            continue
        when, kind = outcome
        counts = event_counts.get(when)
        if counts is None:
            counts = event_counts[when] = [0, 0]
        counts[0 if kind == 'leak' else 1] += 1

    entries.sort()
    outcomes.sort()
    _check_deadline(start, deadline)

    at_risk_day = _analysable_day(entries, outcomes, day, label)

    survival = 1.0
    cif = 0.0
    times = sorted(when for when in event_counts if when <= day)
    for position, when in enumerate(times):
        if position % 2048 == 0:
            _check_deadline(start, deadline)
        at_risk = bisect_right(entries, when) - bisect_left(outcomes, when)
        leak_count, break_count = event_counts[when]
        if at_risk <= 0:
            # Every event subject enters no later than its event day, so this
            # can only happen with inconsistent input.
            raise ValueError('在险集为空却存在事件，输入不一致')
        cif += survival * leak_count / at_risk
        survival *= 1.0 - (leak_count + break_count) / at_risk

    leak_total = sum(c[0] for when, c in event_counts.items() if when <= day)
    break_total = sum(c[1] for when, c in event_counts.items() if when <= day)
    loss_total = bisect_right(outcomes, day) - leak_total - break_total
    return {
        'cif': cif,
        'at_risk': at_risk_day,
        'entered': len(entries),
        'leak': leak_total,
        'break': break_total,
        'loss': loss_total,
    }


def calculate_competing_risk(snapshot, params, deadline=DEFAULT_DEADLINE_SECONDS):
    """Return the requested-day B-minus-A leak cumulative-incidence difference."""
    start = time.monotonic()
    day = _finite((params or {}).get('day'), '指定日')
    groups = _parse_snapshot(snapshot, start, deadline)
    _check_deadline(start, deadline)

    a = _analyse_group(groups['A'], day, 'A', start, deadline)
    b = _analyse_group(groups['B'], day, 'B', start, deadline)
    _check_deadline(start, deadline)

    difference = b['cif'] - a['cif']
    if abs(difference) < 1e-15:
        difference = 0.0
    if difference > 0:
        sentence = (f'指定第 {_format_day(day)} 天，B工艺漏封累计发生率比A工艺高 '
                    f'{difference * 100:.2f} 个百分点（B减A）')
    elif difference < 0:
        sentence = (f'指定第 {_format_day(day)} 天，B工艺漏封累计发生率比A工艺低 '
                    f'{abs(difference) * 100:.2f} 个百分点（B减A）')
    else:
        sentence = f'指定第 {_format_day(day)} 天，B工艺与A工艺的漏封累计发生率相同（B减A）'

    metrics = {
        'B减A漏封风险差': difference,
        'A组漏封累计发生率': a['cif'],
        'B组漏封累计发生率': b['cif'],
        '指定日 (天)': day,
        'A组指定日在险试件': a['at_risk'],
        'B组指定日在险试件': b['at_risk'],
        '总试件数': a['entered'] + b['entered'],
    }
    rows = [
        [label, stat['entered'], stat['at_risk'], stat['leak'], stat['break'],
         stat['loss'], stat['cif']]
        for label, stat in (('A', a), ('B', b))
    ]
    return {
        'metrics': metrics,
        'interpretation': (
            f'{sentence}。累计发生率按竞争风险（破包为竞争事件、失访为删失）计算，'
            '并使用迟入组风险集；未对无在险观察的时段外推。'
        ),
        'caveat': (
            '假定入组与失访独立且失访为非信息删失；同一时刻先加入迟入组试件，再合并计算'
            '漏封与破包，最后移除失访。结果为指定日描述性风险差，不含区间估计或检验。'
        ),
        'assumptions': [
            '入组独立、失访独立（非信息删失）',
            '同一时刻：先入组，再同算漏封与破包，最后移除失访',
            '破包后无法观察漏封，按竞争事件处理',
            '无在险观察的时段不外推',
        ],
        'table_title': '指定日竞争风险在险依据',
        'columns': ['工艺', '入组试件', '指定日在险', '漏封事件(至指定日)',
                    '破包事件(至指定日)', '失访(至指定日)', '漏封累计发生率'],
        'rows': rows,
    }
