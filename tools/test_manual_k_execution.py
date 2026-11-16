"""用真实两分卷教学输入核对K05/K06文案，不按运行快慢推断执行路径。

测试仅在临时目录写冲突夹具和运行工作文件。通过公开Runner读取结果，
只观察P5执行入口是否调用，既不替换算法也不改变预算及计算配置。
"""
from copy import deepcopy
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from ruamel.yaml import YAML
from chronaxis import AnalysisPlan, AnalysisRunner
from chronaxis.execution.parallel_integral_session import ParallelIntegralSession
from chronaxis.planning.backend_selection import select_backend
from chronaxis.results.errors import AnalysisError

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / 'Docs/Current/examples'


class ManualKExecutionTests(unittest.TestCase):
    """限定同刻更新与表达式选路，结果分别由38/44/76J手算验收。"""

    def setUp(self):
        """无参数；读取教学声明并创建临时工作区；文件错误直接传播。"""
        self.temp = tempfile.TemporaryDirectory(prefix='manual-k-execution-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.raw = YAML(typ='safe').load((EXAMPLES / 'continuous-parallel.yaml').read_text(encoding='utf-8'))

    def run_value(self, raw):
        """参数为新配置；返回(能量,执行次数)；公共运行和关闭异常保留。"""
        plan = AnalysisPlan.from_dict(raw, base_dir=EXAMPLES)
        self.assertEqual(select_backend(plan).selected, 'reference')
        calls = []
        original = ParallelIntegralSession.execute

        def observed(owner):
            """参数为真实会话；记录入口后调用原实现；返回及异常保持。"""
            calls.append(True)
            return original(owner)

        with patch.object(ParallelIntegralSession, 'execute', observed):
            with AnalysisRunner().run(plan, work_dir=self.root / ('run-' + str(len(list(self.root.iterdir()))))) as result:
                rows = tuple(result.iter_calculations())
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0].status, 'complete')
                value = rows[0].value
                budget = result.spool.budget
        self.assertEqual(budget.ram_bytes, 0)
        return value, len(calls)

    def test_expression_examples_observe_real_execution(self):
        """合法表达式均算对，只有受支持表达式实际调用P5；返回None，失败抛断言。"""
        cases = [('abs(power)', 38., 1), ('power * 2', 76., 1),
                 ('clip(power, quantity(0,"W"), quantity(1000,"W"))', 38., 0),
                 ('minimum(power,power)', 38., 0)]
        for expression, expected, calls in cases:
            with self.subTest(expression=expression):
                raw = deepcopy(self.raw)
                raw['calculations'][0]['expr'] = expression
                self.assertEqual(self.run_value(raw), (expected, calls))

    def test_derived_expression_keeps_supported_operations(self):
        """派生表达式内部仍为算术时运行P5并得76J；无参数或返回，错误原样传播。"""
        raw = deepcopy(self.raw)
        raw['derived'] = {'twice_power': {'expr': 'power * 2'}}
        raw['calculations'][0]['expr'] = 'twice_power'
        self.assertEqual(self.run_value(raw), (76., 1))

    def test_equivalent_and_conflicting_updates(self):
        """相同更新两策略均38J；冲突error失败、last为44J，逐一覆盖1/4进程。"""
        second = (EXAMPLES / 'data/can/session/part2.asc').read_text(encoding='utf-8')
        for value in (4., 7.):
            path = self.root / ('part-' + str(value) + '.asc')
            frame = '1 1 100 Rx d 8 ' + ' '.join(f'{x:02X}' for x in struct.pack('<d', value)) + '\n'
            path.write_text(second.replace('base hex timestamps absolute\n', 'base hex timestamps absolute\n' + frame), encoding='utf-8')
            for count in (1, 4):
                for policy in ('error', 'last_by_sequence'):
                    with self.subTest(value=value, count=count, policy=policy):
                        raw = deepcopy(self.raw)
                        raw['sources'][0]['paths'][1] = str(path)
                        raw['signals'][0]['same_time_policy'] = policy
                        raw['execution']['process_count'] = count
                        if value == 7. and policy == 'error':
                            with self.assertRaises(AnalysisError):
                                self.run_value(raw)
                        else:
                            self.assertEqual(self.run_value(raw)[0], 38. if value == 4. else 44.)


if __name__ == '__main__':
    unittest.main()
