"""D3草稿专项：保留异常及暂停生成器，检查本层大对象释放和借用边界。

只在D3产品补丁应用后运行。使用私有临时目录，不读取真实日志、不改RefProjects。
弱引用仅证明指定对象不再由本层持有，不代表进程RSS保证；完整结果回归另跑。
"""
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory
import gc
import unittest
from unittest.mock import patch
import weakref

from chronaxis.results import readable, result, artifact_exports


class LargeCell(str):
    """可弱引用的文本测试值，不改变str的CSV编码。"""


class LargeBlock(bytearray):
    """可弱引用的固定读取块，用于证明异常帧已释放本层引用。"""


def capture_failure(callback):
    """保留真实异常及回溯。参数: 零参调用。返回: 异常。异常: 未失败则AssertionError。"""
    try:
        callback()
    except BaseException as exc:
        return exc
    finally:
        callback = None
    raise AssertionError('预期故障没有发生')


def local_values(error, module_name, function_name):
    """只读取指定故障帧，不修改回溯。参数: 错误和模块/函数。返回: 局部变量。异常: 未找到断言。"""
    trace = error.__traceback__
    while trace is not None:
        frame = trace.tb_frame
        if frame.f_globals.get('__name__') == module_name and frame.f_code.co_name == function_name:
            return frame.f_locals
        trace = trace.tb_next
    raise AssertionError('未找到预期异常帧')


class FailingOutput:
    """在指定写入次数失败，记录真实关闭；不保存传入载荷。"""

    def __init__(self, failure, fail_at=3):
        """参数: 原异常及失败次序。返回: owner。异常: 无。"""
        self.failure, self.fail_at, self.calls, self.closed = failure, fail_at, 0, False

    def __enter__(self):
        """参数: 无。返回: 自身。异常: 无。"""
        return self

    def __exit__(self, kind, value, traceback):
        """参数: 原错误。返回: False保留原错。异常: 无。"""
        self.close()
        return False

    def close(self):
        """参数: 无。返回: None。异常: 无；记录实际关闭事实。"""
        self.closed = True

    def write(self, payload):
        """参数: 借用载荷。返回: 长度。异常: 指定原错；本层不留载荷。"""
        try:
            self.calls += 1
            if self.calls == self.fail_at:
                raise self.failure
            return len(payload)
        finally:
            payload = None


class FailingDigest:
    """摘要故障本身不保存输入，避免把其他帧保留误算成被测层泄漏。"""

    def __init__(self, failure):
        """参数: 原错。返回: 状态。异常: 无。"""
        self.failure = failure

    def update(self, payload):
        """参数: 借用块。返回: 无。异常: 原错；释放本测试帧参数。"""
        try:
            raise self.failure
        finally:
            payload = None


class BlockInput:
    """每次读取构造一个独立64KiB块，只向测试交出弱引用。"""

    def __init__(self, references):
        """参数: 弱引用列表。返回: 读句柄。异常: 无。"""
        self.references, self.closed = references, False

    def __enter__(self):
        """参数: 无。返回: 自身。异常: 无。"""
        return self

    def __exit__(self, kind, value, traceback):
        """参数: 原错误。返回: False。异常: 无。"""
        self.close()
        return False

    def read(self, size):
        """参数: 有限读取量。返回: 新块。异常: 非64KiB请求拒绝。"""
        assert size == 65536
        block = LargeBlock(b'x' * size)
        self.references.append(weakref.ref(block))
        return block

    def close(self):
        """参数: 无。返回: None。异常: 无。"""
        self.closed = True

    def fileno(self):
        """参数: 无。返回: fstat替身使用的句柄号。异常: 无。"""
        return 7


