"""用真实Windows目录锁验证新结果发布安装的有限重试与不覆盖边界。

每例构造真实ResourceBudget、已封口ResultSpool、RunMetadata和AnalysisResult。
CreateFileW以FILE_LIST_DIRECTORY打开实际待安装目录且不共享DELETE，使原os.rename
真正返回Win5/32；属性访问不参与该共享检查，不能单用READ_ATTRIBUTES充作锁。
短锁由Timer在首次原错误后0.12秒CloseHandle，长锁跨全部尝试保持。测试观察真实
rename调用及原异常对象，不用伪造重试结果替代Windows重现。已有目标与重试间
创建目标都必须保护；另以真实缺失源和明确标识的受控非eligible PermissionError
验证其他错误不重试。只写work新目录，源暂存SHA与最终RAM另核，不涉及旧CAN链。
"""

# Windows API只在平台专用测试实际运行时调用，普通导入不打开句柄或创建目录。
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from threading import Lock, Timer
import unittest
from unittest.mock import patch
from uuid import uuid4

from chronaxis.results import AnalysisError, AnalysisResult, RunMetadata
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.spool import ResultSpool


class DirectoryDeleteLock:
    """持有一个真实Windows目录句柄，排除FILE_SHARE_DELETE直到成功CloseHandle。

    close用线程锁串行化Timer与测试清理，不重复抵销同一OS句柄；closed只有原
    CloseHandle返回成功后才为True。本类不代表产品owner或伪造资源预算归属。
    """

    def __init__(self, path):
        """在真实既有目录上取得禁止删除共享的句柄，不改变ACL或文件内容。

        参数: path为本例实际temporary目录。返回: 持有真实HANDLE的测试资源。
        异常: WinError为原CreateFileW失败；没有成功句柄时不假报已锁定。
        """
        self._mutex = Lock()
        self._kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        self._create = self._kernel32.CreateFileW
        self._create.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
            wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
        self._create.restype = wintypes.HANDLE
        self._close = self._kernel32.CloseHandle
        self._close.argtypes, self._close.restype = (wintypes.HANDLE,), wintypes.BOOL
        self.path, self.closed, self.close_calls = Path(path), False, 0
        # FILE_LIST_DIRECTORY参与共享访问检查；仅属性访问不会阻止rename。
        # 共享READ|WRITE而不共享DELETE；OPEN_EXISTING与目录必需标志保持原值。
        self.handle = self._create(str(self.path), 0x1, 0x1 | 0x2, None, 3, 0x02000000, None)
        if self.handle == ctypes.c_void_p(-1).value:
            self.handle = None
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        """调用真实CloseHandle，Timer与finally竞争时只关闭一次。

        参数: 无。返回: None。异常: 原CloseHandle错误传播并保留原句柄供清理重试。
        """
        with self._mutex:
            if self.handle is None:
                return
            if not self._close(self.handle):
                raise ctypes.WinError(ctypes.get_last_error())
            self.close_calls += 1
            self.handle = None
            self.closed = True


