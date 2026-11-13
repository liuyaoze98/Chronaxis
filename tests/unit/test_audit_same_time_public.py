"""通过真实ASC文件边界验证普通同刻策略和静态校验范围。

两文件使用同一DBC和时间坐标；计算只选择观测值，不增加后台预扫描或稳定ID。
"""
from itertools import product
from pathlib import Path
from uuid import uuid4
import unittest
from workspace_fixtures import TemporaryDirectory
from chronaxis import AnalysisPlan, AnalysisRunner
from chronaxis.results.errors import AnalysisError


class AuditSameTimePublicTests(unittest.TestCase):
    """同刻处理不取决于文件批次或读取工作进程到达顺序。"""

    def setUp(self):
        """创建独立两分卷和DBC目录。参数: 无。返回: None。异常: 原I/O错误。"""
        self.directory = TemporaryDirectory(prefix='audit-same-time-')
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        self.dbc = self.root / 'power.dbc'
        self.dbc.write_text('VERSION ""\nNS_ :\nBS_:\nBU_: Node\n'
                           'BO_ 256 Frame: 1 Node\n'
                           ' SG_ Value : 0|8@1+ (1,0) [0|255] "W" Node\n',encoding='utf8')

    def config(self, second, policy, processes, batch_rows):
        """写真实同刻分卷并声明选择计算。参数: 第二值/策略/进程/批次。返回: dict。异常: I/O错。"""
        prefix = 'date Mon Jan 1 00:00:00.000 2024\nbase hex timestamps absolute\n'
        first = self.root / 'part1.asc'
        later = self.root / 'part2.asc'
        first.write_text(prefix + '0.0 1 100 Rx d 1 0A\n',encoding='utf8')
        later.write_text(prefix + f'0.0 1 100 Rx d 1 {second:02X}\n'
                         '1.0 1 100 Rx d 1 1E\n2.0 1 100 Rx d 1 28\n',encoding='utf8')
        return dict(config_version=4,dataset=dict(name='data',domain=dict(start='0s',end='2s')),
            sources=[dict(paths=[str(first),str(later)],dbc_by_channel={'1':str(self.dbc)})],
            signals=[dict(name='power',field=dict(frame_id='0x100',signal='Value'),
                          dtype='float64',unit='W',valid_for='3s',same_time_policy=policy)],
            calculations=[dict(name='values',operation='select',scope='session',expr='power',unit='W')],
            execution=dict(process_count=processes,batch_rows=batch_rows))

    def test_identical_and_conflicting_updates_across_files_and_batches(self):
        """相同10W合并；冲突error拒绝，last取20W。参数: 无。返回: None。异常: 原运行错或断言。"""
        for processes,batch_rows,policy,second in product((1,4),(1,8),('error','last_by_sequence'),(10,20)):
            with self.subTest(processes=processes,batch_rows=batch_rows,policy=policy,second=second):
                plan=AnalysisPlan.from_dict(self.config(second,policy,processes,batch_rows))
                work=self.root/uuid4().hex
                if policy=='error' and second==20:
                    with self.assertRaises(AnalysisError):
                        AnalysisRunner().run(plan,work_dir=work)
                    self.assertFalse(work.exists())
                    continue
                result=AnalysisRunner().run(plan,work_dir=work)
                budget=result.spool.budget
                try:
                    rows=tuple(result.iter_selections())
                    self.assertEqual([(row.time_ns,row.value,row.unit,int(row.quality)) for row in rows],
                                     [(0,float(second),'W',0),(1_000_000_000,30.0,'W',0)])
                finally:
                    result.close()
                self.assertEqual(budget.ram_bytes,0)
                self.assertFalse(work.exists())

    def test_static_validation_does_not_read_bad_record_contents(self):
        """合法声明可静态通过，真实坏行在run失败。参数: 无。返回: None。异常: 断言或预期分析错。"""
        raw=self.config(10,'error',1,1)
        path=Path(raw['sources'][0]['paths'][1])
        path.write_text('date Mon Jan 1 00:00:00.000 2024\nbase hex timestamps absolute\n'
                        '0.0 1 100 Rx d 1 0A\nthis is not a CAN record\n',encoding='utf8')
        plan=AnalysisPlan.from_dict(raw)
        self.assertTrue(AnalysisRunner().validate(plan).valid)
        self.assertTrue(AnalysisRunner().validate(plan).execution_ready)
        work=self.root/uuid4().hex
        with self.assertRaises(AnalysisError):
            AnalysisRunner().run(plan,work_dir=work)
        self.assertFalse(work.exists())


if __name__=='__main__':
    unittest.main()