class ReadableOwnershipTests(unittest.TestCase):
    """区分借用行流和writer自建行流，故障后仍保留原异常。"""

    def writer(self, directory):
        """参数: 临时目录。返回: 不需要SQLite的写入器。异常: 无。"""
        owner = SimpleNamespace(metadata=SimpleNamespace(integrity_diagnostics=False), spool=SimpleNamespace(budget=None))
        return readable.ReadableWriter(owner, directory, None)

    def rows(self, references, closed, cleanup=None):
        """参数: 弱引用/关闭记录及可选收尾错。返回: 自持大单元格的生成器。异常: 可选收尾错。"""
        cell = LargeCell('x' * 1048576)
        references.append(weakref.ref(cell))
        try:
            yield [cell]
            yield ['next']
        finally:
            cell = None
            closed.append(True)
            if cleanup is not None:
                raise cleanup

    def test_borrowed_rows_remain_open_after_csv_failure(self):
        """借用流写失败后由调用者继续使用/关闭，清理仅释放writer自己的编码对象。"""
        with TemporaryDirectory(prefix='chronaxis-d3-') as directory:
            writer = self.writer(Path(directory)); references, closed = [], []
            rows = self.rows(references, closed); failure = OSError('write failure'); handle = FailingOutput(failure)
            with patch.object(Path, 'open', return_value=handle):
                error = capture_failure(lambda: writer._write('contributions', ['value'], rows))
            self.assertIs(error, failure); self.assertTrue(handle.closed)
            self.assertFalse(closed); self.assertIsNotNone(rows.gi_frame)
            self.assertIsNotNone(references[0]())
            values = local_values(error, readable.__name__, '_write')
            for name in ('rows', 'columns', 'values', 'payload', 'writer', 'buffer'):
                self.assertIsNone(values[name], name)
            self.assertEqual(next(rows), ['next'])
            rows.close(); gc.collect(); self.assertIsNone(references[0]())

    def test_owned_rows_close_even_while_error_and_generator_are_retained(self):
        """writer创建的流在写失败后显式结束；外部保留生成器对象也不持有大单元格。"""
        with TemporaryDirectory(prefix='chronaxis-d3-') as directory:
            writer = self.writer(Path(directory)); references, closed = [], []; rows = self.rows(references, closed)
            failure = OSError('write failure'); handle = FailingOutput(failure)
            with patch.object(writer, '_main_rows', return_value=rows), patch.object(Path, 'open', return_value=handle):
                error = capture_failure(lambda: writer._write_owned_rows('contributions', ['value']))
            gc.collect(); self.assertIs(error, failure); self.assertEqual(closed, [True])
            self.assertIsNone(rows.gi_frame); self.assertIsNone(references[0]())
            self.assertEqual(writer.infos, {}); self.assertEqual(writer.counts, {})

    def test_owned_close_error_does_not_replace_primary_write_error(self):
        """写入和生成器close同时失败，保留写入错及附加清理说明。"""
        with TemporaryDirectory(prefix='chronaxis-d3-') as directory:
            writer = self.writer(Path(directory)); references, closed = [], []
            rows = self.rows(references, closed, RuntimeError('close failure'))
            failure = OSError('write failure'); handle = FailingOutput(failure)
            with patch.object(writer, '_main_rows', return_value=rows), patch.object(Path, 'open', return_value=handle):
                error = capture_failure(lambda: writer._write_owned_rows('contributions', ['value']))
            self.assertIs(error, failure)
            self.assertTrue(any('RuntimeError' in note for note in error.__notes__))
            self.assertEqual(closed, [True]); self.assertIsNone(rows.gi_frame)

    def test_detail_generator_closes_only_its_created_input(self):
        """暂停明细生成器再关闭，内部自建源流应结束，即使测试仍持有它。"""
        with TemporaryDirectory(prefix='chronaxis-d3-') as directory:
            writer = self.writer(Path(directory)); writer.varying = (); references, closed = [], []
            def source_rows():
                """参数: 无。返回: 一条输入追溯行。异常: 无；finally记录本流关闭。"""
                value = LargeCell('x' * 1048576); references.append(weakref.ref(value))
                try:
                    yield dict(source='bus', original_sequence=1, time_ns=0, record_type='signal_sample',
                               locator='', values_json=value, quality=0)
                finally:
                    value = None; closed.append(True)
            source = source_rows()
            with patch.object(writer, '_rows', return_value=source):
                rows = writer._detail_rows('input_trace'); item = next(rows)
            self.assertIsNotNone(references[0]()); item = None
            rows.close(); gc.collect()
            self.assertEqual(closed, [True]); self.assertIsNone(source.gi_frame); self.assertIsNone(references[0]())


