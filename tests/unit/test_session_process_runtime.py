"""以实际ASC/BLF小文件验证连续会话并行读取；能量独立手算。

本次专用工作目录保存夹具，输入只读。比较原串行、并行拼接及时间归并，
同时检查事件跨文件连续、同刻组和资源归零，不把进程已启动等同于计算正确。
"""
from copy import deepcopy
from pathlib import Path
from workspace_fixtures import TemporaryDirectory
from uuid import uuid4
import unittest
from unittest.mock import patch
import multiprocessing

from chronaxis import AnalysisPlan, AnalysisRunner
from chronaxis.results import AnalysisError


class SessionProcessRuntimeTests(unittest.TestCase):
    """一个分析任务维护完整信号/事件状态，文件切换只改变来源定位。"""

    def setUp(self):
        """建立简单功率DBC及独占目录。参数: 无。返回: None。异常: IO。
        """
        self.directory=TemporaryDirectory(dir='work',prefix='session-process-test-')
        self.addCleanup(self.directory.cleanup)
        self.root=Path(self.directory.name).resolve()
        self.dbc=self.root/'fixture.dbc'
        self.dbc.write_text('VERSION ""\nNS_ :\nBS_:\nBU_: Node\nBO_ 256 Frame: 1 Node\n'
            ' SG_ Power : 0|8@1+ (1,0) [0|255] "W" Node\n',encoding='utf-8')

    def file(self,rows,kind):
        """把给定秒/功率写入合成输入。参数: rows/kind。返回: Path。异常: IO或编码错误。
        """
        path=self.root/(uuid4().hex+'.'+kind)
        if kind=='asc':
            path.write_text('base hex timestamps absolute\n'+''.join(
                f'{stamp} 1 100 Rx d 1 {value:02x}\n' for stamp,value in rows),encoding='utf-8')
        else:
            import can
            with can.BLFWriter(path) as writer:
                for stamp,value in rows:
                    writer.on_message_received(can.Message(timestamp=1700000000+stamp,
                        arbitration_id=256,is_extended_id=False,channel=0,data=bytes([value])))
        return path

    def plan(self,parts,kind,merge='concatenate',*,same_time='last_by_sequence',raw_frames=False):
        """声明单会话、2秒有效期及持续活动。参数: 分卷记录/格式/归并。返回: AnalysisPlan。异常: 校验错误。
        """
        files=[self.file(rows,kind) for rows in parts]
        raw=dict(config_version=4,dataset=dict(name='continuous'),sources=[dict(name='bus',paths=[str(p) for p in files],
            file_merge=merge,dbc_by_channel={'1':str(self.dbc)},time=dict(offset='-1700000000s' if kind=='blf' else '0s'))],
            signals=[dict(name='power',field=dict(frame_id=256,signal='Power'),dtype='float64',unit='W',
                valid_for='2s',same_time_policy=same_time)],
            rules=[dict(name='active',rule_type='condition_duration',condition='power > 0',
                minimum_duration='1s',duration_comparison='>=')],
            calculations=[dict(name='energy',operation='integral',expr='power',unit='J')],outputs=dict(tables='jsonl'))
        if raw_frames:
            raw['outputs']['can_frames']=dict(source='bus',format='blf',scope='session',
                capture_date='2023-11-14',timezone='UTC')
            if raw_frames=='grid':
                raw['outputs']['can_frames']['resampling']=dict(period='500ms',max_gap='2s',
                    messages=[dict(frame_id=256,continuous=['Power'])])
            raw['metadata']=dict(device_label='home')
        return AnalysisPlan.from_dict(raw)

    def run_plan(self,plan,count):
        """运行并取最终有限摘要，核所有预算释放。参数: plan/count。返回: 指标和事件。异常: 原错误。
        """
        with AnalysisRunner().run(plan,self.root/uuid4().hex,process_count=count) as result:
            calculations=list(result.iter_calculations());events=list(result.iter_events())
            budget=result.spool.budget
        self.assertEqual(budget.ram_bytes,0)
        return calculations,events

    def test_continuous_split_preserves_event_and_integral(self):
        """0/1/2/3秒功率10/20/30/40：积分60J，活动跨两个文件保持一段。参数: 无。返回: None。异常: 断言。
        """
        for kind in ('asc','blf'):
            with self.subTest(kind=kind):
                plan=self.plan([[(0,10),(1,20)],[(2,30),(3,40)]],kind)
                baseline=self.run_plan(plan,1)
                self.assertEqual(baseline[0][0].value,60.)
                self.assertEqual(len(baseline[1]),1)
                for count in (2,4):
                    self.assertEqual(self.run_plan(plan,count),baseline)

    def test_wide_three_signal_blocks_preserve_strict_cross_file_duration(self):
        """三信号密集帧不能因一批64条超额失败；60秒排除，跨卷61秒保留244J。"""
        self.dbc.write_text('VERSION ""\nNS_ :\nBS_:\nBU_: Node\nBO_ 256 Frame: 3 Node\n'
            ' SG_ BatteryPackPower : 0|8@1+ (1,0) [0|255] "W" Node\n'
            ' SG_ BatteryChargeState : 8|8@1+ (1,0) [0|255] "1" Node\n'
            ' SG_ BatteryPackVoltage : 16|8@1+ (1,0) [0|255] "V" Node\n',encoding='utf-8')
        files=[]
        for start,end in ((0,70),(70,124)):
            path=self.root/f'wide-{start}.asc'
            path.write_text('base hex timestamps absolute\n'+''.join(
                f'{t} 1 100 Rx d 3 {4 if t<60 or 61<=t<122 else 0:02x} 02 28\n'
                for t in range(start,end)),encoding='utf-8')
            files.append(str(path))
        raw=dict(config_version=4,dataset=dict(name='wide'),
            sources=[dict(paths=files,dbc_by_channel={'1':str(self.dbc)})],
            signals=[dict(name=name,field=dict(frame_id=256,signal=field),valid_for='2s')
                for name,field in (('power','BatteryPackPower'),('state','BatteryChargeState'),
                                   ('voltage','BatteryPackVoltage'))],
            rules=[dict(name='active',rule_type='condition_duration',
                condition='state == 2 and voltage > 10 and power > 0',
                minimum_duration='60s',duration_comparison='>')],
            calculations=[dict(name='energy',operation='integral',scope=dict(rule='active'),expr='power')])
        baseline=self.run_plan(AnalysisPlan.from_dict(raw),1)
        self.assertEqual(baseline[0][0].value,244.)
        self.assertEqual([(e.start_ns,e.end_ns) for e in baseline[1]],[(61*10**9,122*10**9)])
        for merge in ('concatenate','time_order'):
            raw['sources'][0]['file_merge']=merge
            actual=self.run_plan(AnalysisPlan.from_dict(raw),4)
            self.assertEqual([(r.value,r.unit,r.status) for r in actual[0]],
                             [(r.value,r.unit,r.status) for r in baseline[0]])
            self.assertEqual([(r.start_ns,r.confirmed_ns,r.end_ns) for r in actual[1]],
                             [(r.start_ns,r.confirmed_ns,r.end_ns) for r in baseline[1]])
        self.assertFalse(multiprocessing.active_children())

    def test_trace_long_original_times_are_counted_and_transferred_in_order(self):
        """诊断保留的长时间原文也计费，不能使合法记录积成超过512KiB的包。"""
        from chronaxis.execution.parallel_can_decode import ParallelCANDecodeRead
        from chronaxis.results.budget import ResourceBudget
        # 零的长文本只有一位有效数字，合法且每条消息仍按原序号保留。
        parts=[[('0.'+'0'*15000,10) for _ in range(40)] for _ in range(2)]
        plan=self.plan(parts,'asc')
        budget=ResourceBudget()
        reader=ParallelCANDecodeRead(plan.sources[0].config,budget,
            tuple(s.definition for s in plan.signals),process_count=2,work_dir=self.root/uuid4().hex,
            emit_frame_ids=(256,),time_frame_ids=(256,),integrity=False,trace=True)
        self.addCleanup(reader.close)
        records=list(reader)
        self.assertEqual([r.sequence for r in records],list(range(80)))
        self.assertEqual([r.raw.raw_time for r in records],[t for part in parts for t,_ in part])
        self.assertEqual(reader.count,80)
        reader.close()
        self.assertEqual(budget.ram_bytes,0)
        self.assertFalse(multiprocessing.active_children())

    def test_time_order_independent_of_process_count(self):
        """两个内部有序但交错文件归并为0/1/2/3秒，单/多进程均为60J。参数: 无。返回: None。异常: 断言。
        """
        for kind in ('asc','blf'):
            plan=self.plan([[(0,10),(2,30)],[(1,20),(3,40)]],kind,'time_order')
            baseline=self.run_plan(plan,1)
            self.assertEqual(baseline[0][0].value,60.)
            self.assertEqual(self.run_plan(plan,2),baseline)

    def test_concatenate_rejects_overlap_and_cleans_workers(self):
        """按文件拼接不能掩盖回退；失败不发布结果。参数: 无。返回: None。异常: 断言。
        """
        plan=self.plan([[(0,10),(2,30)],[(1,20),(3,40)]],'asc')
        with self.assertRaisesRegex(AnalysisError,'时间回退'):
            self.run_plan(plan,2)

    def test_internal_regression_is_not_sorted_away(self):
        """time_order仍拒绝单个文件内部回退，不能全量排序修复。参数: 无。返回: None。异常: 断言。
        """
        plan=self.plan([[(0,10),(2,30),(1,20)],[(3,40)]],'asc','time_order')
        with self.assertRaises(AnalysisError):
            self.run_plan(plan,2)

    def test_same_time_cross_file_group_is_complete(self):
        """1秒两次更新保持到完整组才选最后值，积分为10+30=40J。参数: 无。返回: None。异常: 断言。
        """
        parts=[[(0,10),(1,20)],[(1,30),(2,40)]]
        for merge in ('concatenate','time_order'):
            plan=self.plan(parts,'asc',merge)
            self.assertEqual(self.run_plan(plan,2)[0][0].value,40.)
            bad=self.plan(parts,'asc',merge,same_time='error')
            with self.assertRaises(AnalysisError):
                self.run_plan(bad,2)

    def test_empty_file_does_not_reset_state(self):
        """中间空文件不使信号失效或事件分裂。参数: 无。返回: None。异常: 断言。
        """
        for merge in ('concatenate','time_order'):
            plan=self.plan([[(0,10),(1,20)],[],[(2,30),(3,40)]],'asc',merge)
            calculations,events=self.run_plan(plan,2)
            self.assertEqual(calculations[0].value,60.)
            self.assertEqual(len(events),1)

    def decoder(self,parts,*,merge='concatenate',quota=None):
        """创建直接读取owner供生命周期测试。参数: 分卷/归并/磁盘配额。返回: owner、账本。异常: 配置错。
        """
        from chronaxis.execution.parallel_can_decode import ParallelCANDecodeRead
        from chronaxis.results.budget import ResourceBudget
        plan=self.plan(parts,'asc',merge)
        budget=ResourceBudget(spool_quota_bytes=quota)
        reader=ParallelCANDecodeRead(plan.sources[0].config,budget,
            tuple(s.definition for s in plan.signals),process_count=2,work_dir=self.root/uuid4().hex,
            emit_frame_ids=(256,),time_frame_ids=(256,),integrity=False,trace=False)
        self.addCleanup(reader.close)
        return reader,budget

    def test_cancel_with_unconsumed_blocks_closes_only_owned_workers(self):
        """不接收预读块就取消，满管道也可关闭，全部费用释放。参数: 无。返回: None。异常: 断言。
        """
        before={p.pid for p in multiprocessing.active_children()}
        reader,budget=self.decoder([[(i,10) for i in range(600)],[(i+600,20) for i in range(600)]])
        reader.prepare_metadata()
        self.assertEqual(len(reader.timings['worker_pids']),2)
        reader.close()
        self.assertEqual(budget.ram_bytes,0)
        self.assertEqual({p.pid for p in multiprocessing.active_children()},before)

    def test_worker_crash_is_not_eof(self):
        """工作进程意外结束必须失败，不能把剩余记录作为完整来源。参数: 无。返回: None。异常: 断言。
        """
        reader,budget=self.decoder([[(i,10) for i in range(600)],[(i+600,20) for i in range(600)]])
        reader.prepare_metadata()
        process=reader._slots[0]['process'];process.terminate();process.join(2)
        with self.assertRaises(Exception):
            list(reader)
        reader.close()
        self.assertFalse(reader.exhausted)
        self.assertEqual(budget.ram_bytes,0)

    def test_spool_quota_failure_removes_owned_temporaries(self):
        """time_order每块写入前检查配额，失败无残余自有文件。参数: 无。返回: None。异常: 断言。
        """
        reader,budget=self.decoder([[(0,10),(2,30)],[(1,20),(3,40)]],merge='time_order',quota=1)
        with self.assertRaisesRegex(AnalysisError,'spool_quota_bytes'):
            list(reader)
        reader.close()
        self.assertEqual(budget.ram_bytes,0)
        self.assertFalse(list(reader._work_dir.glob('file-merge-*')))

    def test_processes_are_reused_and_original_counts_retained(self):
        """六文件只用两个PID，报文及原计数不丢不重复。参数: 无。返回: None。异常: 断言。
        """
        reader,budget=self.decoder([[(i,10)] for i in range(6)])
        records=list(reader)
        self.assertEqual(len(records),6)
        self.assertEqual(reader.count,6)
        self.assertEqual([r.input_index for r in records],list(range(6)))
        self.assertEqual([r.sequence for r in records],list(range(6)))
        self.assertEqual(len(set(reader.timings['worker_pids'])),2)
        reader.close()
        self.assertEqual(budget.ram_bytes,0)

    def test_unselected_blf_tail_preserves_observation_and_expiry(self):
        """末尾无关帧到5秒仍形成观测；2秒有效期到3秒后未知，已知能量50J。参数: 无。返回: None。异常: 断言。
        """
        import can
        plan=self.plan([[(0,10),(1,20)],[(5,0)]],'blf')
        path=plan.sources[0].config.input_paths[1]
        with can.BLFWriter(path) as writer:
            writer.on_message_received(can.Message(timestamp=1700000005,
                arbitration_id=257,is_extended_id=False,channel=0,data=b'\x00'))
        baseline=self.run_plan(plan,1)
        self.assertEqual(baseline[0][0].value,50.)
        self.assertEqual(baseline[0][0].status,'partial')
        self.assertEqual(self.run_plan(plan,2),baseline)

    def test_raw_blf_export_reuses_original_frames(self):
        """显式原帧导出在同一读取中完成；多进程与串行的报文内容一致。参数: 无。返回: None。异常: 断言。
        """
        import can
        plan=self.plan([[(0,10),(1,20)],[(2,30),(3,40)]],'blf',raw_frames=True)
        outputs=[]
        for count in (1,2):
            with AnalysisRunner().run(plan,self.root/uuid4().hex,process_count=count) as result:
                manifest=result.write(self.root/uuid4().hex)
                paths=list(manifest.output_dir.rglob('*.blf'))
                frames=[]
                for path in paths:
                    with can.BLFReader(path) as reader:
                        frames.extend((m.timestamp,m.arbitration_id,bytes(m.data)) for m in reader)
                outputs.append(frames)
        self.assertTrue(outputs[0])
        self.assertEqual(outputs[1],outputs[0])

    def test_frame_resampling_uses_same_file_decode(self):
        """重建帧所需物理值在worker同次解码得到，原串行与并行输出一致。参数: 无。返回: None。异常: 断言。
        """
        import can
        plan=self.plan([[(0,10),(1,20)],[(2,30),(3,40)]],'blf',raw_frames='grid')
        outputs=[]
        for count in (1,2):
            with AnalysisRunner().run(plan,self.root/uuid4().hex,process_count=count) as result:
                manifest=result.write(self.root/uuid4().hex)
                frames=[]
                for path in manifest.output_dir.rglob('*.blf'):
                    with can.BLFReader(path) as reader:
                        frames.extend((m.timestamp,m.arbitration_id,bytes(m.data)) for m in reader)
                outputs.append(frames)
        self.assertTrue(outputs[0])
        self.assertEqual(outputs[1],outputs[0])

    def test_message_only_concatenate_preserves_untimed_policy(self):
        """纯逐报文累计不需要时间，文件回退在1/2进程都不成为新错误。参数: 无。返回: None。异常: 断言。
        """
        paths=[str(self.file(rows,'blf')) for rows in ([(2,10)],[(1,20)])]
        plan=AnalysisPlan.from_dict(dict(config_version=4,dataset=dict(name='message'),
            sources=[dict(name='bus',paths=paths,dbc_by_channel={'1':str(self.dbc)})],
            signals=[dict(name='power',field=dict(frame_id=256,signal='Power'),dtype='float64',unit='W',valid_for='2s')],
            message_calculations=[dict(name='energy',source='bus',profile='sclicer-functions-v1',
                operation='legacy_sum',message_policy='current_message-v1',update_message=dict(channel=1,frame_id=256),
                expr='power * period',parameters=dict(period=dict(value=.01,unit='s')),unit='J')]))
        baseline=self.run_plan(plan,1)
        self.assertEqual(baseline[0][0].value,.3)
        self.assertEqual(self.run_plan(plan,2),baseline)

    def test_subnanosecond_file_boundary_preserves_exact_check(self):
        """两条ASC时间舍入后相同也不能掩盖文件边界的精确回退。参数: 无。返回: None。异常: 断言。
        """
        plan=self.plan([[('1.0000000004',10)],[('1.0000000003',20)]],'asc')
        for count in (1,2):
            with self.assertRaisesRegex(AnalysisError,'时间回退'):
                self.run_plan(plan,count)

    def test_public_cancel_reclaims_workers_before_propagating(self):
        """公共run收到取消时关闭已预读工作进程，再原样传播KeyboardInterrupt。参数: 无。返回: None。异常: 断言。
        """
        from chronaxis.execution.parallel_can_decode import ParallelCANDecodeRead
        before={p.pid for p in multiprocessing.active_children()}
        plan=self.plan([[(i,10) for i in range(600)],[(i+600,20) for i in range(600)]],'asc')
        interruption=KeyboardInterrupt('controlled session cancellation')
        with patch.object(ParallelCANDecodeRead,'_block',side_effect=interruption):
            with self.assertRaises(KeyboardInterrupt) as caught:
                self.run_plan(plan,2)
        self.assertIs(caught.exception,interruption)
        self.assertEqual({p.pid for p in multiprocessing.active_children()},before)

    def test_large_same_time_group_uses_shared_budget(self):
        """同刻组跨很多传输块仍受全任务预算限制，不按块分割或丢弃样本。参数: 无。返回: None。异常: 断言。
        """
        from dataclasses import replace
        plan=self.plan([[('0',10)]*6000,[('1',20)]],'asc')
        plan=replace(plan,execution=replace(plan.execution,memory_budget_bytes=64*1048576))
        with self.assertRaisesRegex(AnalysisError,'内存|RAM|预算'):
            self.run_plan(plan,2)
        self.assertFalse(multiprocessing.active_children())


if __name__=='__main__':
    unittest.main()
