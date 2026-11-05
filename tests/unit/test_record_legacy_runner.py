"""公开入口核三格式逐消息累计：三帧含同刻两帧，仍各算一次，不建普通历史。"""
from published_paths import published_file


from configuration_fixtures import current_fixture

from copy import deepcopy
import csv
import json
from itertools import product
from uuid import uuid4
import unittest
from unittest.mock import patch

from chronaxis import AnalysisPlan, AnalysisRunner, validate_analysis_plan
from test_current_message_calculation import config
import test_raw_can_continuous as files


class RecordLegacyRunnerTests(unittest.TestCase):
    """独立手算正桶800J、负桶-200J；有无时间域不改变逐条贡献规则。"""

    setUp = files.RawCANContinuousTests.setUp
    asc = files.RawCANContinuousTests.asc
    csv = files.RawCANContinuousTests.csv
    blf = files.RawCANContinuousTests.blf

    def fixtures(self):
        """创建有符号功率DBC和同值三格式。参数: 无。返回: 路径字典。异常: I/O错误。"""
        self.dbc.write_text('VERSION ""\nNS_ :\nBS_:\nBU_: Node\n'
            'BO_ 256 Frame: 1 Node\n SG_ Power : 0|8@1- (1000,0) [-128000|127000] "W" Node\n', encoding='utf-8')
        return dict(can_blf=self.blf(((0.,bytes([4])),(0.,bytes([4])),(.2,bytes([254])))),
            can_asc=self.asc('0.00 1 100 Rx d 1 04\n0.00 1 100 Rx d 1 04\n0.20 1 100 Rx d 1 FE\n').path,
            raw_can_csv=self.csv('0,100,04,1\n0,100,04,1\n0.2,100,FE,1\n').path)

    def plan(self, kind, path, bounded=True):
        """在编译前确定全部来源和时间声明。参数: 格式/路径/是否有域。返回: 配置。异常: 无主动错误。"""
        raw = config(kind)
        raw['sources'][0]['path'] = str(path.absolute())
        raw['sources'][0]['dbc_by_channel'] = {'1': str(self.dbc.absolute())}
        if not bounded:
            raw['dataset'].pop('domain')
        elif kind == 'can_blf':
            raw['dataset']['domain'] = dict(start='1700000000s', end='1700000012s')
        positive = raw['message_calculations'][0]
        positive['name'] = 'positive'
        positive['split_by_sign'] = dict(signal='power', bucket='positive', value_policy='raw_decoded-v1')
        negative = deepcopy(positive)
        negative['name'] = 'negative'
        negative['split_by_sign']['bucket'] = 'negative'
        raw['message_calculations'].append(negative)
        return raw

    def test_three_formats_backends_and_optional_domain(self):
        """同刻两帧不会合并，负桶不补正；默认没有历史仓或最新值状态。"""
        for (kind,path),backend,bounded in product(self.fixtures().items(),('reference','numpy'),(True,False)):
            with self.subTest(kind=kind,backend=backend,bounded=bounded):
                plan = AnalysisPlan.from_dict(current_fixture(self.plan(kind,path,bounded)))
                self.assertTrue(validate_analysis_plan(plan).execution_ready)
                root = self.root / uuid4().hex
                with patch('chronaxis.execution.record_session_calculations.LatestSignalState', side_effect=AssertionError('unused state')):
                    result = AnalysisRunner(backend).run(plan,root)
                self.addCleanup(result.close)
                rows = tuple(result.iter_calculations())
                self.assertEqual({r.calculation_id:r.value for r in rows},dict(positive=800.,negative=-200.))
                self.assertTrue(all(r.status=='complete' and r.quality==0 for r in rows))
                budget=result.spool._budget
                result.close()
                self.assertEqual(budget.ram_bytes,0)
                self.assertFalse(root.exists())

    def test_constant_formula_needs_no_signal_decode(self):
        """参数公式仅按匹配ID触发，三帧各400J；不构造任何普通信号组。"""
        for kind,path in self.fixtures().items():
            raw=self.plan(kind,path)
            raw['signals']=[]
            calculation=raw['message_calculations'][0]
            calculation.pop('split_by_sign')
            calculation['expr']='watts * period'
            calculation['parameters']['watts']=dict(value=4000,unit='W')
            raw['message_calculations']=[calculation]
            result=AnalysisRunner().run(AnalysisPlan.from_dict(current_fixture(raw)),self.root/uuid4().hex)
            self.addCleanup(result.close)
            self.assertEqual(next(result.iter_calculations()).value,1200.)
            result.close()

    def test_summary_uses_bounded_target_batches_and_flushes_tail(self):
        """两桶共享目标批，跨批尾部不漏；完整贡献仍保逐消息顺序。"""
        from chronaxis.execution.current_message_calculation import CurrentMessageCalculation
        paths=self.fixtures()
        for (kind,path),backend,detail,limit in product(paths.items(),('reference','numpy'),('none','full'),(2,64)):
            with self.subTest(kind=kind,backend=backend,detail=detail,limit=limit):
                raw=self.plan(kind,path,False)
                raw.setdefault('execution',{})['batch_rows']=limit
                raw['outputs']['contributions']=detail
                calls=[];original=CurrentMessageCalculation.consume
                def measured(owner,updates):
                    """只记录真实计算批大小，不替代数值实现。"""
                    calls.append(len(updates));return original(owner,updates)
                with patch.object(CurrentMessageCalculation,'consume',measured):
                    result=AnalysisRunner(backend).run(AnalysisPlan.from_dict(current_fixture(raw)),self.root/uuid4().hex)
                self.addCleanup(result.close)
                self.assertEqual({r.calculation_id:r.value for r in result.iter_calculations()},dict(positive=800.,negative=-200.))
                self.assertEqual(calls,[1]*6 if detail=='full' else [2,2,1,1] if limit==2 else [3,3])
                budget=result.spool.budget;result.close()
                self.assertEqual(budget.ram_bytes,0)

    def test_buffer_failure_releases_owned_rows_and_does_not_publish(self):
        """消息批扣账后取消及释放时故障都保真实费用，由会话失败清理回收。"""
        import chronaxis.execution.record_session_calculations as module
        raw=self.plan('can_asc',self.fixtures()['can_asc'],False)
        raw.setdefault('execution',{})['batch_rows']=64
        for method in ('_reserve_owned_ram','_release_owned_ram'):
            original=getattr(module,method);budgets=[];fired=[]
            def fail_once(owner,amount,slot):
                """在真实费用操作成功后抛取消，不能把已扣/已退账重复处理。"""
                original(owner,amount,slot)
                if slot=='_message_cost' and amount and not fired:
                    fired.append(True);budgets.append(owner._budget)
                    raise KeyboardInterrupt('message buffer transaction')
            root=self.root/uuid4().hex
            with patch.object(module,method,fail_once),self.assertRaises(KeyboardInterrupt):
                AnalysisRunner().run(AnalysisPlan.from_dict(current_fixture(raw)),root)
            self.assertTrue(fired)
            self.assertEqual(budgets[0].ram_bytes,0)
            self.assertFalse(root.exists())

    def test_large_requested_batch_leaves_memory_for_calculation(self):
        """批上限大于预算可容纳条数时提前计算，不能填满缓存后才发现数组放不下。"""
        from chronaxis.execution.current_message_calculation import CurrentMessageCalculation
        self.fixtures()
        path=self.asc(''.join(f'{i/1000:.3f} 1 100 Rx d 1 04\n' for i in range(2000))).path
        raw=self.plan('can_asc',path,False)
        raw['execution']=dict(batch_rows=4096,memory_budget_bytes=64*1024*1024)
        calls=[];original=CurrentMessageCalculation.consume
        def measured(owner,updates):
            """保留真实计算，只观察实际批和最终预算峰值。"""
            calls.append(len(updates));return original(owner,updates)
        with patch.object(CurrentMessageCalculation,'consume',measured):
            result=AnalysisRunner().run(AnalysisPlan.from_dict(current_fixture(raw)),self.root/uuid4().hex)
        self.addCleanup(result.close)
        self.assertEqual({r.calculation_id:r.value for r in result.iter_calculations()},dict(positive=800000.,negative=None))
        self.assertEqual(sum(calls),4000)
        self.assertGreater(max(calls),1)
        self.assertLess(max(calls),2000)
        budget=result.spool.budget
        self.assertLessEqual(budget.peak_ram_bytes,64*1024*1024)
        result.close();self.assertEqual(budget.ram_bytes,0)

    def test_requested_contributions_are_compact_and_match_totals(self):
        """三格式明细含同刻两次计算及跳过；外排和CSV/JSONL发布不复制原值/帧。"""
        from chronaxis.results.summary import SummaryContributionRow
        for (kind,path),backend,fmt in product(self.fixtures().items(),('reference','numpy'),('csv','jsonl')):
            with self.subTest(kind=kind,backend=backend,fmt=fmt):
                raw=self.plan(kind,path,False)
                raw['outputs']['contributions']='full'
                raw['outputs']['tables']=fmt
                raw.setdefault('execution',{})['result_buffer_rows']=1
                result=AnalysisRunner(backend).run(AnalysisPlan.from_dict(current_fixture(raw)),self.root/uuid4().hex)
                self.addCleanup(result.close)
                rows=tuple(result.iter_contributions())
                self.assertTrue(result.contributions_available)
                self.assertEqual(len(rows),6)
                self.assertTrue(all(type(row) is SummaryContributionRow for row in rows))
                for calculation in result.iter_calculations():
                    selected=[row for row in rows if row.calculation_id==calculation.calculation_id]
                    self.assertEqual(sum(row.value for row in selected if row.value is not None),calculation.value)
                    self.assertEqual(len({row.original_sequence for row in selected}),3)
                output=self.root/uuid4().hex
                publication=result.write(output)
                target=published_file(publication,'contributions.'+fmt)
                if fmt=='csv':
                    with target.open(encoding='utf-8',newline='') as handle:
                        published=list(csv.DictReader(handle))
                else:
                    published=[json.loads(line)['row'] for line in target.read_text(encoding='utf-8').splitlines()]
                self.assertEqual(len(published),6)
                self.assertEqual(set(published[0]),set(rows[0].__dataclass_fields__))
                self.assertFalse(any(name.suffix=='.sort' for name in result.spool.path.rglob('*') if name.is_file()))
                budget=result.spool.budget
                result.close()
                self.assertEqual(budget.ram_bytes,0)

    def test_default_contributions_do_not_invoke_output_constructor(self):
        """关闭从生成处跳过；查询明确提示未生成，不能当作零条贡献。"""
        from chronaxis.results.errors import ContributionsUnavailableError
        path=self.fixtures()['can_asc']
        with patch('chronaxis.execution.record_session_calculations.SummaryContributionRow',side_effect=AssertionError('unused')):
            result=AnalysisRunner().run(AnalysisPlan.from_dict(current_fixture(self.plan('can_asc',path))),self.root/uuid4().hex)
        self.addCleanup(result.close)
        self.assertNotIn('contributions',result.spool.tables)
        self.assertFalse(result.contributions_available)
        with self.assertRaises(ContributionsUnavailableError):
            result.iter_contributions()
        result.close()

    def test_empty_input_remains_unknown(self):
        """没有匹配报文不是零能量。"""
        self.fixtures()
        raw=self.plan('can_asc',self.asc('').path)
        result=AnalysisRunner().run(AnalysisPlan.from_dict(current_fixture(raw)),self.root/uuid4().hex)
        self.addCleanup(result.close)
        self.assertTrue(all(r.value is None and r.reason=='no_evaluations' for r in result.iter_calculations()))
        result.close()

    def test_missing_decode_is_partial_not_carried_forward(self):
        """未定义子类型使本条失效，下一条正常继续；不会复用上一条4000W。"""
        self.dbc.write_text('VERSION ""\nNS_ :\nBS_:\nBU_: Node\n'
            'BO_ 256 Frame: 2 Node\n SG_ Kind M : 0|8@1+ (1,0) [0|255] "" Node\n'
            ' SG_ Power m1 : 8|8@1+ (1000,0) [0|255000] "W" Node\n',encoding='utf-8')
        paths=dict(can_blf=self.blf(((0.,bytes([1,4])),(.1,bytes([2,9])),(.2,bytes([1,4])))),
            can_asc=self.asc('0.0 1 100 Rx d 2 01 04\n0.1 1 100 Rx d 2 02 09\n0.2 1 100 Rx d 2 01 04\n').path,
            raw_can_csv=self.csv('0,100,01 04,2\n0.1,100,02 09,2\n0.2,100,01 04,2\n').path)
        for (kind,path),backend in product(paths.items(),('reference','numpy')):
            raw=self.plan(kind,path)
            raw['outputs']['contributions']='full'
            result=AnalysisRunner(backend).run(AnalysisPlan.from_dict(current_fixture(raw)),self.root/uuid4().hex)
            self.addCleanup(result.close)
            rows={row.calculation_id:row for row in result.iter_calculations()}
            self.assertEqual(rows['positive'].value,800.)
            self.assertEqual(rows['positive'].status,'partial')
            self.assertNotEqual(rows['positive'].quality,0)
            self.assertIsNone(rows['negative'].value)
            details=[row for row in result.iter_contributions() if row.calculation_id=='positive']
            self.assertEqual([row.value for row in details],[400.,None,400.])
            self.assertEqual(details[1].reason,'missing_input')
            result.close()

    def test_shared_input_time_integral_and_message_sum(self):
        """同次读取兼顾两种明确算法：逐消息800-200=600J，实际积分800J。"""
        path=self.fixtures()['can_asc']
        raw=self.plan('can_asc',path)
        raw['signals'][0]['valid_for']='1s'
        raw['dataset']['domain']=dict(start='0s',end='0.2s')
        raw['calculations']=[dict(name='integral',scope='session',operation='integral',expr='power',unit='J')]
        result=AnalysisRunner().run(AnalysisPlan.from_dict(current_fixture(raw)),self.root/uuid4().hex)
        self.addCleanup(result.close)
        rows={row.calculation_id:row.value for row in result.iter_calculations()}
        # 半开请求域不纳入0.2秒的负消息，但它可关闭积分记录对。
        self.assertEqual(rows,dict(positive=800.,negative=None,integral=800.))
        result.close()

    def test_cancel_after_message_does_not_publish_prefix(self):
        """实际消费一条后取消，原错传播；本次目录和预算均释放。"""
        from chronaxis.execution.current_message_calculation import CurrentMessageCalculation
        path=self.fixtures()['can_asc']
        original=CurrentMessageCalculation.consume
        budgets=[]
        def cancel(owner,updates):
            """在真实累计后中断。参数: owner/updates。返回: 不返回。异常: KeyboardInterrupt。"""
            original(owner,updates)
            budgets.append(owner._budget)
            raise KeyboardInterrupt('cancel after message')
        root=self.root/uuid4().hex
        raw=self.plan('can_asc',path)
        raw['outputs']['contributions']='full'
        with patch.object(CurrentMessageCalculation,'consume',cancel):
            with self.assertRaises(KeyboardInterrupt):
                AnalysisRunner().run(AnalysisPlan.from_dict(current_fixture(raw)),root)
        self.assertTrue(budgets)
        self.assertEqual(budgets[0].ram_bytes,0)
        self.assertFalse(root.exists())
