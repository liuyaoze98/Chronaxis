"""以有限手算历史验证信号CSV真时间、质量、原引用及失败发布边界。

仅生成新work测试目录；不访问原始CAN文件。源游标包含未选/越界样本，必须完整
消费和关闭，不能只看已写行数。原始表不插值，不把无效/无样本变成正常零。
"""

import csv
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from published_paths import published_file
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from chronaxis.core.models import Interval, SourceRef
from chronaxis.core.numeric import ScalarValue
from chronaxis.core.types import SignalDType as D, QualityFlag as Q
from chronaxis.execution.history_records import HistorySample
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.codec import _unpack
from chronaxis.results.errors import BudgetExceededError, ResultFormatError
from chronaxis.results.signal_exports import SignalCSVExportSpec, export_signal_csv


def sample(time, value, *, name='voltage', sequence=0, dtype=D.FLOAT64, quality=Q.NONE):
    """构造明确物理样本。参数: time整数ns、value、name/sequence/dtype/quality。返回: HistorySample。异常: 模型非法。
    """
    scalar = ScalarValue(value,dtype,quality==Q.NONE,quality)
    physical = value if scalar.valid else 0.0 if dtype is D.FLOAT64 else 0
    return HistorySample(0,name,time,sequence,physical,scalar,'V' if name=='voltage' else '1',
        SourceRef('session','bus','字段,"含逗号"'),True,value)


