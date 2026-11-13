"""共用 BLF 读取器的独立行为预期；迁移不统一各入口的既有解码政策。"""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4
import unittest

from workspace_fixtures import TemporaryDirectory
from chronaxis import AnalysisPlan, AnalysisRunner
from chronaxis.results.budget import ResourceBudget
from chronaxis.sources.blf import BLFRead, BLFSpec
from chronaxis.sources.text_can_decode import CANTextDecodeRead
from chronaxis.sources.text_can_spec import CANTextSpec
from chronaxis.legacy.records import LegacyRawFrame
from chronaxis.sources.raw_can import RawCANRecord
import test_session_process_legacy as legacy_fixtures
import test_session_process_runtime as runtime_fixtures


class BLFConvergenceTests(unittest.TestCase):
    """实际公开读取与低层异常注入共同验证政策和资源；不碰历史输入。"""

    setUp=legacy_fixtures.SessionProcessLegacyTests.setUp
    fixture=legacy_fixtures.SessionProcessLegacyTests.fixture
    run_plan=legacy_fixtures.SessionProcessLegacyTests.run_plan

    def reader(self, plan, policy='requested'):
        """创建直读候选并完成同次 DBC 准备，供异常类型对照。"""
        source=plan.sources[0].config
        spec=CANTextSpec(source.name,tuple(BLFSpec(p,source.offset_ns) for p in source.input_paths),
            source.dbc_path,source.channel,source.timebase,source.decode_policy,'full')
        budget=ResourceBudget()
        read=CANTextDecodeRead(spec,budget,tuple(s.definition for s in plan.signals),
            legacy_blf_decode=source.decode_policy=='legacy',serial_blf_policy=policy,trace=False)
        read.prepare_metadata()
        return read,budget

    def test_public_serial_uses_shared_reader_without_vendor(self):
        """普通单 BLF 在新读取层得到 1J，旧 vendor loader 不再执行。"""
        plan=self.fixture(('blf',))
        with patch('chronaxis.legacy.worker._iter_blf',side_effect=AssertionError('旧读取器不应再启动')):
            self.assertEqual(self.run_plan(plan,1)[0][0][0],1.)

    def test_record_cursor_without_requirements_keeps_none_and_selected_time(self):
        """旧低层requirements省略仍可工作；消息消费者按真实domain选择是否采时间。"""
        from chronaxis.execution.record_source_cursor import RecordSourceCursor
        from chronaxis.core.models import Interval
        from chronaxis.planning.backend_selection import execution_plan
        for timed in (False,True):
            # 模拟Runner先解析auto，再把具体数值后端交给内部来源游标。
            plan=execution_plan(self.fixture(('blf',),'legacy'))
            if timed:plan=replace(plan,dataset=replace(plan.dataset,domain=Interval(0,3000000000),domain_explicit=True))
            definitions=tuple(item.definition for item in plan.signals)
            budget=ResourceBudget();updates=[]
            cursor=RecordSourceCursor(plan,plan.sources[0],definitions,{'power'},set(),budget,
                self.root/uuid4().hex,group_names=(),message_consumer=updates.append,
                message_keys=((0,256,None,None),))
            try:
                self.assertIsNone(cursor.peek())
                self.assertEqual([row.time_ns for row in updates],[0,1000000000] if timed else [None,None])
                self.assertEqual([row.sequence for row in updates],[0,1])
            finally:cursor.close()
            self.assertEqual(budget.ram_bytes,0)

    def test_unique_id_keeps_old_decoder_exception_policy(self):
        """三种长度政策均先核长度，再按旧唯一 ID 规则将普通异常记作缺值。"""
        for policy in ('legacy','strict','partial'):
            plan=self.fixture(('blf',),policy)
            read,budget=self.reader(plan)
            try:
                with patch.object(read._db,'decode_message',side_effect=RuntimeError('decoder sentinel')):
                    row=next(read)
                self.assertEqual(dict(row.values)[plan.signals[0].definition.field],None)
                self.assertEqual(read.decode_calls,1)
            finally:read.close()
            self.assertEqual(budget.ram_bytes,0)

    def test_duplicate_id_keeps_unexpected_decoder_failure(self):
        """同 ID 多定义不走数据库覆盖表，非 DecodeError 不被吞掉。"""
        plan=self.fixture(('blf',),'strict')
        source=plan.sources[0].config
        with source.dbc_path.open('a',encoding='utf-8') as stream:
            stream.write('BO_ 2147483904 Extended: 2 Node\n SG_ Power : 0|16@1+ (2,0) [0|131070] "W" Node\n')
        read,budget=self.reader(plan)
        message=next(m for m in read._db.messages if not m.is_extended_frame)
        try:
            with patch.object(message,'decode',side_effect=RuntimeError('duplicate sentinel')):
                with self.assertRaisesRegex(RuntimeError,'duplicate sentinel'):next(read)
        finally:read.close()
        self.assertEqual(budget.ram_bytes,0)

    def test_all_decodes_unrequested_frames_and_keeps_value_checks(self):
        """完整诊断仍解码未知 ID，并拒绝未请求字段的非数值返回；requested 不扩检查。"""
        plan=self.fixture(('blf',),'legacy')
        for scope in ('requested','all'):
            read,budget=self.reader(plan,scope)
            try:
                with patch.object(read._db,'decode_message',return_value={'Power':10,'Other':'invalid'}):
                    if scope=='all':
                        with self.assertRaises((TypeError,ValueError)):next(read)
                    else:self.assertEqual(dict(next(read).values)[plan.signals[0].definition.field],10)
            finally:read.close()
            self.assertEqual(budget.ram_bytes,0)

    def test_all_calls_decoder_for_unrequested_id(self):
        """同一目标加未知ID两帧：requested只解一次，all仍解两次。"""
        import can
        plan=self.fixture(('blf',),'legacy')
        with can.BLFWriter(plan.sources[0].config.path) as writer:
            for ident in (256,999):
                writer.on_message_received(can.Message(timestamp=1700000000,arbitration_id=ident,
                    is_extended_id=False,channel=0,data=b'\x0a\x00'))
        for scope,expected in (('requested',1),('all',2)):
            read,budget=self.reader(plan,scope)
            try:
                self.assertEqual(len(tuple(read)),2)
                self.assertEqual(read.decode_calls,expected)
            finally:read.close()
            self.assertEqual(budget.ram_bytes,0)

    def test_unselected_native_skips_time_but_custom_message_keeps_full_check(self):
        """按需无时间模式跳过原生无关帧；自定义消息仍走既有完整校验回退。"""
        import can
        native=can.Message(timestamp=float('nan'),arbitration_id=999,is_extended_id=False,channel=0,data=b'\x01')
        custom=SimpleNamespace(**{name:getattr(native,name) for name in ('timestamp','arbitration_id',
            'is_extended_id','is_remote_frame','is_error_frame','channel','dlc','data','is_fd','is_rx',
            'bitrate_switch','error_state_indicator')})
        path=self.root/'fallback.blf';path.write_bytes(b'placeholder')
        for frame,fails in ((native,False),(custom,True)):
            class Reader:
                def __iter__(self):yield frame
                def stop(self):pass
            budget=ResourceBudget()
            with patch('can.BLFReader',return_value=Reader()):
                read=BLFRead(BLFSpec(path),budget,binary_time=True,projection_only=True,
                    emit_frame_ids=(256,),time_scope='none')
                try:
                    if fails:
                        with self.assertRaises((TypeError,ValueError)):next(read)
                    else:self.assertEqual(tuple(read),())
                finally:read.close()
            self.assertEqual(budget.ram_bytes,0)

    def test_fast_raw_mode_does_not_read_unneeded_time(self):
        """原消息模式只借真实消息，不因共用读取层访问未请求的时间属性。"""
        class Message:
            @property
            def timestamp(self):raise AssertionError('无时间消费者不读取时间')
        message=Message()
        path=self.root/'raw.blf';path.write_bytes(b'placeholder')
        class Reader:
            def __iter__(self):yield message
            def stop(self):pass
        budget=ResourceBudget()
        with patch('can.BLFReader',return_value=Reader()):
            read=BLFRead(BLFSpec(path),budget,frame_only=True)
            self.assertIs(next(read),message)
            read.close()
        self.assertEqual(budget.ram_bytes,0)

    def test_explain_reports_real_serial_and_parallel_schedule(self):
        """串行在宿主内执行报0；多文件或time_order按实际工作槽报告上限。"""
        from chronaxis.planning.process_execution import source_execution_facts
        for count in (1,4):
            for size in (1,2):
                for merge in ('concatenate','time_order'):
                    plan=self.fixture(('blf',)*size,'strict')
                    source=plan.sources[0]
                    plan=replace(plan,sources=(replace(source,config=replace(source.config,file_merge=merge)),),
                        execution=replace(plan.execution,process_count=count))
                    expected=min(count,size) if merge=='time_order' or min(count,size)>1 else 0
                    self.assertEqual(source_execution_facts(plan)[0]['read_process_limit'],expected)

    def test_header_failure_closes_file_and_refunds(self):
        """库在返回 reader 前报错，BLF owner 已拥有实际文件并负责关闭。"""
        path=self.root/'broken.blf';path.write_bytes(b'bad')
        files=[]
        def fail(stream):
            files.append(stream)
            raise ValueError('broken header')
        budget=ResourceBudget()
        with patch('can.BLFReader',side_effect=fail):
            with self.assertRaisesRegex(ValueError,'broken header'):
                BLFRead(BLFSpec(path),budget,frame_only=True)
        self.assertTrue(files[0].closed)
        self.assertEqual(budget.ram_bytes,0)

    def test_binary_time_matches_old_exact_float_conversion(self):
        """纯 BLF 串行保原二进制 float 秒换算，不改为十进制字符串时间。"""
        plan=self.fixture(('blf',),'legacy')
        import can
        with can.BLFWriter(plan.sources[0].config.path) as writer:
            writer.on_message_received(can.Message(timestamp=1700000000.1,arbitration_id=256,is_extended_id=False,channel=0,data=b'\x0a\x00'))
        read,budget=self.reader(plan)
        try:
            from chronaxis.execution.can_batch_reader import _float_seconds_ns
            row=next(read)
            self.assertEqual(row.raw.time_ns,_float_seconds_ns(row.raw.frame.timestamp)[0]+plan.sources[0].config.offset_ns)
        finally:read.close()
        self.assertEqual(budget.ram_bytes,0)


