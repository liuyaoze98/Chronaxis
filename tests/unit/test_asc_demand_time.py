"""核对按需ASC时间顺序、全来源观测范围及失败清理。

使用小型合成报文，目标ID为0x100；无关帧不进入计算，但其原始时间仍决定
实际来源范围。仅写新项目work目录，不修改用户日志；预期时间/积分由手算给出。
"""
from dataclasses import replace
from decimal import localcontext
import unittest

from chronaxis import AnalysisPlan, AnalysisRunner
from chronaxis.sources.asc import ASCRead, ASCSpec
from chronaxis.sources.raw_can import CANTextError
from chronaxis.results.errors import AnalysisError
import test_text_can_decode as fixtures


class ASCDemandTimeTests(unittest.TestCase):
    """使用真实DBC和解析器验证消费者所需序列，不排序也不重写报文。"""
    setUp = fixtures.TextCANDecodeTests.setUp
    asc = fixtures.TextCANDecodeTests.asc
    reader = fixtures.TextCANDecodeTests.reader

    def test_unrelated_rollback_keeps_source_bounds_and_original_positions(self):
        """参数: 无。返回: None。异常: 断言失败；无关帧前后端仍计入观测范围。"""
        parser=self.asc('0 2 777 Tx d 0\n1 1 100 Rx d 2 01 00\n'
            '2 2 777 Tx d 0\n1.999999 2 777 Tx d 0\n3 1 100 Rx d 2 03 00\n'
            '9 2 777 Tx d 0\n8.999999 2 777 Tx d 0\n')
        with self.reader((parser,),time_frame_ids=(256,)) as read:
            rows=list(read)
            self.assertEqual([row.raw.time_ns for row in rows],[10**9,3*10**9])
            self.assertEqual([row.sequence for row in rows],[1,4])
            self.assertEqual((read.first_ns,read.last_ns,read.count,read.retained_count),(0,9*10**9,7,2))
            self.assertEqual(read.metadata['time_order_check_scope'],'selected_ids')
        self.assertEqual(self.budget.ram_bytes,0)

    def test_target_and_cross_file_rollback_remain_errors(self):
        """参数: 无。返回: None。异常: 断言失败；无关帧不能掩盖目标回退。"""
        for files in (
                (self.asc('1 1 100 Rx d 2 01 00\n0.999999 1 100 Rx d 2 03 00\n'),),
                (self.asc('1 1 100 Rx d 2 01 00\n'),self.asc('0.999999 1 100 Rx d 2 03 00\n'))):
            with self.subTest(files=len(files)):
                with self.assertRaisesRegex(CANTextError,'回退'):
                    with self.reader(files,time_frame_ids=(256,)) as read:
                        list(read)
                self.assertEqual(self.budget.ram_bytes,0)

    def test_cross_file_subnanosecond_rollback_survives_empty_files(self):
        """参数: 无。返回: None。异常: 断言失败；舍入相同与空分卷不能抹掉回退。"""
        inputs=(self.asc('0.0000000012 1 100 Rx d 2 01 00\n'),self.asc(''),
                self.asc('0.0000000011 1 100 Rx d 2 03 00\n'))
        for options in ({},{'time_frame_ids':(256,)}):
            with self.subTest(scope=options):
                with self.assertRaisesRegex(CANTextError,'回退') as caught:
                    with self.reader(inputs,**options) as read:
                        list(read)
                self.assertEqual(caught.exception.path,inputs[-1].path)
                self.assertEqual(self.budget.ram_bytes,0)

    def test_exact_cross_file_comparison_uses_offsets_and_dates(self):
        """参数: 无。返回: None。异常: 断言失败；偏移和跨午夜都先转到同一分析轴。"""
        first=self.asc('1.0000000012 1 100 Rx d 2 01 00\n')
        for suffix,allowed in (('11',False),('12',True),('13',True)):
            second=self.asc(f'0.00000000{suffix} 1 100 Rx d 2 03 00\n',offset_ns=10**9)
            for options in ({},{'time_frame_ids':(256,)}):
                with self.subTest(suffix=suffix,scope=options):
                    if allowed:
                        with self.reader((first,second),**options) as read:
                            self.assertEqual([row.raw.time_ns for row in read],[1000000001]*2)
                    else:
                        with self.assertRaisesRegex(CANTextError,'回退'):
                            with self.reader((first,second),**options) as read:
                                list(read)
                    self.assertEqual(self.budget.ram_bytes,0)
        inputs=(self.asc('date Wed Jan 01 23:59:59.000 2025\n'
                        '1.0000000012 1 100 Rx d 2 01 00\n',time_reference='epoch',timezone_offset_minutes=0),
                self.asc('date Thu Jan 02 00:00:00.000 2025\n'
                         '0.0000000011 1 100 Rx d 2 03 00\n',time_reference='epoch',timezone_offset_minutes=0))
        for options in ({},{'time_frame_ids':(256,)}):
            with self.assertRaisesRegex(CANTextError,'回退'):
                with self.reader(inputs,**options) as read:
                    list(read)
            self.assertEqual(self.budget.ram_bytes,0)

    def test_relative_and_metadata_keep_only_required_boundary(self):
        """参数: 无。返回: None。异常: 断言失败；full保元数据检查，按需只延续目标时刻。"""
        for tail in ('0.0000000006 2 777 Tx d 0','0.0000000006 Start of measurement'):
            first=self.asc('0.0000000006 1 100 Rx d 2 01 00\n'+tail+'\n')
            first.path.write_text(first.path.read_text().replace('timestamps absolute','timestamps relative'))
            second=self.asc('0.0000000011 1 100 Rx d 2 03 00\n')
            with self.reader((first,second),time_frame_ids=(256,)) as read:
                self.assertEqual([row.raw.time_ns for row in read],[1,1])
            with self.assertRaisesRegex(CANTextError,'回退'):
                with self.reader((first,second)) as read:
                    list(read)
            self.assertEqual(self.budget.ram_bytes,0)

    def test_cancel_after_cross_file_state_transfer_cleans_up(self):
        """参数: 无。返回: None。异常: 原取消类型；第二文件打开后取消不遗留预算。"""
        class Cancel(RuntimeError):
            """验证取消不会被时间诊断替换。"""
        calls=[0]
        def cancel():
            """参数: 无。返回: None。异常: Cancel在第二文件数据行读取前触发。"""
            calls[0]+=1
            if calls[0]==7:
                raise Cancel('cancel second input')
        inputs=(self.asc('0.0000000012 1 100 Rx d 2 01 00\n'),
                self.asc('0.0000000013 1 100 Rx d 2 03 00\n'))
        with self.assertRaisesRegex(Cancel,'second input'):
            with self.reader(inputs,time_frame_ids=(256,),check_cancel=cancel) as read:
                self.assertEqual(next(read).raw.time_ns,1)
                next(read)
        self.assertEqual(calls[0],7)
        self.assertEqual(self.budget.ram_bytes,0)

    def test_non_asc_boundary_does_not_use_callers_decimal_precision(self):
        """参数: 无。返回: None。异常: 断言失败；新增比较状态不能把1.25/1.24舍入相同。"""
        first=fixtures.TextCANDecodeTests.csv(self,'1.25,100,01 00,2\n')
        for time in ('1.24','1.26'):
            second=fixtures.TextCANDecodeTests.csv(self,f'{time},100,03 00,2\n')
            with localcontext() as context:
                context.prec=2
                if time=='1.24':
                    with self.assertRaisesRegex(CANTextError,'回退'):
                        with self.reader((first,second)) as read:
                            list(read)
                else:
                    with self.reader((first,second)) as read:
                        self.assertEqual([row.raw.time_ns for row in read],[1250000000,1260000000])
            self.assertEqual(self.budget.ram_bytes,0)

    def test_cross_file_ignores_only_unrelated_boundary_and_empty_selection(self):
        """参数: 无。返回: None。异常: 断言失败；必要序列跨卷延续，空选择仍有来源范围。"""
        inputs=(self.asc('1 1 100 Rx d 2 01 00\n5 2 777 Tx d 0\n'),
                self.asc('4 1 100 Rx d 2 03 00\n6 2 777 Tx d 0\n'))
        with self.reader(inputs,time_frame_ids=(256,)) as read:
            self.assertEqual([row.raw.time_ns for row in read],[10**9,4*10**9])
            self.assertEqual((read.first_ns,read.last_ns),(10**9,6*10**9))
        with self.reader(inputs,time_frame_ids=()) as read:
            self.assertEqual(list(read),[])
            self.assertEqual((read.first_ns,read.last_ns,read.count),(10**9,6*10**9,4))
        self.assertEqual(self.budget.ram_bytes,0)

    def test_full_default_still_checks_unrelated_rollback(self):
        """参数: 无。返回: None。异常: 断言失败；低层未选择时沿用完整顺序检查。"""
        parser=self.asc('1 1 100 Rx d 2 01 00\n0.999999 2 777 Tx d 0\n')
        with self.assertRaisesRegex(CANTextError,'回退'):
            with self.reader((parser,)) as read:
                list(read)
        self.assertEqual(self.budget.ram_bytes,0)

    def test_relative_deltas_and_midnight_remain_exact(self):
        """参数: 无。返回: None。异常: 断言失败；未选帧增量不丢，日期跨日不归零。"""
        relative=self.asc('0.1 1 100 Rx d 2 01 00\n0.2 2 777 Tx d 0\n0.3 1 100 Rx d 2 03 00\n')
        relative.path.write_text(relative.path.read_text().replace('timestamps absolute','timestamps relative'))
        with self.reader((relative,),time_frame_ids=(256,)) as read:
            self.assertEqual([row.raw.time_ns for row in read],[100000000,600000000])
        midnight=self.asc('Begin Triggerblock Wed Jan 01 23:59:59.000 2025\n'
            '0.5 1 100 Rx d 2 01 00\nEnd TriggerBlock\n'
            'Begin Triggerblock Thu Jan 02 00:00:00.000 2025\n0.1 1 100 Rx d 2 03 00\n')
        with self.reader((midnight,),time_frame_ids=(256,)) as read:
            self.assertEqual([row.raw.time_ns for row in read],[500000000,1100000000])
        self.assertEqual(self.budget.ram_bytes,0)

    def test_selected_subnanosecond_rollback_and_cancellation(self):
        """参数: 无。返回: None。异常: 断言失败；按需不放宽精度或取消清理。"""
        parser=self.asc('0.0000000012 1 100 Rx d 2 01 00\n0.0000000011 1 100 Rx d 2 03 00\n')
        with self.assertRaisesRegex(CANTextError,'回退'):
            with self.reader((parser,),time_frame_ids=(256,)) as read:
                list(read)
        class Cancel(Exception):
            """只用来确认原取消异常不被输入错误替换。"""
        calls=[0]
        def cancel():
            """参数: 无。返回: None。异常: Cancel在第一次帧后中断。"""
            calls[0]+=1
            if calls[0]>=4:
                raise Cancel('cancel requested')
        parser=self.asc('1 1 100 Rx d 2 01 00\n2 1 100 Rx d 2 03 00\n')
        with self.assertRaises(Cancel):
            with self.reader((parser,),time_frame_ids=(256,),check_cancel=cancel) as read:
                list(read)
        self.assertEqual(self.budget.ram_bytes,0)

    def config(self, parser, *, full=False, frames=False):
        """参数: parser输入，full完整检查，frames原帧导出。返回: 公共配置。异常: 无。"""
        result={'config_version':3,'dataset':{'name':'time_check'},
            'sources':[{'name':'bus','path':str(parser.path.resolve()),
                'dbc_by_channel':{'1':str(self.dbc.resolve())}}],
            'signals':[{'name':'voltage','source':'bus',
                'field':{'frame_id':'0x100','signal':'Voltage'},'unit':'V','valid_for':'10s'}],
            'calculations':[{'name':'area','operation':'integral','expr':'voltage','unit':'V*s'}]}
        if full: result['sources'][0]['reader']={'input_check':'full'}
        if frames:
            result['outputs']={'can_frames':{'source':'bus','format':'asc'}}
            result['metadata']={'device_label':'home'}
        return result

    def test_public_runner_ignores_unrelated_order_but_retains_tail(self):
        """参数: 无。返回: None。异常: 断言失败；两后端手算3V×1s+7V×1s=10Vs。"""
        parser=self.asc('0 1 100 Rx d 2 01 00\n1 1 100 Rx d 2 03 00\n'
            '2 2 777 Tx d 0\n1.999999 2 777 Tx d 0\n')
        for backend in ('reference','numpy'):
            plan=AnalysisPlan.from_dict(self.config(parser))
            with AnalysisRunner(backend=backend).run(plan) as result:
                rows=list(result.iter_calculations())
                self.assertEqual(rows[0].value,10)
        # 显式完整检查及原帧导出均要保留全来源顺序，不能静默忽略坏序。
        for options in ({'full':True},{'frames':True}):
            with self.subTest(options=options):
                plan=AnalysisPlan.from_dict(self.config(parser,**options))
                with self.assertRaisesRegex(AnalysisError,'回退'):
                    with AnalysisRunner().run(plan): pass
