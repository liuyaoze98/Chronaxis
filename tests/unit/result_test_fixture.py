"""为当前结果资源专项提供独立目录、借款和手写平坦贡献事实。

不引用旧结果版本或旧TestCase，不读取CAN；所有句柄和所有者必须真实关闭。
"""
from dataclasses import replace
from pathlib import Path
from uuid import uuid4
import unittest

from chronaxis.core.types import QualityFlag as Q
from chronaxis.results import ResourceBudget
from chronaxis.results.summary import SummaryContributionRow, SummaryCalculationRow


class ResultFixture(unittest.TestCase):
    """仅提供夹具，无测试方法；调用方明确执行setUp/tearDown。"""

    def setUp(self):
        """建立本例目录和责任清单。参数: 无。返回: None。异常: 真实IO错。"""
        self.root = Path('work/current-result-tests').resolve() / uuid4().hex
        self.root.mkdir(parents=True)
        self.owners, self.budgets = [], []

    def tearDown(self):
        """从实际owner关闭并归还借款。参数: 无。返回: None。异常: 关闭/漏账断言。"""
        for owner in reversed(self.owners):
            owner.close()
        for budget in self.budgets:
            self.assertEqual(budget.ram_bytes, 333)
            budget.release_ram(333)
            self.assertEqual(budget.ram_bytes, 0)

    def budget(self):
        """保调用方333字节借款。参数: 无。返回: 实际账本。异常: 预算错。"""
        budget = ResourceBudget(16 * 1024**2)
        budget.reserve_ram(333)
        self.budgets.append(budget)
        return budget

    def contribution(self, sequence=0, *, missing=False, **changes):
        """手写400J或缺失贡献。参数: 序号/缺失/字段覆盖。返回: 当前行。异常: 模型错。"""
        row = SummaryContributionRow(sequence, 'dataset', 'entity', 'session', 'energy', 'bus',
            sequence, sequence, None if missing else 400., 'missing_input' if missing else 'contributed',
            Q.MISSING if missing else Q.NONE)
        return replace(row, **changes)

    def summary(self, sequence=0, **changes):
        """手写800J汇总，无额外原帧证明。参数: 序号/字段覆盖。返回: 当前行。异常: 模型错。"""
        row = SummaryCalculationRow(sequence, 'dataset', 'entity', 'session', 'energy', 'legacy_sum',
                                    'session', None, 800., 'J', 'complete', 'ok', Q.NONE)
        return replace(row, **changes)
