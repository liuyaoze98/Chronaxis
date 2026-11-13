"""验证同一fast任务跨文件的顺序、资源、空值与公开入口；夹具为合成ASC/BLF。

所有输出位于项目work，DBC使用已有教学文件；结果按每帧400J手算，不用被测
累计器生成预期。真实十文件与正式性能在独立工具中运行。
"""
import json
from pathlib import Path
from workspace_fixtures import TemporaryDirectory
from threading import Event
from threading import Timer
import struct
import unittest
from unittest.mock import patch

from chronaxis.configuration import load_configuration
from chronaxis.fast.run import run
from chronaxis.fast.config import compile_config
from chronaxis.fast.session import run_session
from chronaxis.fast.blocks import encode, decode

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / 'Docs/Current/examples'
HEADER = 'date Mon Jan 01 00:00:00.000 2024\nbase hex timestamps absolute\ninternal events logged\n'


def crash_worker(control, data, cancel):
    """模拟工作进程突然退出。参数: 协议句柄/取消。返回: 无。异常: 直接退出。"""
    import os
    control.recv()
    os._exit(37)


def stalled_worker(control, data, cancel):
    """模拟正在读取的慢worker。参数: 协议/取消。返回: None。异常: 无。"""
    control.recv()
    cancel.wait(20)


def missing_block_worker(control, data, cancel):
    """谎报一个未交付块的EOF。参数: 协议/取消。返回: None。异常: 无。"""
    import os
    command = control.recv()
    # 协议字段本身合法，仍谎报一块未交付数据，专门验证父调度的缺块检查。
    count=len(command[2]['metrics'])
    facts=dict(raw=0,targets=[0]*count,valid=[0]*count,selected=[0]*count,
               kinds=[0]*count,compatible=[])
    control.send(('eof', command[1], 1, facts, {}, os.getpid()))
    cancel.wait(20)


def duplicate_offer_worker(control, data, cancel):
    """重复申请同一贡献块。参数: 协议/取消。返回: None。异常: 无。"""
    command = control.recv()
    control.send(('offer', command[1], 0, 32))
    control.recv()
    control.send(('offer', command[1], 0, 32))
    cancel.wait(20)