class PureBLFContinuousTests(unittest.TestCase):
    """复用独立手算的连续分析断言，但只执行本类三项纯 BLF 差分。"""

    setUp=runtime_fixtures.SessionProcessRuntimeTests.setUp
    file=runtime_fixtures.SessionProcessRuntimeTests.file
    plan=runtime_fixtures.SessionProcessRuntimeTests.plan
    run_plan=runtime_fixtures.SessionProcessRuntimeTests.run_plan

    def test_pure_blf_continuous_same_time_and_empty(self):
        """同刻跨卷、空卷和连续 TTL 不因串行迁移改变事件或积分。"""
        for parts in ([[(0,10),(1,20)],[(2,30),(3,40)]],
                      [[(0,10),(1,20)],[],[(1,30),(3,40)]]):
            plan=self.plan(parts,'blf')
            for count in (1,4):
                value=self.run_plan(plan,count)
                if count==1:baseline=value
                else:self.assertEqual(value,baseline)

    def test_pure_blf_unselected_tail_preserves_ttl(self):
        """0/1 秒 10/20W，尾帧 5 秒，2 秒有效期：已知积分 50J 且 partial。"""
        runtime_fixtures.SessionProcessRuntimeTests.test_unselected_blf_tail_preserves_observation_and_expiry(self)

    def test_unselected_first_frame_cannot_hide_cross_file_regression(self):
        """来源时间需要全检时，第二文件开头的无关回退帧仍失败。"""
        import can
        from chronaxis.results import AnalysisError
        plan=self.plan([[(0,10),(1,20)],[(2,30),(3,40)]],'blf')
        path=plan.sources[0].config.input_paths[1]
        with can.BLFWriter(path) as writer:
            for stamp,ident,value in ((.5,257,0),(2,256,30),(3,256,40)):
                writer.on_message_received(can.Message(timestamp=1700000000+stamp,
                    arbitration_id=ident,is_extended_id=False,channel=0,data=bytes([value])))
        for input_check,scope in (('auto','requested'),('full','requested'),('full','all')):
            source=plan.sources[0]
            current=replace(plan,sources=(replace(source,config=replace(source.config,
                input_check=input_check,decode_scope=scope)),))
            with self.subTest(input_check=input_check,scope=scope):
                with self.assertRaisesRegex(AnalysisError,'时间回退'):
                    self.run_plan(current,1)

    def test_pure_blf_raw_export(self):
        """串行与并行原帧导出均沿同次读取，没有重新读取原文件。"""
        runtime_fixtures.SessionProcessRuntimeTests.test_raw_blf_export_reuses_original_frames(self)


if __name__=='__main__':unittest.main()
