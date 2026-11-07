"""按独立文件模板的声明顺序汇总同一业务指标。只在请求 --total 时使用。"""

from dataclasses import dataclass
import json
import math
from pathlib import Path


def _semantics(spec):
    """比较业务绑定、计算指令、时间范围及解码选项。单文件路径和展示格式可不同。"""
    settings = {key: value for key, value in spec.items()
                if key not in ('path', 'dbc', 'table_format', '_database', 'inputs')}
    if 'inputs' in spec:
        settings['input_options'] = [{k:v for k,v in item.items() if k != 'path'} for item in spec['inputs']]
    return Path(spec['dbc']).resolve(), json.dumps(settings, sort_keys=True, allow_nan=False)


@dataclass(frozen=True)
class FastTotals:
    """在开始读文件前冻结可求和的指标，以及这些指标应当来自哪些任务。"""

    members: tuple
    metrics: tuple

    @classmethod
    def from_specs(cls, specs, *, template):
        """specs 为按模板输入顺序排列的 job_id→fast 声明。返回只读求和计划。

        只接受同模板、可核实相同绑定和累计口径的不同文件。失败发生在任务分派前。
        """
        if template is not True:
            raise ValueError('--total 仅支持同一分析模板展开的独立文件')
        if not specs:
            raise ValueError('--total 没有预期文件')
        first = next(iter(specs.values()))
        expected = _semantics(first)
        metrics = tuple((item['name'], item['unit']) for item in first['metrics'])
        if not metrics or len(metrics) != len({name for name, _ in metrics}):
            raise ValueError('批量总计需要互不重复的计算项')
        files = set()
        for job, spec in specs.items():
            if _semantics(spec) != expected:
                raise ValueError(f'{job} 与首文件的 DBC、绑定、公式、方向或时间口径不同')
            path = Path(spec['path']).resolve()
            if path in files:
                raise ValueError(f'{job} 重复选择了同一个输入文件')
            files.add(path)
        return cls(tuple(specs), metrics)

    def finish(self, outcomes):
        """按计算项和方向桶分别求和。失败/取消/未运行任务须显式写为 None。

        outcomes 的正常值是 worker 返回的未舍入行。成员或行不符合计划属于协议错误。
        数值缺失导致该项总计不可用。有限加数之和溢出时抛出 OverflowError。
        """
        if set(outcomes) != set(self.members):
            raise ValueError('批量结果成员与启动前冻结的文件清单不一致')
        schema = dict(self.metrics)
        sums = dict.fromkeys(schema, 0.0)
        unavailable = {}
        for job in self.members:
            rows = outcomes[job]
            if rows is None:
                for name in schema:
                    unavailable[name] = 'member_not_completed'
                continue
            seen = set()
            for row in rows:
                name = row['name']
                if name not in schema or name in seen or row['unit'] != schema[name]:
                    raise ValueError(f'{job} 返回了未知、重复或单位不符的计算项 {name}')
                seen.add(name)
                value = row['value']
                if value is None and row['status'] == 'indeterminate':
                    unavailable.setdefault(name, 'member_value_unknown')
                elif row['status'] != 'complete' or type(value) not in (float, int):
                    raise ValueError(f'{job} 的 {name} 数值与状态不符')
                elif not math.isfinite(value) or float(value) != value:
                    raise ValueError(f'{job} 的 {name} 不能无损表示为有限 float64')
                else:
                    sums[name] += value
            if seen != schema.keys():
                raise ValueError(f'{job} 缺少预期计算项')
        result = []
        for name, unit in self.metrics:
            reason = unavailable.get(name)
            value = None
            if reason is None:
                value = sums[name]
                if not math.isfinite(value):
                    raise OverflowError(f'批量总计 {name} 溢出')
            result.append(dict(name=name, unit=unit, value=value,
                               status='complete' if reason is None else 'indeterminate', reason=reason))
        return result