class PayloadReleaseTests(unittest.TestCase):
    """故障后只核本层引用释放；保留原异常，不清理第三方回溯。"""

    def test_digest_failure_releases_borrowed_text_without_closing_stream(self):
        """摘要失败时释放本帧text/encoded，借用输出流的关闭权仍在调用者。"""
        failure = OSError('digest failure'); stream = FailingOutput(failure, fail_at=99)
        writer = result._DigestOutput(stream); writer.digest = FailingDigest(failure); references = []
        def invoke():
            """参数: 无。返回: 不返回。异常: 原摘要错；测试调用层也不留文本。"""
            value = LargeCell('x' * 1048576); references.append(weakref.ref(value))
            try:
                writer.write(value)
            finally:
                value = None
        error = capture_failure(invoke); gc.collect()
        self.assertIs(error, failure); self.assertFalse(stream.closed); self.assertIsNone(references[0]())
        values = local_values(error, result.__name__, 'write')
        self.assertIsNone(values['payload']); self.assertIsNone(values['encoded'])

    def test_output_file_hash_failure_closes_input_and_releases_chunk(self):
        """文件摘要错保留回溯，with仍关闭自有输入，当前64KiB块不留在本层。"""
        references=[]; handle=BlockInput(references); failure=OSError('hash failure')
        owner=SimpleNamespace(metadata=SimpleNamespace(detailed_diagnostics=True))
        path=SimpleNamespace(open=lambda mode:handle, name='result.csv')
        with patch.object(result.hashlib, 'sha256', return_value=FailingDigest(failure)):
            error=capture_failure(lambda:result.AnalysisResult._file_info(owner,path))
        gc.collect(); self.assertIs(error,failure); self.assertTrue(handle.closed)
        self.assertIsNone(references[0]()); self.assertIsNone(local_values(error,result.__name__,'_file_info')['chunk'])

    def test_artifact_hash_failure_releases_block_but_preserves_owner_slot(self):
        """附件块释放与句柄恢复责任分开：错误后input槽仍保留给最高所有者重试。"""
        references=[]; handle=BlockInput(references); failure=OSError('hash failure')
        owner=object.__new__(artifact_exports.ArtifactExportStore)
        owner._input=owner._output=None;owner._integrity=True
        owner._identity=lambda path:(1,2,65536,3)
        stat=SimpleNamespace(st_dev=1,st_ino=2,st_size=65536,st_mtime_ns=3)
        with patch.object(Path,'open',return_value=handle), patch.object(artifact_exports.os,'fstat',return_value=stat), patch.object(artifact_exports,'sha256',return_value=FailingDigest(failure)):
            error=capture_failure(lambda:owner._file(Path('owned-artifact')))
        gc.collect(); self.assertIs(error,failure); self.assertIsNone(references[0]())
        self.assertIs(owner._input,handle); self.assertFalse(handle.closed)
        self.assertIsNone(local_values(error,artifact_exports.__name__,'_file')['block'])
        handle.close()




if __name__ == '__main__':
    unittest.main()


class FailingReader:
    """第一次读取失败，前两次关闭失败，第三次成功的真实恢复责任替身。"""
    def __init__(self):
        """参数: 无。返回: 未关闭读者。异常: 无。"""
        self.error = OSError('read primary')
        self.calls = 0
        self.closed = False
    def __iter__(self):
        """参数: 无。返回: 自身。异常: 无。"""
        return self
    def __next__(self):
        """参数: 无。返回: 不返回。异常: 首要读取错。"""
        raise self.error
    def close(self):
        """参数: 无。返回: None。异常: 前两次失败，不能据调用次数假报关闭。"""
        self.calls += 1
        if self.calls <= 2:
            raise RuntimeError('close retry')
        self.closed = True