class FastSessionTests(unittest.TestCase):
    """从公开配置/API运行多文件，不把独立batch求和当作连续会话验证。"""

    def setUp(self):
        """创建隔离输入。参数: 无。返回: None。异常: 文件IO。"""
        self.temp = TemporaryDirectory(prefix='fast-session-test-', dir=ROOT/'work')
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.raw = load_configuration(EXAMPLES/'message-minimal.yaml').data
        self.raw['dataset'] = dict(name='one_session')
        self.raw['outputs'] = dict(tables='jsonl')
        self.raw['sources'][0]['dbc_by_channel']['1'] = str(EXAMPLES/'data/power.dbc')
        self.paths = [self.asc('a.asc', [0, 1]), self.asc('b.asc', [1, 2])]
        self.raw['sources'][0]['paths'] = [str(p) for p in self.paths]

    def asc(self, name, times, identifier='100'):
        """写合成4000W报文。参数: 名称/时间列表/ID。返回: 路径。异常: IO。"""
        path = self.folder/name
        path.write_text(HEADER+''.join(f'{time:.9f} 1 {identifier} Rx d 2 A0 0F\n' for time in times), encoding='ascii')
        return path

    def config(self, merge='concatenate', count=1, quota=None):
        """保存完整配置。参数: 合并/进程/可选配额。返回: 配置路径。异常: IO。"""
        self.raw['sources'][0]['file_merge'] = merge
        self.raw['execution'] = dict(process_count=count)
        if quota is not None:
            self.raw['execution']['spool_quota_bytes'] = quota
        path = self.folder/'analysis.json'
        path.write_text(json.dumps(self.raw), encoding='utf8')
        return path

    def result(self, path, **options):
        """读公开输出。参数: 配置及API选项。返回: 行list/清单dict。异常: 执行错误。"""
        manifest = run(path, self.folder/'output', work_dir=self.folder/'temporary', **options)
        data = json.loads(manifest.read_bytes())
        rows = [json.loads(line) for line in (manifest.parent/data['outputs'][0]['name']).read_text().splitlines()]
        return rows, data

    def test_same_session_all_process_counts_both_orders(self):
        """4条报文应为1600J；同刻两条均计入，进程数只改变工作上限。"""
        for merge in ('concatenate', 'time_order'):
            baseline = None
            for count in (1, 2, 4, 8):
                with self.subTest(merge=merge, count=count):
                    rows, report = self.result(self.config(merge, count))
                    self.assertEqual(rows[0]['value'], 1600.0)
                    if baseline is None:
                        baseline = rows
                    self.assertEqual(rows, baseline)
                    self.assertEqual(len(report['inputs']), 2)
                    self.assertEqual(len(report['execution']['worker_pids']), 0 if count == 1 else 2)
                    self.assertEqual(report['execution']['ram_estimated_bytes'], 0)

    def test_override_and_invalid_counts_without_mutation(self):
        """API覆盖不改文件，非法进程数在读取前拒绝。"""
        path = self.config(count=1)
        before = path.read_bytes()
        _, report = self.result(path, process_count=2)
        self.assertEqual(len(report['execution']['worker_pids']), 2)
        self.assertEqual(path.read_bytes(), before)
        for value in (True, False, 0, -1, 1.0, '2'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.result(path, process_count=value)

    def test_optional_spool_quota_pauses_but_required_spool_fails(self):
        """配额1字节不能写一块；拼接仍计算全部240万J，时间归并明确失败。"""
        for path in self.paths:
            self.asc(path.name, range(3000))
        from chronaxis.fast.session import FilePool
        from time import monotonic
        original_start=FilePool.start
        def start_with_backpressure(pool,*args,**kwargs):
            """先接到第二文件的真实报价，暂不消费第一文件，确定性建立背压。"""
            original_start(pool,*args,**kwargs)
            deadline=monotonic()+30
            while not any(slot.get('file')==1 and slot.get('paused') for slot in pool.slots):
                if monotonic()>deadline:
                    pool.close()
                    raise AssertionError('未收到第二文件的配额背压握手')
                pool.pump()
        with patch.object(FilePool,'start',new=start_with_backpressure):
            rows, report = self.result(self.config(count=2, quota=1))
        self.assertEqual(rows[0]['value'], 2400000.0)
        self.assertEqual(report['execution']['spool_written_bytes'], 0)
        self.assertGreater(report['execution']['prefetch_pauses'], 0)
        with self.assertRaisesRegex(Exception, 'spool_quota_bytes'):
            self.result(self.config('time_order', 2, 1))
        self.assertFalse(list((self.folder/'temporary').iterdir()))

    def test_empty_or_unmatched_member_does_not_invalidate_session(self):
        """一个空/无目标分卷不抹掉另一个文件的800J。"""
        for identifier, times in (('100', []), ('101', [1, 2])):
            self.asc('b.asc', times, identifier)
            rows, _ = self.result(self.config(count=2))
            self.assertEqual(rows[0]['value'], 800.0)
            self.assertEqual(rows[0]['status'], 'complete')

    def test_counts_are_per_calculation_and_domain(self):
        """目标在范围外时为null；完全无目标的另一个计算项不借用其他项计数。"""
        spec = compile_config(self.config())
        absent = dict(spec['metrics'][0], name='absent', frame_id=0x101)
        # 独立DBC增加另一个合法定义，避免静态绑定失败替代缺帧验收。
        dbc = self.folder/'two.dbc'
        dbc.write_text((EXAMPLES/'data/power.dbc').read_text()+'\nBO_ 257 Other: 2 E\n SG_ OtherPower : 0|16@1+ (1,0) [0|65535] "W" E\n', encoding='utf8')
        absent['signals'] = {k:dict(v, signal='OtherPower') for k,v in absent['signals'].items()}
        spec.pop('_dbc_digest')  # 此低层夹具显式换了DBC，不能沿用公开编译时的旧身份。
        spec.update(dbc=str(dbc), metrics=[spec['metrics'][0], absent], domain_ns=[10**9, 2*10**9])
        rows, _ = run_session(spec)
        self.assertEqual(rows[0]['value'], 800.0)
        self.assertIsNone(rows[1]['value'])
        self.assertEqual(rows[1]['reason'], 'no_target_frames')
        spec['domain_ns'] = [10*10**9, 11*10**9]
        rows, _ = run_session(spec)
        self.assertEqual(rows[0]['reason'], 'no_target_in_domain')

    def test_time_regression_checked_before_direction_and_domain(self):
        """时间归并拒绝目标2→1回退，即使两帧都在范围外；拼接无时间消费者可处理。"""
        self.asc('a.asc', [2, 1])
        rows, _ = self.result(self.config(count=2))
        self.assertEqual(rows[0]['value'], 1600.0)
        for count in (1, 2):
            with self.assertRaisesRegex(Exception, '时间回退'):
                self.result(self.config('time_order', count))

    def test_cancelled_before_start_does_not_publish(self):
        """预取消不发布结果，临时数据不残留。"""
        cancel = Event()
        cancel.set()
        with self.assertRaises(InterruptedError):
            self.result(self.config(count=2), cancel_event=cancel)
        self.assertFalse(list((self.folder/'output').glob('*manifest*')))

    def test_blocks_preserve_bits_and_detect_corruption(self):
        """binary64大数/小数/负零不舍入；校验和与身份错误拒绝。"""
        values = [1e16, -1e16, 1.0, -0.0, 1e-300]
        records = [(i, i, ((0, value, True),)) for i,value in enumerate(values)]
        payload = encode(3, 9, records)
        actual = list(decode(payload, 3, 9, 1))
        self.assertEqual([r[2][0][1].hex() for r in actual], [v.hex() for v in values])
        with self.assertRaises(ValueError):
            list(decode(payload, 3, 8, 1))
        corrupt = bytearray(payload)
        corrupt[-8] ^= 1
        with self.assertRaisesRegex(ValueError, '完整性'):
            list(decode(corrupt, 3, 9, 1))

    def test_float_order_through_inline_direct_and_spool(self):
        """依次加1e16、-1e16、1的结果为1；若按文件部分和会变0，检验真实数据路径。"""
        import can
        dbc = self.folder/'double.dbc'
        dbc.write_text('VERSION ""\nNS_ :\nBS_:\nBU_: E\nBO_ 256 Frame: 8 E\n'
                       ' SG_ Power : 0|64@1+ (1,0) [0|0] "W" E\nSIG_VALTYPE_ 256 Power : 2;\n', encoding='ascii')
        paths = []
        for index, values in enumerate(([1e16], [-1e16, 1.0])):
            path = self.folder/f'float-{index}.blf'
            with can.BLFWriter(path) as writer:
                for position,value in enumerate(values):
                    writer.on_message_received(can.Message(timestamp=1704067200+index+position*.1,
                        channel=0,arbitration_id=256,is_extended_id=False,data=struct.pack('<d',value)))
            paths.append(str(path))
        self.raw['sources'][0].update(paths=paths, dbc_by_channel={'1':str(dbc)})
        self.raw['message_calculations'][0]['parameters']['period']['value'] = 1.0
        for merge,count,quota in (('concatenate',1,None),('concatenate',2,1),('concatenate',2,None),
                                  ('time_order',1,None),('time_order',2,None)):
            with self.subTest(merge=merge,count=count,quota=quota):
                rows,_ = self.result(self.config(merge,count,quota))
                self.assertEqual(rows[0]['value'].hex(), (1.0).hex())

    def test_missing_and_duplicate_delivery_fail_without_hanging(self):
        """实际子进程谎报EOF或重复块，主进程须拒绝并清理，不等待永远不会到来的块。"""
        for worker in (missing_block_worker, duplicate_offer_worker):
            with self.subTest(worker=worker.__name__):
                with patch('chronaxis.fast.session_worker.worker_main', worker):
                    with self.assertRaises(ValueError):
                        self.result(self.config(count=2))
                self.assertFalse(list((self.folder/'output').glob('*manifest*')))
                self.assertFalse(list((self.folder/'temporary').iterdir()))

    def test_reader_close_failure_does_not_publish(self):
        """读取结束后关闭报错不能发布成功，即使全部贡献已经求出。"""
        from chronaxis.fast.stream import FileContributions
        original = FileContributions.close
        def broken_close(reader):
            """释放真实资源再注入一次关闭错。参数: 读取器。返回: None。异常: OSError。"""
            was_closed = reader.closed
            original(reader)
            if not was_closed:
                raise OSError('injected reader close failure')
        with patch.object(FileContributions, 'close', broken_close):
            with self.assertRaisesRegex(OSError, 'injected'):
                self.result(self.config())
        self.assertFalse(list((self.folder/'output').glob('*manifest*')))

    def test_required_spool_write_failure_cleans_partial_files(self):
        """内联归并暂存部分写入后失败，清理本次文件且不发布成功。"""
        original = Path.write_bytes
        def broken_write(path, content):
            """模拟实际写盘中断。参数: 路径/数据。返回: 字节数。异常: OSError。"""
            if path.suffix == '.block':
                original(path, content[:16])
                raise OSError('injected disk write failure')
            return original(path, content)
        with patch.object(Path, 'write_bytes', broken_write):
            with self.assertRaisesRegex(OSError, 'injected'):
                self.result(self.config(merge='time_order'))
        self.assertFalse(list((self.folder/'output').glob('*manifest*')))
        self.assertFalse(list((self.folder/'temporary').iterdir()))

    def test_failure_and_inflight_cancel_leave_no_session_files(self):
        """worker崩溃及在途取消均可结束，不能留下正在写暂存的孤儿。"""
        with patch('chronaxis.fast.session_worker.worker_main', crash_worker):
            with self.assertRaises((RuntimeError, EOFError)):
                self.result(self.config(count=2))
        self.assertFalse(list((self.folder/'temporary').iterdir()))
        cancel = Event()
        timer = Timer(0.6, cancel.set)
        timer.start()
        try:
            with patch('chronaxis.fast.session_worker.worker_main', stalled_worker):
                with self.assertRaises(InterruptedError):
                    self.result(self.config(count=2), cancel_event=cancel)
        finally:
            timer.join()
        self.assertFalse(list((self.folder/'temporary').iterdir()))
        self.assertFalse(list((self.folder/'output').glob('*manifest*')))

    def test_corrupt_spool_and_small_memory_do_not_publish(self):
        """实际暂存回读损坏和RAM不足必须失败，禁止发布成功清单。"""
        from chronaxis.fast.session import FilePool
        original = FilePool.read_spool
        def corrupt(owner,index,number):
            """在本测试中破坏一次读取。参数: 调度器/文件/块。返回: 损坏bytes。异常: 原IO。"""
            packet = bytearray(original(owner,index,number))
            packet[-1] ^= 1
            return packet
        with patch.object(FilePool, 'read_spool', corrupt), self.assertRaisesRegex(ValueError, '完整性'):
            self.result(self.config('time_order',2))
        spec = compile_config(self.config(count=2))
        spec['memory_budget_bytes'] = 1
        with self.assertRaisesRegex(Exception, 'RAM'):
            run_session(spec)
        self.assertFalse(list((self.folder/'temporary').iterdir()))
        self.assertFalse(list((self.folder/'output').glob('*manifest*')))

    def test_cli_static_override_and_batch_nesting_rejection(self):
        """静态解释允许缺日志、报告覆盖上限；独立batch内禁止再开进程池。"""
        from contextlib import redirect_stdout
        from io import StringIO
        from chronaxis.cli import _parser
        from chronaxis.fast.cli import execute
        from chronaxis.fast.batch import run_batch
        self.raw['sources'][0]['paths'] = [str(self.folder/'absent1.asc'),str(self.folder/'absent2.asc')]
        config = self.config(count=1)
        arguments = _parser().parse_args(['fast','explain',str(config),'--process-count','4'])
        captured = StringIO()
        with redirect_stdout(captured):
            self.assertEqual(execute(arguments),0)
        self.assertEqual(json.loads(captured.getvalue())['worker_process_limit'],2)
        self.config(count=2)
        batch = self.folder/'batch.json'
        batch.write_text(json.dumps(dict(batch_version=1,jobs=[dict(plan=config.name)])),encoding='utf8')
        with self.assertRaisesRegex(ValueError,'内部不能请求多进程'):
            run_batch(batch,self.folder/'batch-output')
        self.assertFalse((self.folder/'batch-output').exists())

    def test_zero_selected_and_cross_file_identity(self):
        """已入选的零贡献为有效零；全会话帧型冲突不能被各文件独立状态隐藏。"""
        from chronaxis.fast.session import SessionAccumulator
        spec = compile_config(self.config())
        accumulator = SessionAccumulator(spec)
        accumulator.consume((0,0,((0,0.0,True),)))
        facts = dict(raw=1, targets=[1], valid=[1], selected=[1], kinds=[1], compatible=[])
        accumulator.finish_file(facts)
        rows,_ = accumulator.result()
        self.assertEqual(rows[0]['value'],0.0)
        self.assertIsNone(rows[0]['reason'])
        with self.assertRaisesRegex(ValueError,'跨文件'):
            accumulator.finish_file(dict(facts,kinds=[2]))

    def test_dbc_change_and_missing_final_contribution(self):
        """冻结后DBC改动和EOF数量不一致均不允许成功。"""
        from chronaxis.fast.session import SessionAccumulator
        spec = compile_config(self.config())
        bad = dict(spec,_dbc_digest='0'*64)
        with self.assertRaisesRegex(ValueError,'DBC内容变化'):
            run_session(bad)
        accumulator = SessionAccumulator(spec)
        accumulator.finish_file(dict(raw=1,targets=[1],valid=[1],selected=[1],kinds=[1],compatible=[]))
        with self.assertRaisesRegex(ValueError,'完整且唯一'):
            accumulator.result()

    def test_mixed_formats_and_blf_domain_does_not_stop_early(self):
        """ASC/BLF混合共享一次累计；BLF先出范围后回范围仍须计算后续帧。"""
        import can
        path = self.folder/'returning.blf'
        with can.BLFWriter(path) as writer:
            for timestamp in (1704067201.5,1704067203.0,1704067201.8):
                writer.on_message_received(can.Message(timestamp=timestamp,channel=0,
                    arbitration_id=256,is_extended_id=False,data=b'\xa0\x0f'))
        self.raw['sources'][0]['paths'] = [str(path)]
        self.raw['dataset']['domain'] = dict(start='1704067201s',end='1704067202s')
        rows,_ = self.result(self.config(count=1))
        self.assertEqual(rows[0]['value'],800.0)
        self.raw['dataset'].pop('domain')
        self.raw['sources'][0]['paths'] = [str(self.paths[0]),str(path)]
        rows,_ = self.result(self.config(count=2))
        self.assertEqual(rows[0]['value'],2000.0)


if __name__ == '__main__':
    unittest.main()
