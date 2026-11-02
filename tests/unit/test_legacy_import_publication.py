"""以真实文件核旧配置三件发布、计划最后提交及取消后原FD恢复，产物home。

输入来自稳定Sclicer字节/文件API，原INI含BOM与CRLF以核精确保留。成功产物
经公开load_analysis_plan从另一个输出目录回读，失败转换只保原文/报告。真实Windows
rename用于已有目标和安装竞态，不能靠mock宣称no-replace已验证。

故障只透明代理本次Path.open返回的实际FD或在真实安装前抛出原异常；持续
close失败仍持同一个句柄和恢复owner。测试不运行旧链、分析源或DBC，不写Ref，
所有新文件留于work/m2-import-tests，根统一正式执行和保存验证记录。
"""

from dataclasses import FrozenInstanceError, replace
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from chronaxis import load_analysis_plan
from chronaxis.migration import import_legacy_ini, load_legacy_ini
from chronaxis.migration import publication
from chronaxis.migration.publication import LegacyImportFiles, write_legacy_import
from test_legacy_import_sclicer import mapping_fixture
from test_legacy_import_sum import legacy_ini, legacy_mapping_fixture


ROOT = Path(__file__).absolute().parents[2]


class ActualPublicationFile:
    """透明保真实文件，写后取消与关闭前故障都不替代实际FD。"""

    def __init__(self, actual):
        """保存原FD及禁用故障。参数: actual。返回: 新代理。异常: 无。"""
        self.actual = actual
        self.write_error = self.close_error = None
        self.write_calls = self.close_calls = 0

    def __getattr__(self, name):
        """透传真实属性。参数: name。返回: 原属性。异常: 原属性错误传播。"""
        return getattr(self.actual, name)

    def write(self, value):
        """先执行真实写入再可选取消。参数: value。返回: 实际写入量。异常: 原IO或write_error。"""
        self.write_calls += 1
        amount = self.actual.write(value)
        if self.write_error is not None:
            raise self.write_error
        return amount

    def close(self):
        """真实关闭前可持续失败。参数: 无。返回: 原close结果。异常: close_error或原IO错误。"""
        self.close_calls += 1
        if self.close_error is not None:
            raise self.close_error
        return self.actual.close()


