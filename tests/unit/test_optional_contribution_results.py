"""验证当前平坦结果的可选贡献、明确空表及原子发布。

合成输入为两条400J和一次缺值，汇总800J；不读取CAN或重新计算表达式。
所有表按真实请求创建，默认不产出贡献及质量副本；显式详细诊断才写质量文件。
测试实际暂存、文件句柄和预算，借用333字节最后完整归还。文件仅写项目work。
"""

from contextlib import closing
from dataclasses import replace
import csv
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from chronaxis.core.types import QualityFlag as Q
from chronaxis.results import AnalysisError, AnalysisResult, ContributionsUnavailableError, BudgetExceededError
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.codec import decode_row
from chronaxis.results.spool import ResultSpool
from chronaxis.results.summary import SummaryCalculationRow, SummaryContributionRow
from chronaxis.execution.current_message_calculation import CurrentMessageCalculation
from test_results import run_metadata, summary_event_row


def total(sequence=4):
    """手写800J部分结果，不从被测累计器生成预期。参数: 序号。返回: 行。异常: 模型校验错。"""
    return SummaryCalculationRow(sequence, 'dataset', 'entity', 'session', 'energy',
        'legacy_sum', 'session', None, 800., 'J', 'partial', 'missing_input', Q.MISSING)


def contributions():
    """手写两次贡献与一次缺值。参数: 无。返回: 三行tuple。异常: 模型校验错。"""
    return tuple(SummaryContributionRow(index+1, 'dataset', 'entity', 'session', 'energy',
        'bus', index, index, 400. if index < 2 else None,
        'contributed' if index < 2 else 'missing_input', Q.NONE if index < 2 else Q.MISSING)
        for index in range(3))