class ReaderRecoveryTests(unittest.TestCase):
    """源结果流和索引游标均由writer恢复，不让关闭错误覆盖读取错误。"""
    def test_result_reader_primary_and_repeated_close(self):
        """结果流失败后保留主错，writer第二次关闭仍可失败，再次关闭成功。"""
        self.check_reader(False)
    def test_index_reader_primary_and_repeated_close(self):
        """索引游标使用相同所有权边界，关闭游标成功后才关闭数据库。"""
        self.check_reader(True)
    def check_reader(self,indexed):
        """参数: 读取路径选择。返回: None。异常: 验收断言。"""
        from chronaxis.results.budget import ResourceBudget
        with TemporaryDirectory(prefix='chronaxis-d3-reader-') as directory:
            reader = FailingReader()
            owner = SimpleNamespace(spool=SimpleNamespace(budget=ResourceBudget(1048576,1048576),counts={}))
            writer = readable.ReadableWriter(owner,Path(directory),lambda *_:reader)
            closed=[]
            if indexed:
                writer.connection=SimpleNamespace(execute=lambda *_:reader,close=lambda:closed.append(True))
            rows=writer._main_rows('events') if indexed else writer._rows('events')
            error=capture_failure(lambda:next(rows))
            self.assertIs(error,reader.error)
            self.assertIs(error.readable_cleanup_owner,writer)
            self.assertIs(writer._pending_reader,reader)
            self.assertTrue(any('RuntimeError' in note for note in error.__notes__))
            with self.assertRaises(RuntimeError):writer.close()
            self.assertFalse(writer.closed);self.assertFalse(reader.closed)
            writer.close();self.assertTrue(writer.closed);self.assertTrue(reader.closed)
            self.assertIsNone(writer._pending_reader)
            self.assertEqual(closed,[True] if indexed else [])


class OutputRecoveryTests(unittest.TestCase):
    """CSV输出close持续失败时，writer保留句柄而非只留一句错误说明。"""
    def test_write_primary_survives_output_close_failure(self):
        """原写错不被关闭错替代；两次失败后仍能从同一writer关闭句柄。"""
        from chronaxis.results.budget import ResourceBudget
        class Output(FailingOutput):
            """前两次close失败，第三次实际关闭。"""
            def __init__(self,failure):
                """参数: 写入原错。返回: 句柄。异常: 无。"""
                super().__init__(failure);self.close_calls=0
            def close(self):
                """参数: 无。返回: None。异常: 前两次关闭失败。"""
                self.close_calls+=1
                if self.close_calls<=2:raise RuntimeError('output close retry')
                self.closed=True
        with TemporaryDirectory(prefix='chronaxis-d3-output-') as directory:
            failure=OSError('write primary');handle=Output(failure)
            owner=SimpleNamespace(metadata=SimpleNamespace(integrity_diagnostics=False),
                spool=SimpleNamespace(budget=ResourceBudget(1048576,1048576)))
            writer=readable.ReadableWriter(owner,Path(directory),None)
            with patch.object(Path,'open',return_value=handle):
                error=capture_failure(lambda:writer._write('contributions',['v'],[['1'],['2']]))
            self.assertIs(error,failure);self.assertIs(error.readable_cleanup_owner,writer)
            self.assertIs(writer._pending_output,handle);self.assertFalse(handle.closed)
            self.assertTrue(any('RuntimeError' in note for note in error.__notes__))
            with self.assertRaises(RuntimeError):writer.close()
            self.assertFalse(writer.closed);self.assertFalse(handle.closed)
            writer.close();self.assertTrue(writer.closed);self.assertTrue(handle.closed)
            self.assertIsNone(writer._pending_output)
