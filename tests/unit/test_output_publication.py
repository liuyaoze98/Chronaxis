"""验证已有输出目录复用、同刻并发和失败回滚，不读取真实日志。

使用合成结果及原帧；发布文件在临时测试目录。旧文件字节、完成清单顺序、
每次独立路径以及实际ASC回读共同验证新行为，不只镜像文件名拼接实现。
"""
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

from chronaxis.results.publication import PublicationNames
from chronaxis.results import ResourceBudget, ExportManifest
from chronaxis.results.frame_exports import export_can_frames, FrameExportSpec
from chronaxis.core.models import Interval
from chronaxis.sources.asc import ASCRead, ASCSpec
from test_frame_exports import raw
from test_readable_results import make_result, sample_event, sample_calculation


class PublicationTests(unittest.TestCase):
    """按本次实际清单取文件，确保新名字不会使用户结果或导出引用失效。"""

    @unittest.skipUnless(os.name=="nt","Windows删除中的命名锁专项")
    def test_delete_pending_lock_uses_independent_candidate(self):
        """锁删除竞争只影响候选名称，不损失结果。参数: 无。返回: None。异常: 断言。"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = Path.open
            attempts = []
            def open_lock(path, *args, **kwargs):
                """模拟首次锁仍待删除。参数: 路径及打开参数。返回: 文件。异常: PermissionError。"""
                if path.name.startswith('.publishing-'):
                    attempts.append(path)
                    if len(attempts) == 1:
                        raise PermissionError(13, 'delete pending', str(path))
                return original(path, *args, **kwargs)
            with patch.object(Path, 'open', open_lock):
                names = PublicationNames(root, ('manifest.json',))
            self.assertEqual(len(attempts), 2)
            self.assertNotEqual(attempts[0], attempts[1])
            names.close()
            self.assertEqual(list(root.iterdir()), [])

    def test_real_permission_error_is_not_retried_forever(self):
        """新候选仍无权限时报告原IO错误。参数: 无。返回: None。异常: 断言。"""
        with tempfile.TemporaryDirectory() as directory:
            failure = PermissionError(13, 'directory access denied', directory)
            with patch.object(Path, 'open', side_effect=failure) as opened:
                with self.assertRaises(PermissionError) as captured:
                    PublicationNames(directory, ('manifest.json',))
            self.assertIs(captured.exception, failure)
            self.assertEqual(opened.call_count, 2 if os.name=="nt" else 1)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_result_repeated_existing_directory(self):
        """同一结果反复发布保留旧内容和每次清单。参数: 无。返回: None。异常: 断言。"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root/'output'; target.mkdir()
            (target/'user.txt').write_bytes(b'keep')
            with make_result(root, [sample_event(), sample_calculation()]) as result:
                first = result.write(target)
                before = {p.name:p.read_bytes() for p in target.iterdir()}
                second = result.write(target)
            self.assertNotEqual(first.manifest_path, second.manifest_path)
            for name, content in before.items():
                self.assertEqual((target/name).read_bytes(), content)
            for manifest in (first, second):
                document = json.loads(manifest.manifest_path.read_text(encoding='utf-8'))
                self.assertEqual(document['manifest_file'], manifest.manifest_path.name)
                self.assertTrue(all((target/f['name']).is_file() for f in document['outputs']))
            self.assertFalse(list(target.glob('.publishing-*')))

    def test_same_time_parallel_and_released_reservation(self):
        """锁释放后的同刻运行也不能重用已有文件。参数: 无。返回: None。异常: 断言。"""
        with tempfile.TemporaryDirectory() as directory, patch('chronaxis.results.publication.datetime') as clock:
            clock.now.return_value.astimezone.return_value.strftime.return_value = '20261103_120000_000001'
            root = Path(directory)
            def publish(index):
                """独立线程发布一个小结果。参数: index序号。返回: 实际文件。异常: IO。"""
                temp = root/str(index); temp.mkdir()
                (temp/'manifest.json').write_text(str(index), encoding='utf-8')
                names = PublicationNames(root, ('manifest.json',))
                names.publish(temp, 'manifest.json')
                return root/names.names['manifest.json']
            with ThreadPoolExecutor(4) as pool:
                paths = list(pool.map(publish, range(8)))
            self.assertEqual(len(set(paths)),8)
            self.assertEqual({p.read_text() for p in paths},{str(i) for i in range(8)})

    def test_manifest_last_failure_rolls_back_only_owned_files(self):
        """完成清单移动失败回滚数据，保留用户文件。参数: 无。返回: None。异常: 断言。"""
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); temp=root/'temporary'; temp.mkdir()
            target=root/'results'; target.mkdir(); (target/'user').write_bytes(b'keep')
            for name in ('data.csv','manifest.json'): (temp/name).write_text(name)
            names=PublicationNames(target,('manifest.json','data.csv'))
            seen=[]
            def move(source,destination):
                """只在完成清单移动时制造故障。参数: 路径。返回: None。异常: OSError。"""
                seen.append(source.name)
                if source.name=='manifest.json': raise OSError('synthetic failure')
                os.rename(source,destination)
            with self.assertRaises(OSError): names.publish(temp,'manifest.json',move)
            self.assertEqual(seen,['data.csv','manifest.json'])
            self.assertEqual([p.name for p in target.iterdir()],['user'])
            self.assertEqual((target/'user').read_bytes(),b'keep')

    def test_external_replacement_is_not_removed(self):
        """回滚不删除外部替换的同名文件。参数: 无。返回: None。异常: 断言。"""
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); temp=root/'temporary'; temp.mkdir()
            for name in ('data.csv','manifest.json'): (temp/name).write_text(name)
            names=PublicationNames(root/'results',('data.csv','manifest.json'))
            target=names.root/names.names['data.csv']
            def move(source,destination):
                """替换已发布数据后令清单失败。参数: 路径。返回: None。异常: OSError。"""
                if source.name=='manifest.json':
                    replacement=names.root/'replacement'; replacement.write_bytes(b'other')
                    os.replace(replacement,target)
                    raise OSError('synthetic failure')
                os.rename(source,destination)
            with self.assertRaises(OSError): names.publish(temp,'manifest.json',move)
            self.assertEqual(target.read_bytes(),b'other')

    def test_public_asc_export_returns_actual_paths_and_reuses_root(self):
        """两次原帧导出各自回读原值，索引引用可达。参数: 无。返回: None。异常: 断言。"""
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); budget=ResourceBudget()
            for _ in range(2):
                result=export_can_frames([raw(1,0)],FrameExportSpec('asc'),Interval(0,2),root,budget,
                                         source='bus',device_label='home')
                self.assertIsInstance(result,ExportManifest)
                doc=json.loads(result.manifest_path.read_text(encoding='utf-8'))
                self.assertTrue((root/doc['exact_source_index']).is_file())
                asc=next(p for p in result.output_files if p.suffix=='.asc')
                with ASCRead(ASCSpec(asc),budget) as records:
                    self.assertEqual([r.time_ns for r in records],[1])
            self.assertEqual(len(list(root.glob('manifest_*.json'))),2)
            self.assertEqual(budget.ram_bytes,0)

    def test_file_created_after_name_reservation_is_not_overwritten(self):
        """分配之后出现的外部同名文件由rename拒绝。参数: 无。返回: None。异常: 断言。"""
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); temp=root/'temporary'; temp.mkdir()
            (temp/'manifest.json').write_bytes(b'new')
            names=PublicationNames(root/'results',('manifest.json',))
            target=names.root/names.names['manifest.json']; target.write_bytes(b'existing')
            with self.assertRaises(FileExistsError): names.publish(temp,'manifest.json')
            self.assertEqual(target.read_bytes(),b'existing')
            self.assertEqual((temp/'manifest.json').read_bytes(),b'new')

    def test_lock_cleanup_failure_does_not_leave_completed_output(self):
        """锁释放失败也撤回清单，保留原错误供调用者诊断。参数: 无。返回: None。异常: 断言。"""
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); temp=root/'temporary'; temp.mkdir()
            (temp/'manifest.json').write_bytes(b'completed')
            names=PublicationNames(root/'results',('manifest.json',))
            close=names.close
            calls=0
            def transient():
                """模拟第一次关闭失败、第二次恢复。参数: 无。返回: None。异常: OSError。"""
                nonlocal calls
                calls+=1
                if calls==1: raise OSError('lock cleanup failed')
                close()
            with patch.object(names,'close',side_effect=transient):
                with self.assertRaisesRegex(OSError,'lock cleanup failed'):
                    names.publish(temp,'manifest.json')
            self.assertFalse(tuple(names.root.iterdir()))
            self.assertTrue((temp/'manifest.json').is_file())

    def test_public_export_failure_removes_only_its_temporary_directory(self):
        """输入中断清理公开导出暂存并保留旧文件。参数: 无。返回: None。异常: 断言。"""
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); target=root/'output'; target.mkdir()
            (target/'old.txt').write_bytes(b'keep')
            def records():
                """一帧后失败。参数: 无。返回: 迭代器。异常: RuntimeError。"""
                yield raw(1,0)
                raise RuntimeError('input failed')
            budget=ResourceBudget()
            with self.assertRaisesRegex(RuntimeError,'input failed'):
                export_can_frames(records(),FrameExportSpec('asc'),Interval(0,2),target,budget,
                                  source='bus',device_label='home')
            self.assertEqual([p.name for p in root.iterdir()],['output'])
            self.assertEqual((target/'old.txt').read_bytes(),b'keep')
            self.assertEqual(budget.ram_bytes,0)

    def test_published_result_keeps_actual_manifest_when_empty_cleanup_fails(self):
        """完成后空目录清理失败由结果close重试。参数: 无。返回: None。异常: 断言。"""
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            result=make_result(root,[sample_event(),sample_calculation()])
            original=Path.rmdir
            def remove(path):
                """只阻止首次输出空暂存删除。参数: 路径。返回: None。异常: OSError。"""
                if path.name.startswith('.output.incomplete-'): raise OSError('empty cleanup')
                original(path)
            with patch.object(Path,'rmdir',remove):
                manifest=result.write(root/'output')
            self.assertTrue(manifest.manifest_path.is_file())
            self.assertIsNotNone(result._pending_output_cleanup)
            result.close()
            self.assertFalse(list(root.glob('.output.incomplete-*')))
            self.assertTrue(manifest.manifest_path.is_file())

    def test_export_cleanup_error_exposes_completed_manifest(self):
        """公开导出已完成而收尾出错时仍明确实际结果路径。参数: 无。返回: None。异常: 断言。"""
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); budget=ResourceBudget(); original=Path.rmdir; failed=False
            def remove(path):
                """首次空暂存删除失败，恢复清理成功。参数: 路径。返回: None。异常: OSError。"""
                nonlocal failed
                if path.name.endswith('.incomplete') and not failed:
                    failed=True
                    raise OSError('empty cleanup')
                original(path)
            with patch.object(Path,'rmdir',remove), self.assertRaisesRegex(OSError,'empty cleanup') as error:
                export_can_frames([raw(1,0)],FrameExportSpec('asc'),Interval(0,2),root/'output',budget,
                                  source='bus',device_label='home')
            self.assertTrue(error.exception.completed_manifest.manifest_path.is_file())
            self.assertFalse(list(root.glob('*.incomplete')))
            self.assertEqual(budget.ram_bytes,0)

    def test_reused_publication_never_rolls_back_previous_success(self):
        """再次写同名报告失败不能移动上一份成功报告。参数: 无。返回: None。异常: 断言。"""
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); temp=root/'temporary'; temp.mkdir()
            (temp/'manifest.json').write_bytes(b'first')
            names=PublicationNames(root/'output',('manifest.json',))
            names.publish(temp,'manifest.json')
            (temp/'manifest.json').write_bytes(b'second')
            with self.assertRaises(FileExistsError): names.publish(temp,'manifest.json')
            self.assertEqual((names.root/names.names['manifest.json']).read_bytes(),b'first')
            self.assertEqual((temp/'manifest.json').read_bytes(),b'second')

    def test_retained_result_cleanup_has_real_directory_identity(self):
        """保留工作现场也登记发布空目录身份，故障恢复后close能结束。参数: 无。返回: None。异常: 断言。"""
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); result=make_result(root,[sample_event(),sample_calculation()],retain_work=True)
            original=Path.rmdir
            def remove(path):
                """只阻止发布后的空暂存删除。参数: 路径。返回: None。异常: OSError。"""
                if path.name.startswith('.output.incomplete-'): raise OSError('cleanup')
                original(path)
            with patch.object(Path,'rmdir',remove): manifest=result.write(root/'output')
            self.assertIsNotNone(result._pending_output_cleanup[1])
            result.close()
            self.assertTrue(manifest.manifest_path.is_file())
            self.assertIsNone(result._pending_output_cleanup)

    def test_batch_lock_failure_still_closes_every_job(self):
        """命名锁失败仍清理所有任务，最后抛出首错。参数: 无。返回: None。异常: 断言。"""
        from chronaxis.batch.models import BatchReport, BatchJobResult, CleanupHandle
        first=OSError('lock failure')
        publication=Mock(); publication.close.side_effect=[first,None]
        one=Mock(); one.close.side_effect=[OSError('job failure'),None]
        two=Mock()
        jobs=(BatchJobResult('one','failed',recovery=CleanupHandle(one)),
              BatchJobResult('two','failed',recovery=CleanupHandle(two)))
        report=BatchReport(Path('unused'),jobs,1,False,False,'home',_publication=publication)
        with self.assertRaises(OSError) as error: report.close()
        self.assertIs(error.exception,first)
        one.close.assert_called_once(); two.close.assert_called_once()
        report.close()
        self.assertEqual(one.close.call_count,2)
        self.assertEqual(two.close.call_count,1)

    def test_completed_manifest_rollback_failure_keeps_its_data(self):
        """锁释放及清单撤回同时失败，完整输出不能被拆坏。参数: 无。返回: None。异常: 断言。"""
        from chronaxis.results import AnalysisError
        for rollback_error in (OSError, FileNotFoundError):
            with tempfile.TemporaryDirectory() as directory:
                root=Path(directory); result=make_result(root,[sample_event(),sample_calculation()])
                from chronaxis.results.publication import move_no_replace
                close=PublicationNames.close; rename=move_no_replace; calls=0
                def fail_close(owner):
                    """首次释放锁失败，后续可恢复。参数: owner。返回: None。异常: OSError。"""
                    nonlocal calls
                    calls+=1
                    if calls==1: raise OSError('lock failure')
                    close(owner)
                def fail_rollback(source,target):
                    """只阻止已发布清单撤回。参数: 路径。返回: None。异常: OSError。"""
                    if Path(target).name=='run_manifest.json': raise rollback_error('manifest locked')
                    rename(source,target)
                with patch.object(PublicationNames,'close',fail_close),patch('chronaxis.results.publication.move_no_replace',fail_rollback):
                    with self.assertRaises(AnalysisError) as error: result.write(root/'output')
                manifest=error.exception.completed_manifest
                document=json.loads(manifest.manifest_path.read_text(encoding='utf-8'))
                self.assertTrue(all((manifest.output_dir/f['name']).is_file() for f in document['outputs']))
                result.close()
                self.assertTrue(manifest.manifest_path.is_file())

    def test_release_failure_preserves_completed_paths(self):
        """发布后的预算释放错误仍携带实际清单供调用方恢复。参数: 无。返回: None。异常: 断言。"""
        from chronaxis.results.budget import _release_owned_ram
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); result=make_result(root,[sample_event(),sample_calculation()])
            def release(owner,amount,slot):
                """只在write最终释放槽制造故障。参数: 原账本参数。返回: None。异常: OSError。"""
                if owner is result and slot=='_writer_cost': raise OSError('release failure')
                return _release_owned_ram(owner,amount,slot)
            with patch('chronaxis.results.result._release_owned_ram',release):
                with self.assertRaisesRegex(OSError,'release failure') as error: result.write(root/'output')
            manifest=error.exception.completed_manifest
            self.assertTrue(manifest.manifest_path.is_file())
            self.assertTrue(all(p.is_file() for p in manifest.output_files))
            result.close()

    def test_failed_batch_keeps_report_path_after_cleanup_error(self):
        """基础设施失败的报告已落盘而收尾失败时仍保存实际路径。参数: 无。返回: None。异常: 断言。"""
        from chronaxis.batch.models import BatchPlan, BatchReport
        from chronaxis.batch.api import run_batch
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); first=RuntimeError('scheduler failure')
            first.batch_report=BatchReport(root,(),1,False,False,'home')
            original=Path.rmdir; failed=False
            def remove(path):
                """只让第一次报告空目录删除失败。参数: 路径。返回: None。异常: OSError。"""
                nonlocal failed
                if path.name.startswith('.batch-report-') and not failed:
                    failed=True
                    raise OSError('cleanup')
                original(path)
            with patch('chronaxis.batch.api.BatchRunner.run',side_effect=first),patch.object(Path,'rmdir',remove):
                with self.assertRaises(RuntimeError) as error: run_batch(BatchPlan(()),root)
            self.assertIs(error.exception,first)
            self.assertTrue(first.batch_report.report_path.is_file())

    def test_cancel_after_manifest_move_rolls_back_a_complete_set(self):
        """系统调用已移动清单再取消时仍能回滚整组。参数: 无。返回: None。异常: 断言。"""
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); temp=root/'temporary'; temp.mkdir()
            for name in ('data.csv','manifest.json'): (temp/name).write_text(name)
            names=PublicationNames(root/'output',('data.csv','manifest.json'))
            def move(source,target):
                """真实rename完成之后模拟取消。参数: 路径。返回: None。异常: KeyboardInterrupt。"""
                os.rename(source,target)
                if source.name=='manifest.json': raise KeyboardInterrupt('after move')
            with self.assertRaises(KeyboardInterrupt): names.publish(temp,'manifest.json',move)
            self.assertFalse(tuple(names.root.iterdir()))
            self.assertEqual({p.name for p in temp.iterdir()},{'data.csv','manifest.json'})
