"""验证CAN FD错误诊断的标准布局和真实时钟推进，不把损坏的部分帧用于解码。

使用Vector规范字段顺序的合成数据，沿用ASCRead真实入口与原有预算清理夹具。
"""
import unittest
import test_asc_source as asc_fixtures
import test_fast_session as fast_fixtures
from chronaxis import AnalysisRunner, load_analysis_plan
from chronaxis.sources.raw_can import CANTextError


def fd_error(*, phase='Arb.', length=2, payload='12 34', flags='17'):
    """生成一条完整FD错误帧，诊断DLC故意大于取得的部分载荷。

    参数: phase、length、payload、flags为需要探测的独立字段。
    返回: 无时间前缀的ASC行。异常: 无主动异常。
    """
    return (f'CANFD 2 Tx ErrorFrame Example receive error fffe c7 31ca {phase} '
            f'5 123 1 1 f {length} {payload} 11984 {flags} 0 46500250 460a0250 20011736 20010205')


class FDErrorDiagnosticTests(unittest.TestCase):
    """每例单独创建读取器，失败也应释放全部已预付费用。"""

    def setUp(self):
        """复用ASC输入夹具。参数: 无。返回: None。异常: 文件准备错误。"""
        self.fixture = asc_fixtures.ASCSourceTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_partial_payload_is_not_normal_data(self):
        """两个已取得字节不要求等于DLC15，但不能进入正常信号载荷。

        参数: 无。返回: None。异常: 断言失败。
        """
        for phase in ('Arb.', 'Data.'):
            with self.subTest(phase=phase):
                record = self.fixture.read('0.2 ' + fd_error(phase=phase) + '\n')[0]
                frame = record.frame
                self.assertEqual((frame.is_fd, frame.is_rx, frame.channel), (True, False, 1))
                self.assertTrue(frame.is_error_frame)
                self.assertTrue(frame.bitrate_switch and frame.error_state_indicator)
                self.assertEqual((frame.arbitration_id, frame.data), (0, b''))
                self.assertIsNone(record.dlc_code)
                self.assertEqual(self.fixture.budget.ram_bytes, 0)

    def test_classic_error_on_fd_channel_and_relative_clock(self):
        """FD通道上的经典错误仍推进相邻事件时差，后续有效数据保留0.3秒。

        参数: 无。返回: None。异常: 断言失败。
        """
        records = self.fixture.read('0.1 ' + fd_error(length=0, payload='', flags='10') +
                                    '\n0.2 1 123 Rx d 1 05\n',
                                    header='base hex timestamps relative\n')
        self.assertFalse(records[0].frame.is_fd)
        self.assertTrue(records[0].frame.is_error_frame)
        self.assertEqual([row.time_ns for row in records], [100000000, 300000000])
        self.assertEqual(records[1].frame.data, b'\x05')

    def test_unknown_or_broken_diagnostics_fail(self):
        """残缺字段、非法字节、未定义阶段和保留位不能被错误帧标签掩盖。

        参数: 无。返回: None。异常: 未拒绝坏输入时断言失败。
        """
        malformed = (fd_error(phase='Unknown'), fd_error(length=3),
                     fd_error(payload='100 00'), fd_error(flags='20'),
                     fd_error().rsplit(' ', 1)[0], fd_error() + ' extra',
                     'CANFD 1 Rx ErrorFrame ECC: 10100010')
        for body in malformed:
            with self.subTest(body=body), self.assertRaises(CANTextError):
                self.fixture.read('0 ' + body + '\n')
            self.assertEqual(self.fixture.budget.ram_bytes, 0)

    def test_public_ordinary_and_fast_ignore_error_payload(self):
        """同一文件的错误帧不贡献能量，普通与fast公开入口仍得到两条有效报文的800J。

        参数: 无。返回: None。异常: 输入、执行或断言失败。
        """
        fixture = fast_fixtures.FastSessionTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        path = fixture.paths[0]
        path.write_text(fast_fixtures.HEADER + '0 1 100 Rx d 2 A0 0F\n'
                        + '0.5 ' + fd_error() + '\n1 1 100 Rx d 2 A0 0F\n', encoding='ascii')
        fixture.raw['sources'][0]['paths'] = [str(path)]
        config = fixture.config(count=1)
        rows, report = fixture.result(config)
        self.assertEqual((rows[0]['value'], rows[0]['unit']), (800.0, 'J'))
        result = AnalysisRunner().run(load_analysis_plan(config))
        budget = result.spool.budget
        try:
            rows = tuple(result.iter_calculations())
            self.assertEqual((rows[0].value, rows[0].unit, rows[0].status), (800.0, 'J', 'complete'))
        finally:
            result.close()
        self.assertEqual(budget.ram_bytes, 0)


if __name__ == '__main__':
    unittest.main()