@unittest.skipUnless(os.name == 'nt', '真实CreateFileW目录共享与不覆盖安装专项仅适用Windows')
class ResultPublishRetryTests(unittest.TestCase):
    """实际目录锁与真实结果共同验证发布，不复用假owner或修改旧数值断言。"""

    def fixture(self):
        """建立两行真实封口结果和独立home工作根，构造后仍由本测试close。

        参数: 无。返回: (root,result)。异常: 真实模型、磁盘或预算错误直接失败。
        """
        # 只在方法局部借纯行夹具，不全局导入TestCase导致本模块重复发现旧测试。
        from test_results import summary_event_row, summary_selection_row
        root = Path(__file__).resolve().parents[2] / 'work/result-publish-retry' / uuid4().hex
        root.mkdir(parents=True)
        budget = ResourceBudget(4 * 1024**2)
        spool = ResultSpool(budget, root / 'source', result_buffer_rows=1, enable_selections=True, requested_tables=('events','selections'))
        self.addCleanup(spool.close)
        spool.append(summary_event_row(0, 1))
        spool.append(summary_selection_row(1))
        spool.seal()
        metadata = RunMetadata('retry-run', 'synthetic-input', 'synthetic-plan', 'reference', 3,
            'relative nanoseconds; origin=0', (('session', 0, 20),),
            datetime.now(timezone.utc).isoformat(), limitations=('synthetic install-lock verification only',),
            device_label='home', detailed_diagnostics=True, retain_work=True)
        result = AnalysisResult(spool, metadata)
        self.addCleanup(result.close)
        return root, result

    def source_snapshot(self, result):
        """为有限源暂存计算实际字节SHA，不包含允许新增的失败诊断文件。

        参数: result为本例真实结果。返回: 表名/路径/字节数/SHA的固定tuple。
        异常: 源文件消失或读取错误传播，不将其当正常安装副作用。
        """
        return tuple((table, path, len(payload), sha256(payload).hexdigest())
            for table, path in result.spool.files.items() for payload in (path.read_bytes(),))

    def close_result(self, result):
        """重复关闭真实最高结果并核零RAM，源与已发布文件均不删除。

        参数: result为本例owner。返回: None。异常: 实际关闭或重复抵销错误使测试失败。
        """
        budget = result.spool.budget
        result.close()
        result.close()
        self.assertEqual(budget.ram_bytes, 0)
        self.assertTrue(result._closed)
        self.assertFalse(result._iterators)

    def test_real_transient_directory_lock_fails_original_rename_then_publishes(self):
        """真实首Win5/32后0.12秒解除锁，实际rename由失败变成功且源SHA不变。

        参数: 无。返回: None。异常: 假错误、未重试、Timer未关真实句柄或结果不完整即失败。
        """
        import chronaxis.results.result as module
        root, result = self.fixture()
        destination, snapshot = root / 'published', self.source_snapshot(result)
        original, attempts, errors, locks, timers, timer_errors = module.os.rename, [], [], [], [], []

        def release_lock():
            """由真实Timer关闭实际句柄。参数: 无。返回: None。异常: 记录原错供主线程强断言。"""
            try:
                locks[0].close()
            except BaseException as exc:
                timer_errors.append(exc)

        def observe_rename(source, target, *args, **kwargs):
            """只透传实际rename并记录原错。参数: 原调用参数。返回: 原返回。异常: 同一OS错误。"""
            attempts.append((Path(source), Path(target)))
            if not locks:
                lock = DirectoryDeleteLock(source)
                locks.append(lock)
                self.addCleanup(lock.close)
            try:
                return original(source, target, *args, **kwargs)
            except OSError as exc:
                errors.append(exc)
                if not timers:
                    # 定时从实际首失败起算，保证不是锁尚未生效就先放行了第一次rename。
                    timer = Timer(.12, release_lock)
                    timer.daemon = True
                    timers.append(timer)
                    self.addCleanup(timer.cancel)
                    self.addCleanup(timer.join, 2.)
                    timer.start()
                raise

        with patch.object(module.os, 'rename', new=observe_rename):
            published = result.write(destination)
        self.assertEqual(len(timers), 1)
        timers[0].join(2.)
        self.assertFalse(timers[0].is_alive())
        self.assertEqual(timer_errors, [])
        self.assertTrue(locks[0].closed)
        self.assertEqual(locks[0].close_calls, 1)
        self.assertGreaterEqual(len(attempts), 2)
        self.assertLessEqual(len(attempts), 6)
        self.assertEqual(len(errors), len(attempts) - 1)
        self.assertTrue(all(isinstance(exc, PermissionError) and exc.winerror in (5, 32) for exc in errors))
        self.assertEqual(len({source for source, _ in attempts}), 1)
        self.assertTrue(all(target == destination for _, target in attempts))
        self.assertFalse(attempts[0][0].exists())
        self.assertEqual(json.loads(published.manifest_path.read_text(encoding='utf-8'))['status'], 'completed')
        self.assertEqual(self.source_snapshot(result), snapshot)
        self.close_result(result)

    def test_real_permanent_directory_lock_stops_after_six_original_errors(self):
        """真实锁跨全部六次尝试，保最后原PermissionError和note，不移动或覆盖路径。

        参数: 无。返回: None。异常: 无界重试、换temp、原错丢失或源暂存受损即失败。
        """
        import chronaxis.results.result as module
        root, result = self.fixture()
        destination, snapshot = root / 'blocked', self.source_snapshot(result)
        original, attempts, errors, locks = module.os.rename, [], [], []

        def locked_rename(source, target, *args, **kwargs):
            """保持真实锁并调用原rename。参数: 原参数。返回: 原返回。异常: 同一真实OS错误。"""
            attempts.append((Path(source), Path(target)))
            if not locks:
                locks.append(DirectoryDeleteLock(source))
                self.addCleanup(locks[0].close)
            try:
                return original(source, target, *args, **kwargs)
            except OSError as exc:
                errors.append(exc)
                raise

        with patch.object(module.os, 'rename', new=locked_rename), self.assertRaises(AnalysisError) as caught:
            result.write(destination)
        self.assertEqual(len(attempts), 6)
        self.assertEqual(len(errors), 6)
        self.assertTrue(all(isinstance(exc, PermissionError) and exc.winerror in (5, 32) for exc in errors))
        self.assertIs(caught.exception.__cause__, errors[-1])
        self.assertTrue(getattr(errors[-1], '__notes__', ()))
        self.assertEqual(len({source for source, _ in attempts}), 1)
        temporary = attempts[0][0]
        self.assertTrue(temporary.is_dir())
        self.assertFalse(destination.exists())
        self.assertEqual(json.loads((temporary / 'run_manifest.json').read_text(encoding='utf-8'))['status'], 'output_failed')
        self.assertEqual(self.source_snapshot(result), snapshot)
        # 普通安装失败只结束本次publish；解除真实锁后可向另一新目录正常重试。
        locks[0].close()
        retry = result.write(root / 'after-unlock')
        self.assertEqual(json.loads(retry.manifest_path.read_text(encoding='utf-8'))['status'], 'completed')
        self.assertEqual(self.source_snapshot(result), snapshot)
        self.close_result(result)

    def test_existing_target_and_target_created_during_real_lock_are_never_overwritten(self):
        """既有目标零rename；首真实锁错后插入目标时下一尝试先拒绝，保sentinel和源。

        参数: 无。返回: None。异常: 目标覆盖、存在检查只做一次或源被移动即失败。
        """
        import chronaxis.results.result as module
        for race in (False, True):
            with self.subTest(race=race):
                root, result = self.fixture()
                destination, snapshot = root / 'existing', self.source_snapshot(result)
                sentinel = destination / 'owned-before-publish.txt'
                original, attempts, errors, locks = module.os.rename, [], [], []
                if not race:
                    destination.mkdir()
                    sentinel.write_bytes(b'preserve destination')

                def race_rename(source, target, *args, **kwargs):
                    """原rename首个真实锁错后创建目标。参数: 原参数。返回: 原返回。异常: 原OS错误。"""
                    attempts.append((Path(source), Path(target)))
                    if not locks:
                        locks.append(DirectoryDeleteLock(source))
                        self.addCleanup(locks[0].close)
                    try:
                        return original(source, target, *args, **kwargs)
                    except OSError as exc:
                        errors.append(exc)
                        if race and len(errors) == 1:
                            destination.mkdir()
                            sentinel.write_bytes(b'preserve destination')
                        raise

                with patch.object(module.os, 'rename', new=race_rename), self.assertRaises(AnalysisError) as caught:
                    result.write(destination)
                self.assertIsInstance(caught.exception.__cause__, FileExistsError)
                self.assertEqual(len(attempts), int(race))
                self.assertEqual(len(errors), int(race))
                if race:
                    self.assertIsInstance(errors[0], PermissionError)
                    self.assertIn(errors[0].winerror, (5, 32))
                    self.assertTrue(attempts[0][0].is_dir())
                    self.assertFalse(locks[0].closed)
                    locks[0].close()
                self.assertEqual(sentinel.read_bytes(), b'preserve destination')
                self.assertEqual(tuple(path.name for path in destination.iterdir()), ('owned-before-publish.txt',))
                self.assertEqual(self.source_snapshot(result), snapshot)
                self.close_result(result)

    def test_noneligible_real_missing_source_and_controlled_permission_are_not_retried(self):
        """其他原OSError直接传播；受控Win33仅核分类，不冒称真实Windows锁重现。

        参数: 无。返回: None。异常: 非eligible错误被重试、替换或使源/目标改变即失败。
        """
        import chronaxis.results.result as module
        root, result = self.fixture()
        snapshot, original, errors = self.source_snapshot(result), module.os.rename, []

        def missing_rename(source, target, *args, **kwargs):
            """真实缺源rename只观察原错误。参数: 原参数。返回: 原返回。异常: 原FileNotFoundError。"""
            try:
                return original(source, target, *args, **kwargs)
            except OSError as exc:
                errors.append(exc)
                raise

        with patch.object(module.os, 'rename', new=missing_rename), self.assertRaises(FileNotFoundError) as caught:
            result._install_directory(root / 'actually-missing', root / 'not-created')
        self.assertEqual(len(errors), 1)
        self.assertIs(caught.exception, errors[0])
        self.assertFalse((root / 'not-created').exists())
        temporary, destination = root / 'controlled-temp', root / 'controlled-destination'
        temporary.mkdir()
        (temporary / 'source.txt').write_bytes(b'preserve controlled source')
        # Windows标准异常构造的第四实参显式保存winerror；不是原OS重现或自造异常类。
        marker, entries = PermissionError(13, 'controlled noneligible permission', str(temporary), 33), []
        self.assertEqual(marker.winerror, 33)

        def controlled_permission(source, target, *args, **kwargs):
            """只注入非eligible分类错，明确不调用原OS。参数: 原参数。返回: 不返回。异常: 同一marker。"""
            entries.append((source, target))
            raise marker

        with patch.object(module.os, 'rename', new=controlled_permission), self.assertRaises(PermissionError) as caught:
            result._install_directory(temporary, destination)
        self.assertIs(caught.exception, marker)
        self.assertEqual(len(entries), 1)
        self.assertEqual((temporary / 'source.txt').read_bytes(), b'preserve controlled source')
        self.assertFalse(destination.exists())
        self.assertEqual(self.source_snapshot(result), snapshot)
        self.close_result(result)
