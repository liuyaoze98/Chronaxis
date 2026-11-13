"""用小型合成输入验证默认CSV和ASC兼容边界，不读取或修改历史日志。

CSV覆盖BOM、匿名尾列和真实物理行；ASC覆盖未知DLC、状态计时、错误帧诊断及统计尾。
预期字段由输入直接手算，两种信号后端均核对。文件只写AUDIT-FIX-02独立工作目录，
每次读取显式关闭并检查预算归还；未知布局、数据损坏和非空匿名列不得静默跳过。
"""

from pathlib import Path
import unittest
from uuid import uuid4

from chronaxis.core.binding import SignalDefinition
from chronaxis.core.models import TimebaseSpec
from chronaxis.core.types import SignalDType, TimeType
from chronaxis.planning.inputs import parse_sources
from chronaxis.results.budget import ResourceBudget
from chronaxis.sources import ReadRequest, SignalCSVSourceAdapter, SignalCSVSpec, SourceReadError
from chronaxis.sources.asc import ASCRead, ASCSpec
from chronaxis.sources.raw_can import CANTextError


class AuditInputCompatibilityTests(unittest.TestCase):
    """各测试独立保存受控输入；不将读取器输出当作自己的预期答案。"""

    def setUp(self):
        """创建本任务的独立工作目录。参数: 无。返回: None。异常: 文件系统写入失败。"""
        self.root = Path('work/audit-fix-02/input-compatibility') / uuid4().hex
        self.root.mkdir(parents=True)

    def csv_values(self, body, *, backend='reference', encoding=None, file_encoding='utf-8', field='power'):
        """消费一个小信号表并提取数值及物理行号，结束时关闭来源。

        参数: body为CSV文本；backend为计算后端；encoding省略时使用产品默认；
            file_encoding只控制夹具写出；field为已知功率列原名。
        返回: (数值列表, 物理行列表)。异常: SourceReadError保留被测输入错误。
        """
        path = self.root / (uuid4().hex + '.csv')
        path.write_text(body, encoding=file_encoding, newline='')
        options = {} if encoding is None else {'encoding': encoding}
        spec = SignalCSVSpec('table', (path,), TimebaseSpec('clock', TimeType.RELATIVE, 'fixture'),
                             'time', 's', **options)
        signal = SignalDefinition('power', 'table', field, SignalDType.FLOAT64, 'W', 10**9)
        adapter = SignalCSVSourceAdapter(spec, 'session', (signal,), backend=backend)
        try:
            # 一条一批同时覆盖匿名尾校验与批次边界；不改变输入中的真实时间。
            batches = list(adapter.iter_batches(ReadRequest('session', ('power',), 0, 10**9, 1)))
            columns = [batch.series['power'] for batch in batches if 'power' in batch.series]
            return ([float(value) for column in columns for value in column.values],
                    [reference.line_number for column in columns for reference in column.source_ref])
        finally:
            adapter.close()

    def asc_records(self, body, *, version='vector-asc-v1', relative=False, selector=None):
        """读取单个ASC夹具，保证失败也归还读取预算。

        参数: body不含头；version选择既有格式；relative控制头部计时；selector为可选帧筛选。
        返回: RawCANRecord列表。异常: CANTextError为被测格式/时间错误，I/O异常原样传播。
        """
        path = self.root / (uuid4().hex + '.asc')
        mode = 'relative' if relative else 'absolute'
        path.write_text(f'base hex timestamps {mode}\n' + body, encoding='utf-8')
        budget = ResourceBudget()
        try:
            with ASCRead(ASCSpec(path, parser_version=version), budget, time_selector=selector) as reader:
                return list(reader)
        finally:
            self.assertEqual(budget.ram_bytes, 0)

    def test_csv_default_accepts_plain_and_bom_for_both_backends(self):
        """参数: 无。返回: None。异常: 断言失败；默认解码不依赖Excel额外配置。"""
        for backend in ('reference', 'numpy'):
            for prefix in ('', '\ufeff'):
                with self.subTest(backend=backend, bom=bool(prefix)):
                    self.assertEqual(self.csv_values(prefix + 'time,power\n0,10\n1,20\n', backend=backend),
                                     ([10.0, 20.0], [2, 3]))

    def test_csv_plan_default_and_explicit_encoding(self):
        """参数: 无。返回: None。异常: 断言失败；静态配置默认与直接来源默认一致。"""
        raw = {'name': 'table', 'source_type': 'signal_csv', 'path': 'unused.csv',
               'time_column': 'time', 'time': {'unit': 's'}}
        self.assertEqual(parse_sources([raw], self.root.resolve())[0].config.encoding, 'utf-8-sig')
        self.assertEqual(parse_sources([dict(raw, encoding='gbk')], self.root.resolve())[0].config.encoding, 'gbk')
        self.assertEqual(self.csv_values('time,power\n0,10\n', encoding='gbk', file_encoding='gbk')[0], [10.0])
        # 显式UTF-8不自动覆盖；失败应给出BOM修正方式。
        with self.assertRaisesRegex(SourceReadError, 'utf-8-sig'):
            self.csv_values('\ufefftime,power\n0,10\n', encoding='utf-8')

    def test_csv_empty_tail_handles_quotes_multiline_and_omitted_empty_cells(self):
        """参数: 无。返回: None。异常: 断言失败；只放宽表尾空格位，不丢有名列。"""
        body = '\ufefftime,power,note,,\n0,10,"first\nsecond",,\n1,20,"comma,text"\n'
        for backend in ('reference', 'numpy'):
            with self.subTest(backend=backend):
                self.assertEqual(self.csv_values(body, backend=backend), ([10.0, 20.0], [3, 4]))

    def test_csv_nonempty_anonymous_tail_and_bad_headers_still_fail(self):
        """参数: 无。返回: None。异常: 断言失败；匿名非空数据、短行和中间空名不能被修剪。"""
        bodies = ('time,power,\n0,10,secret\n', 'time,power,\n0,10, \n',
                  'time,power,\n0,10,,\n', 'time,power,,\n0\n',
                  'time,,power\n0,,10\n', 'time,power,power,\n0,10,10,\n',
                  'time,power, \n0,10,\n', ',,\n,,\n')
        for body in bodies:
            with self.subTest(body=body), self.assertRaises(SourceReadError):
                self.csv_values(body)

    def test_csv_does_not_remove_internal_bom(self):
        """参数: 无。返回: None。异常: 断言失败；只处理文件首BOM，列名与单元格原文保留。"""
        self.assertEqual(self.csv_values('time,po\ufeffwer\n0,10\n', field='po\ufeffwer')[0], [10.0])
        with self.assertRaises(SourceReadError):
            self.csv_values('time,power\n0,1\ufeff0\n')

    def test_csv_bad_anonymous_multiline_reports_record_end(self):
        """参数: 无。返回: None。异常: 断言失败；错误仍定位到CSV记录结束物理行。"""
        with self.assertRaises(SourceReadError) as caught:
            self.csv_values('time,power,\n0,10,"hidden\nvalue"\n')
        self.assertIn(':3:', str(caught.exception))
        self.assertIn('匿名列', str(caught.exception))

    def test_remote_without_dlc_is_distinct_from_explicit_zero(self):
        """参数: 无。返回: None。异常: 断言失败；已有可选DLC字段保留未知，不补造长度。"""
        for version in ('vector-asc-v1', 'vector-asc-statistics-v1', 'sclicer-asc-v1'):
            with self.subTest(version=version):
                records = self.asc_records('0 1 100 Rx r\n1 1 100 Tx r 0\n2 2 100x Rx r 8\n', version=version)
                self.assertEqual([record.dlc_code for record in records], [None, 0, 8])
                self.assertTrue(all(record.frame.is_remote_frame and not record.frame.data for record in records))
                self.assertFalse(records[1].frame.is_rx)
                self.assertTrue(records[2].frame.is_extended_id)

    def test_remote_and_data_damage_have_exact_position(self):
        """参数: 无。返回: None。异常: 断言失败；缺DLC仅适用于远程帧，不能放宽普通坏行。"""
        for row in ('1 1 100 Rx d', '1 1 100 Rx r 9', '1 1 100 Rx r 0 ff',
                    '1 1 100 Rx r z', '1 1 100 Rx', '1'):
            with self.subTest(row=row), self.assertRaises(CANTextError) as caught:
                self.asc_records('0 1 100 Rx d 0\n' + row + '\n')
            self.assertEqual(caught.exception.line_number, 3)

    def test_status_events_advance_relative_clock_before_skip(self):
        """参数: 无。返回: None。异常: 断言失败；状态行不产出样本但必须保留后续真实时间。"""
        def selected(frame):
            """参数: frame为已解析原帧。返回: 是否选择0x100。异常: 无；只读身份。"""
            return frame.arbitration_id == 256

        body = ('0.1 1 100 Rx d 0\n0.2 CAN 1 Status:chip status error active\n'
                '0.3 CAN 2 Status: chip Status error passive - TxErr: 8 RxErr: 0\n'
                '0.4 1 100 Rx d 0\n')
        for version in ('vector-asc-v1', 'vector-asc-statistics-v1', 'sclicer-asc-v1'):
            for selector in (None, selected):
                with self.subTest(version=version, selected=selector is not None):
                    records = self.asc_records(body, relative=True, selector=selector, version=version)
                    self.assertEqual([record.time_ns for record in records], [100_000_000, 1_000_000_000])
                    self.assertEqual([record.line_number for record in records], [2, 5])
                    self.assertEqual([record.sequence for record in records], [0, 1])

    def test_each_documented_status_has_the_same_nonframe_behavior(self):
        """参数: 无。返回: None。异常: 断言失败；公开列出的状态均只推进时钟。"""
        for state in ('error active', 'error passive', 'warning level', 'busoff', 'bus off'):
            with self.subTest(state=state):
                rows = self.asc_records(f'0.1 CAN 1 Status:chip status {state}\n0.2 1 100 Rx d 0\n', relative=True)
                self.assertEqual([row.time_ns for row in rows], [300_000_000])

    def test_status_unknown_and_malformed_lines_are_not_skipped(self):
        """参数: 无。返回: None。异常: 断言失败；通道、计数和未知事件仍严格拒绝。"""
        rows = ('1 CAN 0 Status:chip status error active', '1 CAN 1 Status:chip status unknown',
                '1 CAN 1 Status:chip status error active - TxErr: 0',
                '1 CAN 1 Status:chip status error active - TxErr: -1 RxErr: 0',
                '1 CAN 1 Status:chip status error active junk', '1 CAN 1 arbitrary text')
        for row in rows:
            with self.subTest(row=row), self.assertRaises(CANTextError) as caught:
                self.asc_records('0 1 100 Rx d 0\n' + row + '\n')
            self.assertEqual(caught.exception.line_number, 3)
        with self.assertRaisesRegex(CANTextError, '回退'):
            self.asc_records('1 1 100 Rx d 0\n0.9 CAN 1 Status:chip status error active\n')

    def test_classic_error_diagnostics_are_error_frames_only(self):
        """参数: 无。返回: None。异常: 断言失败；诊断ID和DLC不冒充正常帧身份。"""
        body = ('0 1 ErrorFrame ECC:10100010\n1 1 ErrorFrame ECC: 10100010\n'
                '2 2 ErrorFrame Flags = 0xe CodeExt = 0x20a2 Code = 0x82 '
                'ID = 291 DLC = 8 Position = 5 Length = 11300\n')
        for version in ('vector-asc-v1', 'vector-asc-statistics-v1', 'sclicer-asc-v1'):
            with self.subTest(version=version):
                records = self.asc_records(body, version=version)
                self.assertTrue(all(record.frame.is_error_frame for record in records))
                self.assertTrue(all(record.dlc_code is None for record in records))
                self.assertTrue(all(record.frame.arbitration_id == 0 and record.frame.data == b'' for record in records))

    def test_bad_error_diagnostics_are_not_discarded(self):
        """参数: 无。返回: None。异常: 断言失败；诊断尾也检查结构、字段顺序及数值。"""
        rows = ('1 1 ErrorFrame ECC: 1010001', '1 1 ErrorFrame ECC: 10100012',
                '1 1 ErrorFrame ECC: 10100010 garbage', '1 1 ErrorFrame unknown',
                '1 1 ErrorFrame Flags = 0xe CodeExt = 0x20a2 Code = 0x82 ID = 0 DLC = 0 Position = 5',
                '1 1 ErrorFrame Flags = 0xe CodeExt = 0x20a2 Code = invalid ID = 0 DLC = 0 Position = 5 Length = 3',
                '1 CANFD 1 Rx ErrorFrame ECC: 10100010')
        for row in rows:
            with self.subTest(row=row), self.assertRaises(CANTextError) as caught:
                self.asc_records('0 1 100 Rx d 0\n' + row + '\n')
            self.assertEqual(caught.exception.line_number, 3)

    def test_default_statistics_tail_keeps_identity_and_dlc(self):
        """参数: 无。返回: None。异常: 断言失败；默认入口与显式统计布局使用同一严格解析。"""
        body = ('0 1 123 Rx d 1 ff Length = 1 BitCount = 8 ID = 291\n'
                '1 1 123 Tx r Length = 1 BitCount = 8 ID = 291\n')
        for version in ('vector-asc-v1', 'vector-asc-statistics-v1'):
            with self.subTest(version=version):
                records = self.asc_records(body, version=version)
                self.assertEqual(records[0].frame.data, b'\xff')
                self.assertEqual(records[0].frame.arbitration_id, 291)
                self.assertIsNone(records[1].dlc_code)

    def test_default_statistics_tail_rejects_identity_and_layout_damage(self):
        """参数: 无。返回: None。异常: 断言失败；不能用自动识别掩盖尾字段坏值。"""
        tails = ('Length = 1 BitCount = 8 ID = 292', 'Length = 1 BitCount = 8 ID = 0x123',
                 'Length = -1 BitCount = 8 ID = 291', 'Length = 1 ID = 291',
                 'Length = 1 BitCount = 8 ID = 291 junk', 'Length = 1 ID = 291 BitCount = 8')
        for tail in tails:
            with self.subTest(tail=tail), self.assertRaises(CANTextError) as caught:
                self.asc_records('0 1 100 Rx d 0\n1 1 123 Rx d 1 ff ' + tail + '\n')
            self.assertEqual(caught.exception.line_number, 3)


if __name__ == '__main__':
    unittest.main()
