"""用手算间隔及三格式连续小文件核对驱动推进；不提前开放schema2执行。"""

import unittest

from chronaxis.core.record_intervals import RecordIntervals, clipped_record_seconds
from chronaxis.core.models import Interval
from chronaxis.timebase.conversion import TimeOverflowError,INT64_MIN,INT64_MAX
from chronaxis.sources.text_can_spec import CANTextSpec
from chronaxis.execution.text_can_reader import BudgetedTextCANSourceAdapter
import test_raw_can_continuous as continuous


class RecordIntervalTests(unittest.TestCase):
    """只验记录对间隔；事件等待、积分尾段及窗口裁剪留给相应消费者测试。"""

    def test_actual_and_fixed_use_same_actual_timestamps(self):
        """10/10.12/10.30对应120/180ms或两个100ms。参数: 无。返回: None。异常: 断言失败。"""
        actual=RecordIntervals();fixed=RecordIntervals(100_000_000)
        times=(10_000_000_000,10_120_000_000,10_300_000_000)
        self.assertEqual([actual.advance(t) for t in times],[None,120_000_000,180_000_000])
        self.assertEqual([fixed.advance(t) for t in times],[None,100_000_000,100_000_000])
        self.assertEqual(times[-1],10_300_000_000)

    def test_empty_single_same_time_and_independent_tasks(self):
        """N条对应N−1段；同刻实际差为0，固定周期仍推进。参数: 无。返回: None。异常: 断言失败。"""
        for period,expected in ((None,0),(10,10)):
            state=RecordIntervals(period)
            self.assertIsNone(state.advance(5))
            self.assertEqual(state.advance(5),expected)
            self.assertIsNone(RecordIntervals(period).advance(5))

    def test_invalid_updates_are_not_skipped(self):
        """无效更新拆开两段，不能直接连接前后有效记录。参数: 无。返回: None。异常: 断言失败。"""
        for period,expected in ((None,[None,120,180]),(100,[None,100,100])):
            clock=RecordIntervals(period)
            updates=((1000,11),(1120,None),(1300,15))
            pairs=[];previous=None
            for time,value in updates:
                step=clock.advance(time)
                pairs.append((step,previous,value))
                previous=value
            self.assertEqual([p[0] for p in pairs],expected)
            self.assertEqual(pairs[1][1:],(11,None))
            self.assertEqual(pairs[2][1:],(None,15))

    def test_bad_time_and_overflow_do_not_advance_state(self):
        """非法更新失败不污染此前状态；固定周期不计算无用实际跨度。参数: 无。返回: None。异常: 断言失败。"""
        clock=RecordIntervals()
        self.assertIsNone(clock.advance(10))
        for bad in (True,10.0,'10',None):
            with self.assertRaises(TypeError):clock.advance(bad)
        with self.assertRaisesRegex(ValueError,'回退'):clock.advance(9)
        self.assertEqual(clock.advance(12),2)
        with self.assertRaises(TimeOverflowError):clock.advance(INT64_MAX+1)
        self.assertEqual(clock.advance(13),1)
        clock=RecordIntervals();clock.advance(INT64_MIN)
        with self.assertRaises(TimeOverflowError):clock.advance(INT64_MAX)
        self.assertEqual(clock.advance(INT64_MIN+1),1)
        fixed=RecordIntervals(100);fixed.advance(INT64_MIN)
        self.assertEqual(fixed.advance(INT64_MAX),100)

    def test_invalid_periods_are_rejected_before_input(self):
        """周期需正整数；不接受bool/float或越界。参数: 无。返回: None。异常: 断言失败。"""
        for value in (0,-1):
            with self.assertRaises(ValueError):RecordIntervals(value)
        for value in (True,1.0,'1'):
            with self.assertRaises(TypeError):RecordIntervals(value)
        with self.assertRaises(TimeOverflowError):RecordIntervals(INT64_MAX+1)

    def test_chunk_boundaries_never_reset_the_cursor(self):
        """同一前序跨批/文件，分块方式不改变结果。参数: 无。返回: None。异常: 断言失败。"""
        times=(0,0,4,9,10)
        for period in (None,3):
            for size in (1,2,5):
                state=RecordIntervals(period);steps=[]
                for start in range(0,len(times),size):
                    steps.extend(state.advance(t) for t in times[start:start+size])
                self.assertEqual(steps,[None,0,4,5,1] if period is None else [None,3,3,3,3])


