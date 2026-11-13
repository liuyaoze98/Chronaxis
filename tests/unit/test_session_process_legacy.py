"""以正常、短帧和未知复用编号核对纯BLF串行/并行政策；ASC和混合来源保持原检查。

合成文件写入独占工作目录。每次运行核资源释放，测试不更改原DBC或历史读取实现。
"""
from pathlib import Path
from workspace_fixtures import TemporaryDirectory
from uuid import uuid4
import multiprocessing
import unittest
from unittest.mock import patch

from chronaxis import AnalysisPlan, AnalysisRunner
from chronaxis.results import AnalysisError


class SessionProcessLegacyTests(unittest.TestCase):
    """按公开配置选择来源，比较改变进程上限前后的结果与失败处理。"""

    def setUp(self):
        """建立独占夹具目录。参数: 无。返回: None。异常: IO错误。"""
        self.directory=TemporaryDirectory(dir='work',prefix='session-legacy-test-')
        self.addCleanup(self.directory.cleanup)
        self.root=Path(self.directory.name).resolve()

    def fixture(self, kinds, policy='legacy', *, mux=False):
        """生成每文件1条有效及1条无值报文。参数: 格式列表/政策/复用例。返回: 计划。异常: IO/配置错误。"""
        import can
        dbc=self.root/(uuid4().hex+'.dbc')
        signals=(' SG_ Mux M : 0|8@1+ (1,0) [0|255] "" Node\n'
                 ' SG_ Power m1 : 8|8@1+ (1,0) [0|255] "W" Node\n' if mux else
                 ' SG_ Power : 0|16@1+ (1,0) [0|65535] "W" Node\n')
        dbc.write_text('VERSION ""\nNS_ :\nBS_:\nBU_: Node\nBO_ 256 Frame: 2 Node\n'+signals,encoding='utf-8')
        paths=[]
        for i,kind in enumerate(kinds):
            path=self.root/(uuid4().hex+'.'+kind);paths.append(str(path))
            payloads=(bytes([1,10*(i+1)]),bytes([2,99])) if mux else (bytes([10*(i+1),0]),b'')
            frames=[can.Message(timestamp=1700000000+i*2+j,arbitration_id=256,
                is_extended_id=False,channel=0,data=data) for j,data in enumerate(payloads)]
            if kind=='blf':
                with can.BLFWriter(path) as writer:
                    for frame in frames:writer.on_message_received(frame)
            else:
                path.write_text('base hex timestamps absolute\n'+''.join(
                    f'{f.timestamp:.0f} 1 100 Rx d {len(f.data)} {f.data.hex(" ")}\n' for f in frames),encoding='utf-8')
        source=dict(paths=paths,dbc_by_channel={'1':str(dbc)},reader=dict(decode_policy=policy),
                    time=dict(offset='-1700000000s'))
        if all(kind=='blf' for kind in kinds):source['source_type']='can_blf'
        return AnalysisPlan.from_dict(dict(config_version=4,dataset=dict(name='legacy'),sources=[source],
            signals=[dict(name='power',field=dict(frame_id=256,signal='Power'),valid_for='2s')],
            message_calculations=[dict(name='energy',update_message=dict(frame_id=256),
                parameters=dict(period=dict(value=.1,unit='s')),expr='power * period',unit='J')],
            outputs=dict(contributions='full')))

    def run_plan(self, plan, count):
        """运行并保留必要值/贡献供比较。参数: 计划/进程上限。返回: tuple。异常: 原运行或断言错误。"""
        before={p.pid for p in multiprocessing.active_children()}
        with AnalysisRunner().run(plan,work_dir=self.root/uuid4().hex,process_count=count) as result:
            calculations=[(r.value,r.unit,r.status,r.reason) for r in result.iter_calculations()]
            contributions=[(r.original_sequence,r.value,r.reason) for r in result.iter_contributions()]
            budget=result.spool.budget
        self.assertEqual(budget.ram_bytes,0)
        self.assertEqual({p.pid for p in multiprocessing.active_children()},before)
        return calculations,contributions

    def test_single_file_upper_limit_does_not_replace_legacy_reader(self):
        """一份文件设上限4仍走原读取器，短帧跳过后保持1J。"""
        plan=self.fixture(('blf',));baseline=self.run_plan(plan,1)
        self.assertEqual(baseline[0][0][0],1.)
        with patch('chronaxis.execution.parallel_can_decode.ParallelCANDecodeRead',
                   side_effect=AssertionError('单文件不应新建并行读取器')):
            self.assertEqual(self.run_plan(plan,4),baseline)

    def test_two_blf_legacy_short_frames_and_decode_errors_match(self):
        """两文件正常值分别10/20W，短帧或未知mux都不贡献，串并行均3J。"""
        for mux in (False,True):
            with self.subTest(mux=mux):
                plan=self.fixture(('blf','blf'),mux=mux);baseline=self.run_plan(plan,1)
                self.assertEqual(baseline[0][0][0],3.)
                self.assertEqual(self.run_plan(plan,4),baseline)

    def test_asc_and_mixed_legacy_still_reject_short_frames(self):
        """保留文本和混合路径的legacy长度检查，不按后缀自动启用纯BLF适配。"""
        for kinds in (('asc','asc'),('blf','asc')):
            plan=self.fixture(kinds)
            for count in (1,4):
                with self.subTest(kinds=kinds,count=count):
                    with self.assertRaisesRegex(AnalysisError,'长度不一致'):
                        self.run_plan(plan,count)
                    self.assertFalse(multiprocessing.active_children())

    def test_blf_strict_and_partial_keep_their_policies(self):
        """strict在两种进程上限拒绝短帧，partial允许已存在字段且缺值不贡献。"""
        strict=self.fixture(('blf','blf'),'strict')
        for count in (1,4):
            with self.assertRaisesRegex(AnalysisError,'长度不一致'):
                self.run_plan(strict,count)
            self.assertFalse(multiprocessing.active_children())
        partial=self.fixture(('blf','blf'),'partial')
        baseline=self.run_plan(partial,1)
        self.assertEqual(baseline[0][0][0],3.)
        self.assertEqual(self.run_plan(partial,4),baseline)

    def test_metadata_identifies_only_explicit_blf_legacy_adapter(self):
        """内部适配标注legacy且拒绝ASC规格；普通BLF文本读取仍标exact。"""
        from chronaxis.execution.parallel_can_decode import ParallelCANDecodeRead
        from chronaxis.sources.text_can_decode import CANTextDecodeRead
        from chronaxis.sources.text_can_spec import CANTextSpec
        from chronaxis.sources.blf import BLFSpec
        from chronaxis.sources.asc import ASCSpec
        from chronaxis.results.budget import ResourceBudget
        plan=self.fixture(('blf','blf'));source=plan.sources[0].config
        spec=CANTextSpec(source.name,tuple(BLFSpec(p,source.offset_ns) for p in source.input_paths),
                         source.dbc_path,source.channel,source.timebase,decode_policy='legacy')
        signals=tuple(s.definition for s in plan.signals)
        for compatible,expected in ((False,'exact'),(True,'legacy')):
            budget=ResourceBudget()
            # 默认文本政策只核元数据，避免故意短帧的预读错误抢先终止本项检查。
            reader=(ParallelCANDecodeRead(spec,budget,signals,process_count=2,
                work_dir=self.root/uuid4().hex,legacy_blf_decode=True) if compatible else
                CANTextDecodeRead(spec,budget,signals))
            try:self.assertEqual(reader.prepare_metadata()['selected_length_check'],expected)
            finally:reader.close()
            self.assertEqual(budget.ram_bytes,0)
        bad=CANTextSpec(source.name,(ASCSpec(self.root/'invalid.asc'),),source.dbc_path,
                        source.channel,source.timebase,decode_policy='legacy')
        budget=ResourceBudget()
        with self.assertRaisesRegex(ValueError,'纯BLF'):
            CANTextDecodeRead(bad,budget,signals,legacy_blf_decode=True)
        self.assertEqual(budget.ram_bytes,0)


if __name__=='__main__':
    unittest.main()
