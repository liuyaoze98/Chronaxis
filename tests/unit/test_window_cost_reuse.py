"""核对长合并窗口复用事件费用，保留原工作区金额和全部父事件。

通过公开Runner生成130段活动；统计费用遍历次数，并以原收费公式独立核对
每笔工作区申请。两数值后端均保留窗口边界和资源关闭，不将此测试作为计时。
"""

from pathlib import Path
import unittest
from unittest.mock import patch

from chronaxis import AnalysisPlan, AnalysisRunner
from chronaxis.core.temporal import Event
from chronaxis.execution import record_windows
from workspace_fixtures import TemporaryDirectory


class WindowCostReuseTests(unittest.TestCase):
    """合并组跨过多次64事件处理边界，旧前缀仍只计一次元数据费用。"""

    def test_retained_parent_cost_is_reused_without_reducing_workspace(self):
        """130活动并成0到260秒窗口，父关系完整且每笔费用等于原公式。

        参数: 无。返回: None。异常: 费用、次数、结果或资源断言失败。
        """
        raw = dict(config_version=4, dataset=dict(name='window_cost'),
                   sources=[dict(name='input', source_type='memory',
                                 rows=[dict(time=f'{t}s', values=dict(v=int(t % 2 == 0 and t < 260)))
                                       for t in range(261)])],
                   signals=[dict(name='value', source='input', field='v', dtype='int64',
                                 unit='1', valid_for='3s')],
                   rules=[dict(name='alarm', rule_type='condition_duration', condition='value > 0',
                               minimum_duration='0s', duration_comparison='>=')],
                   windows=[dict(name='merged', rule='alarm', anchor='activity', pre='0s', post='2s',
                                 merge='overlap_and_adjacent')], calculations=[])
        estimate = record_windows._metadata_bytes
        reserve = record_windows._reserve_owned_ram
        for backend in ('reference', 'numpy'):
            counted, workspaces = [], []

            def observed(value, *args, **kwargs):
                """记录真正遍历的事件。参数: 原估算输入。返回: 原费用。异常: 原估算错误。"""
                if type(value) is Event:
                    counted.append(value.event_id)
                return estimate(value, *args, **kwargs)

            def charged(owner, amount, slot):
                """用原公式核费用，独立计算不纳入被测遍历次数。

                参数: 原所有者、金额和槽。返回: 原申请结果。异常: 费用差异或原预算错误。
                """
                if slot == '_workspace_cost':
                    entries = owner._parents['merged']
                    expected = 65536 + sum(8192 + 16 * estimate(item[0]) for item in entries)
                    self.assertEqual(amount, expected)
                    workspaces.append(len(entries))
                return reserve(owner, amount, slot)

            with self.subTest(backend=backend), TemporaryDirectory(prefix='window-fees-') as folder:
                with patch.object(record_windows, '_metadata_bytes', new=observed), \
                     patch.object(record_windows, '_reserve_owned_ram', new=charged):
                    with AnalysisRunner(backend).run(AnalysisPlan.from_dict(raw), Path(folder)/'run') as result:
                        events = tuple(result.iter_events())
                        segment, = tuple(result.iter_segments())
                        budget = result.spool.budget
                        self.assertEqual(len(events), 130)
                        self.assertEqual(segment.parent_event_ids, tuple(event.event_id for event in events))
                        self.assertEqual((segment.start_ns, segment.end_ns, segment.status),
                                         (0, 260_000_000_000, 'partial'))
                self.assertEqual(len(counted), 130)
                self.assertEqual(len(set(counted)), 130)
                self.assertEqual(workspaces, [64, 128, 130])
                self.assertEqual(budget.ram_bytes, 0)
