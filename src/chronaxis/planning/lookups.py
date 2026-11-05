"""在静态配置中解析 v4 一维表；仅创建冻结点对，不创建求值数组或打开文件。"""

from ..core.lookup import LookupTablePlan, MAX_POINTS, MAX_TABLES
from .checks import PlanValidationError, array_at, model_at, number_at, object_at, text_at


def parse_lookups(raw, version):
    """从根数组建立标定表。参数: 原列表及版本。返回: 冻结表元组。异常: 含具体位置的配置错误。"""
    items = array_at(raw, '$.lookups')
    if version != 4:
        raise PlanValidationError('$.lookups', 'lookups需要config_version=4')
    if len(items) > MAX_TABLES:
        raise PlanValidationError('$.lookups', f'最多声明{MAX_TABLES}张表')
    result, names = [], set()
    for index, item in enumerate(items):
        path = f'$.lookups[{index}]'
        item = object_at(item, path, ('name', 'points', 'input_unit', 'unit'))
        name = text_at(item['name'], path + '.name', identifier=True)
        if name in names:
            raise PlanValidationError(path + '.name', 'lookup表名重复')
        names.add(name)
        points = array_at(item['points'], path + '.points')
        if not 2 <= len(points) <= MAX_POINTS:
            raise PlanValidationError(path + '.points', f'查表需要2至{MAX_POINTS}个点')
        pairs = []
        for offset, pair in enumerate(points):
            position = f'{path}.points[{offset}]'
            if len(array_at(pair, position)) != 2:
                raise PlanValidationError(position, '查表点需要一对数值')
            pairs.append(tuple(number_at(v, f'{position}[{i}]') for i, v in enumerate(pair)))
        result.append(model_at(LookupTablePlan, path, name, tuple(pairs),
                               text_at(item['input_unit'], path + '.input_unit'), text_at(item['unit'], path + '.unit')))
    return tuple(result)
