"""用真实BLF/ASC/CSV核共同消息输入，另验缺失、预算、失败及按需跳过。

DBC和文本夹具复用既有小样例；预期3/7/11V由raw*2+1手算，
不把一个入口的输出当作其他入口真值。结果不包含原载荷和双时间。
"""

from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_text_can_decode as fixtures
from chronaxis.core.models import SourceRef
from chronaxis.execution.can_reader import BudgetedLegacyCANSourceAdapter
from chronaxis.execution.text_can_reader import BudgetedTextCANSourceAdapter
from chronaxis.legacy.updates import LegacyDecodedUpdate, LegacyUntimedUpdate
from chronaxis.sources.can_spec import LegacyCANSpec
from chronaxis.sources.can_updates import CANUpdateProjection
from chronaxis.sources.models import ReadRequest
from chronaxis.sources.text_can_spec import CANTextSpec


class CANMessageProjectionTests(unittest.TestCase):
    """每例使用独立文件/预算；回调只保存断言所需的少量标量。"""

    setUp = fixtures.TextCANDecodeTests.setUp
    asc = fixtures.TextCANDecodeTests.asc
    csv = fixtures.TextCANDecodeTests.csv
    reader = fixtures.TextCANDecodeTests.reader

    def blf(self):
        """生成含无关帧及同刻两目标帧的BLF。参数: 无。返回: 路径。异常: 写库/I/O错误。
        """
        import can
        path = self.root/'messages.blf'
        writer = can.BLFWriter(path)
        try:
            for second, frame_id, data in ((0, 257, b'\x00'), (1, 256, b'\x01\x05'),
                                            (1, 256, b'\x03\x06'), (2, 256, b'\x05\x07')):
                writer.on_message_received(can.Message(timestamp=1700000000.0+second,
                    arbitration_id=frame_id, is_extended_id=False, channel=0, data=data))
        finally:
            writer.stop()
        return path

    def consume(self, adapter, names=()):
        """完整读取并关闭，空信号投影仍消费所请求消息。参数: adapter/names。返回: None。异常: 原错误传播。
        """
        try:
            read = adapter.iter_batches(ReadRequest('session', names, 0, 3*10**9, 2))
            try:
                for batch in read:
                    if not batch.source_eof:
                        self.assertEqual(set(batch.series), set(names))
            finally:
                read.close()
        finally:
            adapter.close()

    def test_three_formats_and_two_blf_protocols_deliver_same_needed_values(self):
        """三格式同次消息身份/值/原序一致，不带无关Mode或载荷。参数: 无。返回: None。异常: 断言/真实读错。
        """
        blf = self.blf()
        parsers = (self.asc('0 1 101 Rx d 1 00\n1 1 100 Rx d 2 01 05\n1 1 100 Rx d 2 03 06\n2 1 100 Rx d 2 05 07\n'),
                   self.csv('0,101,00,1\n1,100,01 05,2\n1,100,03 06,2\n2,100,05 07,2\n'))
        for kind in ('blf-single','blf-batch',*parsers):
            rows = []
            def collect(update):
                """只摘录断言值，不留原对象。参数: update。返回: None。异常: 断言失败。
                """
                self.assertIs(type(update), LegacyDecodedUpdate)
                self.assertIs(type(update.source_ref), SourceRef)
                self.assertFalse(hasattr(update, 'raw_time'))
                rows.append((update.sequence, update.evaluation_index, update.time_ns,
                    update.frame_id, update.channel, update.is_extended, update.is_fd, dict(update.values)))
            if isinstance(kind, str):
                spec = LegacyCANSpec('bus',blf,self.dbc,0,self.timebase,
                    offset_ns=-1700000000*10**9,decode_scope='requested' if kind=='blf-batch' else 'all')
                adapter = BudgetedLegacyCANSourceAdapter(self.budget,spec,'session',(self.signal,),
                    work_dir=self.root/kind,retain_raw_frames=False,message_consumer=collect)
            else:
                spec = CANTextSpec('bus',(kind,),self.dbc,0,self.timebase)
                adapter = BudgetedTextCANSourceAdapter(self.budget,spec,'session',(self.signal,),message_consumer=collect)
            self.consume(adapter)
            self.assertEqual(rows,[(1,1,10**9,256,0,False,False,{'Voltage':3}),
                (2,2,10**9,256,0,False,False,{'Voltage':7}),
                (3,3,2*10**9,256,0,False,False,{'Voltage':11})])
            self.assertEqual(self.budget.ram_bytes,0)

    def test_exact_text_nanoseconds_are_not_rebuilt_from_float(self):
        """远离零点仍保精确纳秒，转换不经float秒。参数: 无。返回: None。异常: 断言失败。
        """
        parser = self.csv('1700000000.000000001,100,01 05,2\n')
        times = []
        adapter = BudgetedTextCANSourceAdapter(self.budget,
            CANTextSpec('bus',(parser,),self.dbc,0,self.timebase),'session',(self.signal,),
            message_consumer=lambda value: times.append(value.time_ns))
        self.consume(adapter)
        self.assertEqual(times,[1700000000000000001])
        self.assertEqual(self.budget.ram_bytes,0)

    def test_missing_value_never_reuses_previous_value_and_untimed_is_explicit(self):
        """已有模型保None和无时间，不补上次值或零时间。参数: 无。返回: None。异常: 断言失败。
        """
        frame = SimpleNamespace(channel=0,arbitration_id=256,is_extended_id=False,is_fd=False,
                                is_remote_frame=False,is_error_frame=False)
        projection = CANUpdateProjection('bus','session',(self.field,self.field))
        first = projection.build(frame,0,{'Voltage':3,'Mode':99},1)
        missing = projection.build(frame,1,{'Mode':99},2)
        untimed = projection.build(frame,2,{'Voltage':5},None)
        self.assertEqual(dict(first.values),{'Voltage':3})
        self.assertEqual(dict(missing.values),{'Voltage':None})
        self.assertIs(first.source_ref,missing.source_ref)
        self.assertIs(type(untimed),LegacyUntimedUpdate)
        self.assertIsNone(untimed.time_ns)
        frame.is_extended_id=True
        self.assertIsNone(projection.build(frame,3,{'Voltage':5},3))

    def test_no_consumer_builds_no_message_and_unrequested_signal_is_not_decoded(self):
        """正常信号请求不创建消息，也不核验未请求字段的错误单位。参数: 无。返回: None。异常: 断言失败。
        """
        other=replace(self.signal,name='unused',input_unit='wrong')
        parser=self.asc('0 1 100 Rx d 2 01 05\n')
        adapter=BudgetedTextCANSourceAdapter(self.budget,CANTextSpec('bus',(parser,),self.dbc,0,self.timebase),
            'session',(self.signal,other))
        with patch.object(CANUpdateProjection,'build',side_effect=AssertionError('没有消费者不构造消息')):
            self.consume(adapter,('voltage',))
        self.assertEqual(self.budget.ram_bytes,0)

    def test_unrelated_ids_do_not_query_dbc_in_message_mode(self):
        """原ID先筛，初始化后不重复按ID查DBC，仅目标实际解码一次。参数: 无。返回: None。异常: 断言失败。
        """
        parser=self.asc('0 1 200 Rx d 1 00\n1 1 101 Rx d 1 00\n2 1 100 Rx d 2 01 05\n')
        with self.reader((parser,),classify_unselected=False) as read:
            read._start()
            selected = next(message for message in read._db.messages if message.frame_id == 256)
            with patch.object(read._db,'get_message_by_frame_id',wraps=read._db.get_message_by_frame_id) as lookup, \
                    patch.object(selected, 'decode', wraps=selected.decode) as decode:
                rows=tuple(read)
            self.assertEqual(lookup.call_count,0)
            self.assertEqual(decode.call_count,1)
            self.assertEqual([row.status for row in rows],['unselected','unselected','decoded'])
            self.assertEqual(read.decode_calls,1)
        self.assertEqual(self.budget.ram_bytes,0)

    def test_consumer_failure_preserves_error_and_releases_only_owned_budget(self):
        """回调失败后关闭读取，原异常不换，其他owner的费用不被释放。参数: 无。返回: None。异常: 断言失败。
        """
        failure=RuntimeError('consumer failed')
        def fail(update):
            """模拟真实消费者报错。参数: update。返回: 不返回。异常: 本例原错误。
            """
            raise failure
        self.budget.reserve_ram(17)
        for spec in (CANTextSpec('bus',(self.asc('0 1 100 Rx d 2 01 05\n'),),self.dbc,0,self.timebase),
                     LegacyCANSpec('bus',self.blf(),self.dbc,0,self.timebase,
                         offset_ns=-1700000000*10**9,decode_scope='requested')):
            adapter=(BudgetedTextCANSourceAdapter(self.budget,spec,'session',(self.signal,),message_consumer=fail)
                if type(spec) is CANTextSpec else BudgetedLegacyCANSourceAdapter(self.budget,spec,'session',
                    (self.signal,),work_dir=self.root/'failure',retain_raw_frames=False,message_consumer=fail))
            with self.assertRaises(RuntimeError) as caught:
                self.consume(adapter)
            self.assertIs(caught.exception,failure)
            self.assertEqual(self.budget.ram_bytes,17)
        self.budget.release_ram(17)

    def test_delivery_budget_and_failed_cleanup_keep_recoverable_ownership(self):
        """预约失败不调用消费者，取消与退费同时失败仍保原取消及费用归属。

        参数: 无，使用独立费用槽及已解码最小帧。返回: None。异常: 预算/异常身份或归属不符使断言失败。
        """
        from chronaxis.execution.message_delivery import deliver_message
        from chronaxis.results.budget import _release_owned_ram
        owner=SimpleNamespace(_budget=self.budget,_held_cost=0,_update_cost=0)
        frame=SimpleNamespace(channel=0,arbitration_id=256,is_extended_id=False,is_fd=False,
            is_remote_frame=False,is_error_frame=False)
        projection=CANUpdateProjection('bus','session',(self.field,))
        def forbidden(update):
            """超预算不得进入。参数: update。返回: 不返回。异常: AssertionError。
            """
            self.fail('未付费就调用消费者')
        with patch.object(self.budget,'reserve_ram',side_effect=MemoryError('allocation refused')):
            with self.assertRaises(MemoryError):
                deliver_message(owner,projection,forbidden,frame,0,{'Voltage':3},0)
        self.assertEqual((owner._held_cost,owner._update_cost,self.budget.ram_bytes),(0,0,0))
        failure=KeyboardInterrupt('consumer cancelled')
        def cancel(update):
            """模拟取消。参数: update。返回: 不返回。异常: 原KeyboardInterrupt。
            """
            raise failure
        with patch.object(self.budget,'release_ram',side_effect=OSError('temporarily unavailable')):
            with self.assertRaises(KeyboardInterrupt) as caught:
                deliver_message(owner,projection,cancel,frame,0,{'Voltage':3},0)
        self.assertIs(caught.exception,failure)
        self.assertGreater(owner._update_cost,0)
        self.assertEqual(owner._update_cost,self.budget.ram_bytes)
        _release_owned_ram(owner,owner._update_cost,'_update_cost')
        self.assertEqual((owner._held_cost,self.budget.ram_bytes),(0,0))


if __name__ == '__main__':
    unittest.main()