class ClippedRecordIntervalTests(unittest.TestCase):
    """手算窗口交集，覆盖不足一纳秒的权重和跨批前序状态。"""

    def test_confirmed_half_period_and_actual_energy(self):
        """固定半周期200J，实际60ms为240J。参数: 无。返回: None。异常: 断言失败。"""
        start, end = 10_000_000_000, 10_120_000_000
        window = Interval(10_060_000_000, end)
        self.assertEqual(4000 * clipped_record_seconds(start, end, window, step_ns=100_000_000), 200)
        self.assertEqual(4000 * clipped_record_seconds(start, end, window), 240)
        self.assertEqual(4000 * clipped_record_seconds(start, end, Interval(start, end), step_ns=100_000_000), 400)

    def test_middle_clip_fractional_ns_and_large_coordinates(self):
        """两端裁剪和大绝对时间保持比例，不把三分之一纳秒截为零。参数: 无。返回: None。异常: 断言失败。"""
        for origin in (0, INT64_MAX - 12, INT64_MIN):
            self.assertEqual(clipped_record_seconds(origin, origin + 12,
                Interval(origin + 3, origin + 9), step_ns=10), 5e-9)
        self.assertAlmostEqual(clipped_record_seconds(0, 3, Interval(1, 2), step_ns=1), 1 / 3e9, delta=1e-25)
        # 两端各合法而记录对跨度超过int64；固定比例在Python整数域计算。
        self.assertGreater(clipped_record_seconds(INT64_MIN, INT64_MAX, Interval(0, 1), step_ns=INT64_MAX), 0)

    def test_empty_touching_and_zero_span_have_no_area(self):
        """无交集、接边、零窗口及同刻记录不产生连续面积。参数: 无。返回: None。异常: 断言失败。"""
        for period in (None, 100):
            for window in (Interval(-5, 0), Interval(10, 15), Interval(3, 3)):
                self.assertEqual(clipped_record_seconds(0, 10, window, step_ns=period), 0)
            self.assertEqual(clipped_record_seconds(4, 4, Interval(0, 10), step_ns=period), 0)

    def test_bad_arguments_fail_without_advancing(self):
        """错误时间/周期/窗口不污染已有游标。参数: 无。返回: None。异常: 断言失败。"""
        for period in (True, 1.5, '1'):
            with self.assertRaises(TypeError):
                clipped_record_seconds(0, 10, Interval(0, 10), step_ns=period)
        for period in (0, -1):
            with self.assertRaises(ValueError):
                clipped_record_seconds(0, 10, Interval(0, 10), step_ns=period)
        with self.assertRaises(TimeOverflowError):
            clipped_record_seconds(0, 10, Interval(0, 10), step_ns=INT64_MAX + 1)
        for bad in (True, 1.0, '1', INT64_MAX + 1):
            with self.assertRaises((TypeError, TimeOverflowError)):
                clipped_record_seconds(bad, 10, Interval(0, 10))
        clock = RecordIntervals(6)
        window = Interval(10, 20)
        self.assertIsNone(clock.advance_seconds(8, window))
        with self.assertRaisesRegex(ValueError, '回退'):
            clock.advance_seconds(7, window)
        with self.assertRaises(TypeError):
            clock.advance_seconds(12, (10, 20))
        self.assertEqual(clock.advance_seconds(12, window), 3e-9)

    def test_outside_invalid_updates_and_chunks_keep_pair_boundaries(self):
        """窗口前无效记录仍覆盖前值，按原记录对分母折算；分批不改变面积。参数: 无。返回: None。异常: 断言失败。"""
        records = ((0, 10.0), (4, None), (8, 20.0), (12, 30.0))
        for size in (1, 2, 4):
            clock = RecordIntervals(2)
            previous, area = None, 0.0
            for index in range(0, len(records), size):
                for time, value in records[index:index + size]:
                    seconds = clock.advance_seconds(time, Interval(6, 10))
                    if seconds is not None and previous is not None:
                        area += previous * seconds
                    previous = value
            # 6—8ns前值无效；8—10ns占8—12ns的一半，20×1ns。
            self.assertEqual(area, 2e-8)


class RecordIntervalInputTests(unittest.TestCase):
    """共同消息消费者实际接入BLF/ASC/CSV，按原报文身份选步进。"""

    setUp=continuous.RawCANContinuousTests.setUp
    asc=continuous.RawCANContinuousTests.asc
    csv=continuous.RawCANContinuousTests.csv
    blf=continuous.RawCANContinuousTests.blf
    multiplex=continuous.RawCANContinuousTests.multiplex
    adapter=continuous.RawCANContinuousTests.adapter
    consume=continuous.RawCANContinuousTests.consume

    def test_three_formats_keep_intervals_across_invalid_and_file_boundary(self):
        """0/1/3秒分在两文件；11/None/15照常形成两段。参数: 无。返回: None。异常: 断言失败。"""
        self.multiplex()
        paths=(self.blf([(0,b'\x01\x05')]),self.blf([(1,b'\x02\x06'),(3,b'\x01\x07')]))
        parsers=((self.asc('0 1 100 Rx d 2 01 05\n'),self.asc('1 1 100 Rx d 2 02 06\n3 1 100 Rx d 2 01 07\n')),
                 (self.csv('0,100,01 05,2\n'),self.csv('1,100,02 06,2\n3,100,01 07,2\n')))
        for inputs in (None,*parsers):
            actual=RecordIntervals();fixed=RecordIntervals(100_000_000);rows=[]
            def collect(update):
                """实际消息按固定物理身份推进，两种模式分开验收。参数: update。返回: None。异常: 断言失败。"""
                identity=(update.source_ref.source_name,update.channel,update.frame_id,update.is_extended,update.is_fd)
                if identity==('bus',0,256,False,False):
                    rows.append((actual.advance(update.time_ns),fixed.advance(update.time_ns),update.values['Voltage']))
            adapter=self.adapter(paths,collect) if inputs is None else BudgetedTextCANSourceAdapter(
                self.budget,CANTextSpec('bus',inputs,self.dbc,0,self.timebase,'strict'),'session',
                (self.signal,),message_consumer=collect)
            self.consume(adapter)
            self.assertEqual(rows,[(None,None,11),(10**9,100_000_000,None),(2*10**9,100_000_000,15)])
            self.assertEqual(self.budget.ram_bytes,0)


if __name__=='__main__':
    unittest.main()