class OptionalContributionResultTests(unittest.TestCase):
    """结果只能使用实际请求表，取消和重试保持同一封口行，不重新分析。"""

    def setUp(self):
        """建立唯一工作目录及借款账本。参数: 无。返回: None。异常: IO/预算错误。"""
        temporary = TemporaryDirectory(dir='work', prefix='current-contributions-')
        self.addCleanup(temporary.cleanup)
        self.root, self.owners = Path(temporary.name), []
        self.budget = ResourceBudget(16 * 1024**2)
        self.budget.reserve_ram(333)

    def tearDown(self):
        """关闭真实owner，核只归还自有费用。参数: 无。返回: None。异常: 原关闭/断言错误。"""
        for owner in reversed(self.owners):
            owner.close()
        self.assertEqual(self.budget.ram_bytes, 333)
        self.budget.release_ram(333)

    def spool(self, *, full=False):
        """显式登记当前表，不使用旧执行路线元数据。参数: full。返回: spool。异常: 原预算/IO。"""
        tables = ('events', 'calculations') + (('contributions',) if full else ())
        spool = ResultSpool(self.budget, self.root / ('spool-'+str(len(self.owners))), 1,
                            requested_tables=tables, enable_contributions=full)
        self.owners.append(spool)
        return spool

    def result(self, *, full=False, empty=False, format='jsonl', detailed=False):
        """按请求写唯一一份当前行并封口。参数: 明细/空/格式/诊断。返回: 结果。异常: 原错误。"""
        spool = self.spool(full=full)
        spool.append(summary_event_row(0))
        if full and not empty:
            for row in contributions():
                spool.append(row)
        spool.append(total())
        spool.seal()
        metadata = replace(run_metadata(), device_label='home', detailed_diagnostics=detailed)
        result = AnalysisResult(spool, metadata, format)
        self.owners.append(result)
        return result

    def test_none_query_is_explicit_and_opens_no_file(self):
        """未请求贡献时明确报错且不建立伪空游标。参数: 无。返回: None。异常: 断言。"""
        result = self.result()
        before = self.budget.ram_bytes
        self.assertFalse(result.contributions_available)
        with patch.object(Path, 'open', side_effect=AssertionError('未请求表不能打开文件')):
            with self.assertRaises(ContributionsUnavailableError):
                result.iter_contributions()
        self.assertEqual(self.budget.ram_bytes, before)
        self.assertNotIn('contributions', result.spool.tables)

    def test_requested_empty_is_available_and_publishes_empty_table(self):
        """明确请求但零贡献与未请求区别保留。参数: 无。返回: None。异常: 断言。"""
        for format in ('csv', 'jsonl'):
            result = self.result(full=True, empty=True, format=format)
            self.assertTrue(result.contributions_available)
            with closing(result.iter_contributions()) as reader:
                self.assertEqual(tuple(reader), ())
            published = result.write(self.root / ('empty-'+format))
            table = published.output_dir / ('contributions.'+format)
            self.assertTrue(table.exists())
            self.assertEqual(dict(published.row_counts)['contributions'], 0)
            if format == 'jsonl':
                self.assertEqual(table.read_bytes(), b'')
            else:
                with table.open(encoding='utf-8', newline='') as handle:
                    self.assertEqual(list(csv.DictReader(handle)), [])

    def test_unrequested_contribution_is_rejected_before_encoding(self):
        """不允许先生成再悄悄丢弃贡献，拒绝不推进计数。参数: 无。返回: None。异常: 断言。"""
        spool = self.spool()
        with patch('chronaxis.results.spool.encode_row', side_effect=AssertionError('不应编码未请求表')):
            with self.assertRaises(AnalysisError):
                spool.append(contributions()[0])
        self.assertEqual(sum(spool.counts.values()), 0)

    def test_csv_jsonl_keep_totals_and_only_requested_contributions(self):
        """两格式有相同800J、原序、缺值和质量，默认无额外明细文件。参数: 无。返回: None。异常: 断言。"""
        for format in ('csv', 'jsonl'):
            for full in (False, True):
                for detailed in (False, True):
                    with self.subTest(format=format, full=full, detailed=detailed):
                        result = self.result(full=full, format=format, detailed=detailed)
                        self.assertEqual(tuple(result.iter_calculations()), (total(),))
                        published = result.write(self.root / f'{format}-{full}-{detailed}')
                        names = {path.name for path in published.output_dir.iterdir()}
                        self.assertEqual(('contributions.'+format) in names, full)
                        self.assertEqual('quality.jsonl' in names, detailed)
                        self.assertNotIn('message_calculations.'+format, names)
                        if full:
                            path = published.output_dir / ('contributions.'+format)
                            if format == 'jsonl':
                                rows = tuple(decode_row(line, 65536) for line in path.read_bytes().splitlines(keepends=True))
                                self.assertEqual(rows, contributions())
                            else:
                                with path.open(encoding='utf-8', newline='') as handle:
                                    rows = list(csv.DictReader(handle))
                                self.assertEqual([row['value'] for row in rows], ['400.0', '400.0', ''])
                                self.assertEqual([row['original_sequence'] for row in rows], ['0', '1', '2'])
                                self.assertEqual(rows[-1]['reason'], 'missing_input')
                        if detailed:
                            quality = [json.loads(line) for line in (published.output_dir/'quality.jsonl').read_text(encoding='utf-8').splitlines()]
                            selected = [row for row in quality if row['table']=='contributions']
                            self.assertEqual([row['quality'] for row in selected], [0, 0, int(Q.MISSING)] if full else [])
                            self.assertEqual([row['reason'] for row in selected], ['contributed', 'contributed', 'missing_input'] if full else [])

    def test_two_readers_have_independent_positions_and_close_fees(self):
        """一个游标读完并关闭不影响另一个的位置。参数: 无。返回: None。异常: 断言。"""
        result = self.result(full=True)
        baseline = self.budget.ram_bytes
        first, second = result.iter_contributions(), result.iter_contributions()
        self.assertEqual(next(first), contributions()[0])
        self.assertEqual(tuple(second), contributions())
        self.assertEqual(tuple(first), contributions()[1:])
        self.assertTrue(first.closed and second.closed)
        self.assertEqual(self.budget.ram_bytes, baseline)

    def test_failed_install_retries_same_rows_without_reanalysis(self):
        """安装失败不发布completed，同一结果重试和再次发布不重算。参数: 无。返回: None。异常: 断言。"""
        result = self.result(full=True)
        with patch.object(CurrentMessageCalculation, 'consume', side_effect=AssertionError('发布不重算')):
            with patch.object(result, '_install_directory', side_effect=OSError('合成安装错误')):
                with self.assertRaises(AnalysisError):
                    result.write(self.root/'failed')
            self.assertFalse((self.root/'failed').exists())
            first, second = result.write(self.root/'first'), result.write(self.root/'second')
        self.assertEqual(first.row_counts, second.row_counts)
        for name in ('calculations', 'contributions', 'events'):
            self.assertEqual((first.output_dir/(name+'.jsonl')).read_bytes(),
                             (second.output_dir/(name+'.jsonl')).read_bytes())

    def test_budget_rejection_precedes_encoding_and_preserves_caller_loan(self):
        """预算不足不编码贡献、不增加计数，也不抵销调用方借款。参数: 无。返回: None。异常: 断言。"""
        spool = self.spool(full=True)
        loan = self.budget.memory_budget_bytes - self.budget.ram_bytes - 1
        self.budget.reserve_ram(loan)
        try:
            with patch('chronaxis.results.spool.encode_row', side_effect=AssertionError('预算不足不能编码')):
                with self.assertRaises(BudgetExceededError):
                    spool.append(contributions()[0])
            self.assertEqual(sum(spool.counts.values()), 0)
            spool.close()
            self.assertEqual(self.budget.ram_bytes, 333+loan)
        finally:
            self.budget.release_ram(loan)


if __name__ == '__main__':
    unittest.main()