class LegacyImportPublicationTests(unittest.TestCase):
    """仅在实际已声明Windows平台验不覆盖文件安装，目录每例独立。"""

    def setUp(self):
        """生成原配置及显式mapping，不创建分析输入。

        参数: 无。返回: None。异常: 非Windows明确skip；实际目录/配置错误传播。
        """
        if os.name != 'nt':
            self.skipTest('publication明确只支持已验证的Windows no-replace安装')
        self.root = ROOT / 'work/m2-import-tests/publication-home' / uuid4().hex
        self.root.mkdir(parents=True)
        self.input_root = self.root / 'inputs'
        self.input_root.mkdir()
        self.ini, self.mapping = self.input_root / 'source.ini', self.input_root / 'mapping.json'
        self.content = b'\xef\xbb\xbf[TRIGGER_test]\r\nmode=single\r\nexpr=OBC_OpMod==2\r\n'
        self.ini.write_bytes(self.content)
        self.mapping.write_text(json.dumps(mapping_fixture()), encoding='utf-8')
        self.result = load_legacy_ini(self.ini, self.mapping, mode='sclicer_single', device_label='home')
        self.assertIsNotNone(self.result.plan, self.result.report.to_dict())
        self.handles, self.owners = [], []

    def tearDown(self):
        """解除本例真实FD故障并从原恢复owner关闭，不删除已发布文件。

        参数: 无。返回: None。异常: 实际关闭错误不吞；工作目录保留作证据。
        """
        for handle in self.handles:
            handle.close_error = handle.write_error = None
        for owner in reversed(self.owners):
            owner.close()
        for handle in self.handles:
            if not handle.closed:
                handle.close()

    def targets(self, output):
        """按合同独立列出三个固定目标。参数: output。返回: 三Path tuple。异常: 无。"""
        return (output, output.with_name(output.stem + '.original.ini'),
            output.with_name(output.stem + '.migration-report.json'))

    def test_success_original_bytes_relocated_plan_and_conversion_report(self):
        """成功三件真实回读，计划搬到新目录仍保mapping原来源绝对定位。

        参数: 无。返回: None。异常: 内容、路径、身份或冻结返回对象不符时失败。
        """
        output = self.root / 'other/output.json'
        files = write_legacy_import(self.result, output, source_paths=(self.ini, self.mapping))
        self.assertIs(type(files), LegacyImportFiles)
        self.assertEqual((files.plan, files.original, files.report), self.targets(output))
        self.assertEqual(files.original.read_bytes(), self.content)
        report = json.loads(files.report.read_text(encoding='utf-8'))
        self.assertEqual((report['status'], report['plan_identity'], report['device_label']),
            ('success', self.result.plan.identity, 'home'))
        self.assertNotIn('completed', report.values())
        plan = load_analysis_plan(files.plan)
        self.assertEqual(plan.identity, self.result.plan.identity)
        self.assertEqual(plan.raw_config['sources'][0]['path'],
            str((self.input_root / 'missing/input.csv').absolute()))
        with self.assertRaises(FrozenInstanceError):
            files.plan = None
        self.assertFalse(tuple(output.parent.glob('*.tmp')))

    def test_failed_conversion_saves_original_and_failed_report_without_plan(self):
        """转换失败仍保存原bytes和失败报告，但绝不生成计划。

        参数: 无。返回: None。异常: 部分计划、原文或状态错误时失败。
        """
        content = b'[TRIGGER_test]\nmode=start_end\nexpr=OBC_OpMod==2\n'
        failed = import_legacy_ini(content, mapping_fixture(), mode='sclicer_single',
            base_dir=self.input_root, device_label='home')
        self.assertIsNone(failed.plan)
        output = self.root / 'failed/output.json'
        files = write_legacy_import(failed, output)
        self.assertIsNone(files.plan)
        self.assertFalse(output.exists())
        self.assertEqual(files.original.read_bytes(), content)
        report = json.loads(files.report.read_text(encoding='utf-8'))
        self.assertEqual(report['status'], 'failed')
        self.assertIsNone(report['plan_identity'])

    def test_multi_parameter_legacy_sum_publication_keeps_declaration_and_expression_identity(self):
        """多参数原序参与声明身份，普通/分桶两种计划写读都不能被JSON键排序改变。

        参数: 无；两后端仅静态构建，来源/DBC均不存在。返回: None。
        异常: 参数tuple、原值/单位、声明身份或静态公式事实变化即失败。
        """
        for backend in ('reference', 'numpy'):
            for bucketed in (False, True):
                with self.subTest(backend=backend, bucketed=bucketed):
                    mapping = legacy_mapping_fixture(disjunction=bucketed, backend=backend)
                    mapping['sections']['integral_energy']['parameter_units']['factorZ'] = '1'
                    content = legacy_ini(disjunction=bucketed, expr='signal_P * period * factorZ')
                    content = content.replace(b'period=0.1\n', b'period=0.1\nfactorZ=3\n')
                    converted = import_legacy_ini(content, mapping, mode='legacy_sum',
                        base_dir=self.input_root, device_label='home')
                    self.assertIsNotNone(converted.plan, converted.report.to_dict())
                    output = self.root / ('ordered-' + backend + '-' + str(bucketed)) / 'output.json'
                    files = write_legacy_import(converted, output)
                    loaded = load_analysis_plan(files.plan)
                    self.assertEqual(loaded.identity, converted.plan.identity)
                    self.assertEqual(len(loaded.message_calculations), 2 if bucketed else 1)
                    self.assertEqual(len(loaded.message_calculations), len(converted.plan.message_calculations))
                    for original, actual in zip(converted.plan.message_calculations, loaded.message_calculations):
                        self.assertEqual(tuple(item.name for item in original.parameters), ('period', 'factorZ'))
                        self.assertEqual(actual.parameters, original.parameters)
                        self.assertEqual(actual.expr.bindings.identity, original.expr.bindings.identity)
                        self.assertEqual(actual.expr.normalized_ast, original.expr.normalized_ast)
                        self.assertEqual(actual.expr.root, original.expr.root)
                        self.assertEqual(actual.expr.identity, original.expr.identity)
                        self.assertEqual(actual.disjunction, original.disjunction)
                    self.assertEqual(files.original.read_bytes(), content)
                    report = json.loads(files.report.read_text(encoding='utf-8'))
                    self.assertEqual(list(report), sorted(report))

    def test_any_existing_target_and_explicit_source_collision_are_preserved(self):
        """三个目标任一已有都整拒；原配置与目标同源也不得覆盖。

        参数: 无。返回: None。异常: 用户bytes变化或生成额外目标即失败。
        """
        for index in range(3):
            with self.subTest(index=index):
                output = self.root / ('existing-' + str(index)) / 'output.json'
                output.parent.mkdir()
                targets = self.targets(output)
                targets[index].write_bytes(b'user-owned')
                with self.assertRaises(FileExistsError):
                    write_legacy_import(self.result, output)
                self.assertEqual(targets[index].read_bytes(), b'user-owned')
                self.assertTrue(all(not path.exists() for i, path in enumerate(targets) if i != index))
        original_mapping = self.mapping.read_bytes()
        with self.assertRaises(ValueError):
            write_legacy_import(self.result, self.mapping, source_paths=(self.ini, self.mapping))
        self.assertEqual(self.mapping.read_bytes(), original_mapping)

    def test_plan_install_is_last_all_fds_closed_and_sidecars_survive_late_failure(self):
        """真实两sidecar先安装，最后计划安装前MemoryError不反删sidecar。

        参数: 无。返回: None。异常: 提前发布计划、FD未关或原MemoryError丢失时失败。
        """
        output = self.root / 'commit/output.json'
        actual_open, rename, order = Path.open, publication.os.rename, []
        marker = MemoryError('before actual plan installation')

        def observed_open(path, mode='r', *args, **kwargs):
            """透明登记本次实际临时FD。参数: Path.open原参数。返回: 原FD/代理。异常: 原IO错误。"""
            actual = actual_open(path, mode, *args, **kwargs)
            if '.import-' not in path.name or mode not in ('x', 'xb'):
                return actual
            handle = ActualPublicationFile(actual)
            self.handles.append(handle)
            return handle

        def observed_rename(source, destination):
            """真实安装sidecar后在计划提交前失败。参数: 原rename路径。返回: 原结果。异常: marker。"""
            self.assertTrue(self.handles and all(handle.closed for handle in self.handles))
            order.append(Path(destination))
            if Path(destination) == output:
                self.assertTrue(all(path.exists() for path in self.targets(output)[1:]))
                self.assertFalse(output.exists())
                raise marker
            return rename(source, destination)

        with patch.object(Path, 'open', new=observed_open), \
                patch.object(publication.os, 'rename', new=observed_rename):
            with self.assertRaises(MemoryError) as caught:
                write_legacy_import(self.result, output)
        self.assertIs(caught.exception, marker)
        self.assertEqual(tuple(order), (*self.targets(output)[1:], output))
        self.assertFalse(output.exists())
        self.assertEqual(self.targets(output)[1].read_bytes(), self.content)
        report = json.loads(self.targets(output)[2].read_text(encoding='utf-8'))
        self.assertEqual(report['status'], 'success')
        self.assertTrue(marker.legacy_import_publication_cleanup_owner.closed)
        self.assertFalse(tuple(output.parent.glob('*.tmp')))

    def test_actual_install_race_never_overwrites_and_uuid_collision_is_not_owned(self):
        """预检查后的真实rename竞态不覆盖；exclusive临时名碰撞不得误删用户文件。

        参数: 无。返回: None。异常: 用户文件变化、误删或计划出现即失败。
        """
        output = self.root / 'race/output.json'
        rename = publication.os.rename
        original_target = self.targets(output)[1]

        def competing(source, destination):
            """在实际第一次rename前插入竞争文件。参数: 原rename路径。返回: 原返回。异常: 原FileExistsError。"""
            if Path(destination) == original_target:
                original_target.write_bytes(b'racing-user-file')
            return rename(source, destination)

        with patch.object(publication.os, 'rename', new=competing):
            with self.assertRaises(FileExistsError):
                write_legacy_import(self.result, output)
        self.assertEqual(original_target.read_bytes(), b'racing-user-file')
        self.assertFalse(output.exists())
        collision_output = self.root / 'collision/output.json'
        collision_output.parent.mkdir()
        token = 'f' * 32
        temporary = collision_output.parent / ('.output.original.ini.import-' + token + '.tmp')
        temporary.write_bytes(b'not-created-by-owner')
        with patch.object(publication, 'uuid4', return_value=SimpleNamespace(hex=token)):
            with self.assertRaises(FileExistsError):
                write_legacy_import(self.result, collision_output)
        self.assertEqual(temporary.read_bytes(), b'not-created-by-owner')
        self.assertTrue(all(not path.exists() for path in self.targets(collision_output)))

    def test_write_then_keyboard_interrupt_retains_real_fd_after_persistent_close_failure(self):
        """原文实际写后KI，持续关闭失败保原KI及同一FD，解除后只清自有临时文件。

        参数: 无。返回: None。异常: 原异常、note、真实FD或恢复责任丢失时失败。
        """
        output = self.root / 'cancel/output.json'
        actual_open = Path.open
        marker, cleanup = KeyboardInterrupt('after real original write'), OSError('persistent actual FD close')

        def failed_open(path, mode='r', *args, **kwargs):
            """仅代理本次原文真实FD。参数: Path.open原参数。返回: 原FD/代理。异常: 原IO错误。"""
            actual = actual_open(path, mode, *args, **kwargs)
            if mode != 'xb' or '.original.ini.import-' not in path.name:
                return actual
            handle = ActualPublicationFile(actual)
            handle.write_error, handle.close_error = marker, cleanup
            self.handles.append(handle)
            return handle

        with patch.object(Path, 'open', new=failed_open):
            with self.assertRaises(KeyboardInterrupt) as caught:
                write_legacy_import(self.result, output)
        self.assertIs(caught.exception, marker)
        owner = marker.legacy_import_publication_cleanup_owner
        self.owners.append(owner)
        handle = self.handles[0]
        self.assertIs(owner._handle, handle)
        self.assertFalse(handle.closed)
        self.assertGreater(handle.write_calls, 0)
        self.assertTrue(any('OSError' in note for note in marker.__notes__))
        for _ in range(3):
            with self.assertRaises(OSError) as secondary:
                owner.close()
            self.assertIs(secondary.exception, cleanup)
            self.assertIs(cleanup.legacy_import_publication_cleanup_owner, owner)
            self.assertFalse(handle.closed)
        self.assertTrue(all(not path.exists() for path in self.targets(output)))
        handle.close_error = None
        owner.close()
        self.assertTrue(handle.closed and owner.closed)
        self.assertFalse(tuple(output.parent.glob('*.tmp')))
        owner.close()

    def test_ref_boundary_and_invalid_result_refuse_before_creation(self):
        """Ref仅检查不写入；后缀或伪造成功/原SHA错误在mkdir前拒绝。

        参数: 无。返回: None。异常: 任何Ref写入、目录创建或坏模型被接受时失败。
        """
        protected = ROOT / 'work/../RefProjects' / ('forbidden-' + uuid4().hex + '.json')
        with patch.object(Path, 'mkdir', side_effect=AssertionError('must refuse before mkdir')), \
                patch.object(Path, 'open', side_effect=AssertionError('must refuse before open')):
            with self.assertRaises(ValueError):
                write_legacy_import(self.result, protected)
            with self.assertRaises(ValueError):
                write_legacy_import(self.result, self.root / 'bad/output.ini')
            bad = replace(self.result, report=replace(self.result.report, source_sha256='0' * 64))
            with self.assertRaises(ValueError):
                write_legacy_import(bad, self.root / 'bad/output.json')
            with self.assertRaises(ValueError):
                write_legacy_import(replace(self.result, plan=None), self.root / 'bad/output.json')
        self.assertFalse((self.root / 'bad').exists())


if __name__ == '__main__':
    # 仅在根显式正式命令中执行，不在开发阶段隐式跑产品或故障案例。
    unittest.main()
