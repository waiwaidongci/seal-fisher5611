import math
from src.config.domain import DOMAIN

KINDS = DOMAIN['kinds']
DEFAULT_KIND = 'seal_fisher'

# Absolute business ceiling for a day count, ~2740 years, kept well inside
# float precision so that ordering and ties remain exact.
MAX_DAY = 1_000_000.0
MAX_SPECIMENS = 100_000


def kind_spec(kind):
    if kind not in KINDS:
        raise ValueError('未知研究类型')
    return KINDS[kind]


def _day(value, label):
    if value is None or value == '':
        return None
    if isinstance(value, bool):
        raise ValueError(label + '必须是数值')
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(label + '必须是数值') from None
    if not math.isfinite(number):
        raise ValueError(label + '必须是有限数值')
    if number < 0:
        raise ValueError(label + '不得为负')
    if number > MAX_DAY:
        raise ValueError(label + '超出业务范围')
    return number


def _seal_values(values):
    expected = {'group', 'success', 'failure'}
    if set(values) != expected:
        raise ValueError('字段必须为 ' + ', '.join(expected))
    group = values['group']
    if group not in ('A', 'B'):
        raise ValueError('工艺组必须为A或B')
    out = {'group': group}
    for key, label in (('success', '合格数'), ('failure', '失败数')):
        raw = values[key]
        if isinstance(raw, bool):
            raise ValueError(label + '必须是数值')
        number = float(raw)
        if not math.isfinite(number) or abs(number) > 1e9:
            raise ValueError(label + '必须为有限业务数值')
        if number < 0:
            raise ValueError(label + '不得为负')
        if number != int(number) or number > 100000:
            raise ValueError('计数必须为0到100000的整数')
        out[key] = number
    if out['success'] + out['failure'] == 0:
        raise ValueError('组内总数必须大于0')
    return out


def _shelf_values(values):
    expected = {'group', 'entry', 'leak', 'break', 'loss'}
    if set(values) != expected:
        raise ValueError('字段必须为 ' + ', '.join(sorted(expected)))
    group = values['group']
    if group not in ('A', 'B'):
        raise ValueError('工艺组必须为A或B')
    entry = _day(values['entry'], '补录入组日')
    if entry is None:
        raise ValueError('补录入组日不得为空')
    out = {'group': group, 'entry': entry, 'leak': None, 'break': None, 'loss': None}
    recorded = 0
    for key, label in (('leak', '首次漏封日'), ('break', '首次破包日'), ('loss', '首次失访日')):
        day = _day(values[key], label)
        if day is not None:
            if day < entry:
                raise ValueError(label + '不得早于补录入组日')
            recorded += 1
        out[key] = day
    if recorded > 1:
        raise ValueError('每件试件只能记录首次漏封、破包或失访之一')
    return out


def validate_values(values, kind=DEFAULT_KIND):
    spec = kind_spec(kind)
    if not isinstance(values, dict):
        raise ValueError('观测必须为字段映射')
    return _shelf_values(values) if kind == 'shelf_risk' else _seal_values(values)


def validate_parameters(params, kind=DEFAULT_KIND):
    spec = kind_spec(kind)
    defaults = spec['defaults']
    if params is None:
        params = {}
    if not isinstance(params, dict) or set(params) - set(defaults):
        raise ValueError('存在未知分析参数')
    p = defaults | params
    if kind == 'shelf_risk':
        day = _day(p.get('day'), '指定日')
        if day is None:
            raise ValueError('指定日不得为空')
        p['day'] = day
        return p
    for key in ('alpha',):
        p[key] = float(p[key])
        if not math.isfinite(p[key]) or not 0.001 <= p[key] <= 0.2:
            raise ValueError('显著性超出范围')
    return p