class SignalExportTests(unittest.TestCase):
    """每例独立目标；所有资源失败都检查实际目录和共享账本。"""

    def setUp(self):
        """创建测试根。参数: 无。返回: None。异常: I/O错。
        """
        self.root=Path('work/m3-input-home-20261023/signal-export-tests')/uuid4().hex
        self.root.mkdir(parents=True)
        self.budget=ResourceBudget()
        self.spec=SignalCSVExportSpec(('voltage','state'))

    def run_export(self, records, *, interval=None, target='output', cancel=None):
        """运行真实导出。参数: records、interval/target/cancel覆盖。返回: Path。异常: 原导出错误。
        """
        return export_signal_csv(records,self.spec,interval or Interval(0,100),self.root/target,
                                 self.budget,device_label='home',check_cancel=cancel)

    def rows(self, path):
        """读取有限输出夹具。参数: path发布目录。返回: dict行列表。异常: I/O/CSV错。
        """
        with (published_file(path,'original.csv')).open(encoding='utf-8',newline='') as stream:
            return list(csv.DictReader(stream))

    def test_original_async_samples_same_time_and_large_int_time(self):
        """时间、状态与同刻原序保持，不强拼宽表。参数: 无。返回: None。异常: 断言失败。
        """
        base=2**53+1
        records=[sample(base,3.0),sample(base+1,True,name='state',dtype=D.BOOL,sequence=1),
                 sample(base+1,7.0,sequence=2),sample(base+1,9.0,sequence=3)]
        path=self.run_export(iter(records),interval=Interval(base,base+2))
        rows=self.rows(path)
        self.assertEqual([int(r['time_ns']) for r in rows],[base,base+1,base+1,base+1])
        self.assertEqual([r['signal'] for r in rows],['voltage','state','voltage','voltage'])
        self.assertEqual([r['value'] for r in rows],['3.0','True','7.0','9.0'])
        self.assertEqual([int(r['sequence']) for r in rows],[0,1,2,3])
        self.assertEqual(_unpack(json.loads(rows[0]['source_ref_json'])),records[0].source_ref)
        manifest=json.loads((published_file(path,'manifest.json')).read_text(encoding='utf-8'))
        self.assertEqual((manifest['rows'],manifest['observed'],manifest['invalid']),(4,4,0))
        self.assertFalse(manifest['resampling'])
        self.assertEqual(manifest['files'][0]['sha256'],hashlib.sha256((published_file(path,'original.csv')).read_bytes()).hexdigest())
        self.assertEqual(self.budget.ram_bytes,0)

    def test_invalid_nan_and_missing_are_blank_with_reason(self):
        """无效值留空，NaN通过安全标签保留，None不变成0。参数: 无。返回: None。异常: 断言失败。
        """
        rows=self.rows(self.run_export([sample(1,None,quality=Q.MISSING),sample(2,float('nan'),quality=Q.NONFINITE)]))
        self.assertEqual([r['value'] for r in rows],['',''])
        self.assertEqual([r['valid'] for r in rows],['False','False'])
        self.assertEqual([int(r['quality']) for r in rows],[int(Q.MISSING),int(Q.NONFINITE)])
        self.assertEqual([r['status'] for r in rows],['invalid','invalid'])
        self.assertIsNone(_unpack(json.loads(rows[0]['original_value_json'])))
        self.assertEqual(self.budget.ram_bytes,0)

    def test_half_open_empty_and_full_input_consumption(self):
        """右端不写且越界后继续消费到EOF，空范围仍发布表头。参数: 无。返回: None。异常: 断言失败。
        """
        seen=[]
        def records():
            """模拟需完整验证的历史游标。参数: 无。返回: 生成器。异常: 原导出错误。
            """
            try:
                for t in (0,1,2,3):
                    seen.append(t)
                    yield sample(t,float(t),sequence=t)
            finally:
                seen.append('closed')
        rows=self.rows(self.run_export(records(),interval=Interval(1,3)))
        self.assertEqual([r['time_ns'] for r in rows],['1','2'])
        self.assertEqual(seen,[0,1,2,3,'closed'])
        self.assertEqual(self.rows(self.run_export([],interval=Interval(2,2),target='empty')),[])

    def test_unknown_or_unselected_signal_does_not_create_rows(self):
        """只消费所选列但不补没有观测的信号。参数: 无。返回: None。异常: 断言失败。
        """
        self.assertEqual(self.rows(self.run_export([sample(1,5.0,name='other')])),[])

    def test_input_failure_closes_generator_and_never_publishes(self):
        """已写一行后历史失败，正式目标仍不存在。参数: 无。返回: None。异常: 断言失败。
        """
        closed=[]
        def records():
            """产生一行再失败。参数: 无。返回: 生成器。异常: OSError作为故障注入。
            """
            try:
                yield sample(1,3.0)
                raise OSError('历史损坏')
            finally:
                closed.append(True)
        with self.assertRaisesRegex(OSError,'历史损坏'):
            self.run_export(records())
        self.assertEqual(closed,[True])
        self.assertFalse((self.root/'output').exists())
        self.assertEqual(self.budget.ram_bytes,0)
        self.assertFalse(list(self.root.glob('*.incomplete')))

    def test_cancel_preserves_other_owner_budget(self):
        """取消关闭本次文件，但不抵销其他费用。参数: 无。返回: None。异常: 断言失败。
        """
        self.budget.reserve_ram(17)
        with self.assertRaises(KeyboardInterrupt):
            self.run_export([sample(1,3.0)],cancel=Mock(side_effect=KeyboardInterrupt('cancel')))
        self.assertEqual(self.budget.ram_bytes,17)
        self.assertFalse((self.root/'output').exists())
        self.budget.release_ram(17)

    def test_spool_and_row_memory_limits_leave_no_published_output(self):
        """磁盘及单行内存限额均在正式发布前失败。参数: 无。返回: None。异常: 断言失败。
        """
        for budget in (ResourceBudget(spool_quota_bytes=1),ResourceBudget(memory_budget_bytes=180000)):
            self.budget=budget
            with self.assertRaises(BudgetExceededError):
                self.run_export([sample(1,3.0)])
            self.assertFalse((self.root/'output').exists())
            self.assertEqual(budget.ram_bytes,0)

    def test_oversize_line_rejected_without_truncation(self):
        """长引用不能静默截断或突破64KiB行上限。参数: 无。返回: None。异常: 断言失败。
        """
        record=replace(sample(1,3.0),source_ref=SourceRef('session','bus','中'*30000))
        with self.assertRaises(ResultFormatError):
            self.run_export([record])
        self.assertFalse((self.root/'output').exists())
        self.assertEqual(self.budget.ram_bytes,0)

    def test_existing_and_racing_targets_are_not_overwritten(self):
        """已有目录重复导出保留用户内容及上次完整结果；竞争覆盖由发布专项验证。参数: 无。返回: None。异常: 断言失败。
        """
        destination=self.root/'output'; destination.mkdir()
        (destination/'sentinel').write_text('keep',encoding='utf-8')
        first=self.run_export([sample(1,3.0)])
        before={p:p.read_bytes() for p in destination.iterdir()}
        second=self.run_export([])
        self.assertNotEqual(first.manifest_path,second.manifest_path)
        for path,content in before.items(): self.assertEqual(path.read_bytes(),content)
        self.assertEqual(self.budget.ram_bytes,0)

    def test_customer_refprojects_directory_preserves_existing_content(self):
        """客户目录可与开发资料同名，信号导出保留已有文件；只在测试根内写入。"""
        target=self.root/'RefProjects'/'output'
        target.mkdir(parents=True)
        sentinel=target/'user.txt'
        sentinel.write_bytes(b'keep')
        result=self.run_export([sample(1,3.0)],target='RefProjects/output')
        self.assertEqual(len(self.rows(result)),1)
        self.assertEqual(sentinel.read_bytes(),b'keep')
        self.assertEqual(self.budget.ram_bytes,0)

    def test_real_file_close_failure_has_retryable_owner(self):
        """真实已写FD关闭持续失败时保owner，恢复关闭后清账且不发布。参数: 无。返回: None。异常: 断言失败。
        """
        original=Path.open
        proxies=[]
        class FailedClose:
            """包装真实二进制文件，仅在开关打开时拒绝close。"""
            def __init__(self,stream):
                """保真实句柄。参数: stream。返回: None。异常: 无。
                """
                self.stream=stream; self.fail=True
            def write(self,payload):
                """真实写入。参数: payload。返回: 写入数。异常: I/O错。
                """
                return self.stream.write(payload)
            def close(self):
                """按开关实际关闭。参数: 无。返回: None。异常: OSError或原关闭错误。
                """
                if self.fail:
                    raise OSError('关闭暂不可用')
                self.stream.close()
        def opened(path,*args,**kwargs):
            """仅代理新输出。参数: path与open参数。返回: 真实流/代理。异常: I/O错。
            """
            stream=original(path,*args,**kwargs)
            if path.name=='original.csv':
                stream=FailedClose(stream); proxies.append(stream)
            return stream
        with patch.object(Path,'open',autospec=True,side_effect=opened):
            with self.assertRaisesRegex(OSError,'关闭暂不可用') as context:
                self.run_export([sample(1,3.0)])
        owner=context.exception.export_cleanup_owner
        self.assertFalse(owner.closed)
        proxies[0].fail=False
        owner.close()
        self.assertTrue(proxies[0].stream.closed)
        self.assertEqual(self.budget.ram_bytes,0)
        self.assertFalse((self.root/'output').exists())
