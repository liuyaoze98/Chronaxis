"""E4 固定 CAN 块协议的独立数值、字段与损坏边界。"""
from dataclasses import replace
from decimal import Decimal
import math
from pathlib import Path
import struct
import unittest

from chronaxis.execution.can_block_codec import encode_block, decode_block, CANBlockError, LIMIT
from chronaxis.legacy.records import LegacyRawFrame, LegacyCANField
from chronaxis.sources.raw_can import RawCANRecord
from chronaxis.sources.blf import _UntimedBLFRecord
from chronaxis.sources.text_can_decode import DecodedCANRecord


def frame(**changes):
    """建立合成原帧。

    参数: changes为明确覆盖的原帧字段。
    返回: LegacyRawFrame。
    异常: 原模型字段非法。
    """
    fields = dict(timestamp=1.25, arbitration_id=0x123, is_extended_id=False,
        is_remote_frame=False, is_error_frame=False, channel=0, dlc=2,
        data=b'\x00\xff', is_fd=False, is_rx=None, bitrate_switch=False,
        error_state_indicator=False)
    fields.update(changes)
    return LegacyRawFrame(**fields)


def facts():
    """建立极值纳秒和亚纳秒事实。

    参数: 无。
    返回: 固定六项facts字典。
    异常: 无。
    """
    return dict(count=8, first_ns=-(2**63), last_ns=2**63-1, decode_calls=7,
        first_order_time=Decimal('-0.00000000001'), last_order_time=Decimal('0E-1000'))


def record(value=2**64-1, **raw_changes):
    """建立带完整定位的合成记录。

    参数: value为原信号值，raw_changes为明确原记录字段覆盖。
    返回: DecodedCANRecord。
    异常: 原模型约束错误。
    """
    raw = RawCANRecord(frame(), 1_250_000_000, Path('C:/资料/数据.asc'), 5, 3,
                       '1.25000000000001', 'vector-asc-v1', 2, True, -(2**63))
    if raw_changes:
        raw = replace(raw, **raw_changes)
    key = LegacyCANField(0, 'Power', 0x123, False, False).key
    return DecodedCANRecord('bus', 0, 3, raw, ((key, value),), 'decoded',
                            (('value', value),), (('mux', 2),))


class CANBlockCodecTests(unittest.TestCase):
    """以合成输入验证固定协议；各用例独立构造，无共享状态或真实日志。"""
    def test_complete_record_and_decimal_roundtrip(self):
        """核完整原帧、极值整数及Decimal精确时间往返。

        参数: 无。
        返回: None。
        异常: 断言失败或被测接口意外错误。
        """
        original = record()
        packet = encode_block(2**64, [original], True, facts())
        number, records, eof, result_facts = decode_block(packet)
        self.assertEqual((number, records, eof), (2**64, [original], True))
        self.assertEqual(result_facts, facts())
        self.assertEqual(result_facts['last_order_time'].as_tuple(), facts()['last_order_time'].as_tuple())

    def test_numeric_value_type_and_bits_preserved(self):
        """核原生类型、int64/uint64和非有限浮点位型。

        参数: 无。
        返回: None。
        异常: 断言失败或被测接口意外错误。
        """
        for value in (None, True, False, -(2**63), 2**63-1, 2**64-1, 2**140,
                      -(2**140), -0.0, float('nan'), float('inf'), -float('inf')):
            with self.subTest(value=value):
                restored = decode_block(encode_block(0, [record(value)], False, facts()))[1][0].values[0][1]
                self.assertIs(type(restored), type(value))
                if type(value) is float:
                    self.assertEqual(struct.pack('!d', restored), struct.pack('!d', value))
                else:
                    self.assertEqual(restored, value)

    def test_remote_unknown_zero_eight_dlc_and_direction(self):
        """核未知、零和八DLC及三种收发状态不混淆。

        参数: 无。
        返回: None。
        异常: 断言失败或被测接口意外错误。
        """
        for code in (None, 0, 8):
            for direction in (None, False, True):
                item = record(dlc_code=code, frame=frame(dlc=8, data=b'', is_remote_frame=True, is_rx=direction))
                restored = decode_block(encode_block(0, [item], True, facts()))[1][0]
                self.assertEqual(restored, item)

    def test_untimed_blf_does_not_validate_unneeded_time(self):
        """核无时间消费者时保留原NaN而不新增时间校验。

        参数: 无。
        返回: None。
        异常: 断言失败或被测接口意外错误。
        """
        import can
        raw = _UntimedBLFRecord(can.Message(timestamp=float('nan'), arbitration_id=12,
            is_extended_id=False, data=b'\x00\xff', channel='CAN1'), Path('C:/数据.blf'), 4)
        item = DecodedCANRecord('bus', 0, 4, raw, (), 'unselected')
        restored = decode_block(encode_block(0, [item], True, facts()))[1][0]
        self.assertIsNone(restored.raw.time_ns)
        self.assertTrue(math.isnan(restored.raw.frame.timestamp))
        self.assertEqual(bytes(restored.raw.frame.data), b'\x00\xff')
        self.assertEqual(restored.raw.path, raw.path)

    def test_string_table_preserves_unicode_and_surrogates(self):
        """核共享字符串表、Unicode及路径代理码位。

        参数: 无。
        返回: None。
        异常: 断言失败或被测接口意外错误。
        """
        original = record(raw_time='0.' + '1' * 2000, path=Path('C:/资料/\udcff.asc'))
        packet = encode_block(0, [original] * 64, False, facts())
        self.assertLess(len(packet), 25000)
        self.assertEqual(decode_block(packet)[1], [original] * 64)

    def test_unknown_version_and_pickle_are_never_loaded(self):
        # 此处仅传入已知pickle指令字节，不调用pickle.loads来执行反例。
        """核未知版本和pickle指令字节只被拒绝。

        参数: 无。
        返回: None。
        异常: 断言失败或被测接口意外错误。
        """
        for payload in (b'cos\nsystem\n(S"echo forbidden"\ntR.', b'CND9'+b'\x00'*40):
            with self.assertRaises(CANBlockError):
                decode_block(payload)

    def test_truncated_and_trailing_packets_rejected(self):
        """遍历全部截断点并拒绝尾随字节。

        参数: 无。
        返回: None。
        异常: 断言失败或被测接口意外错误。
        """
        packet = encode_block(0, [record()], True, facts())
        for end in range(len(packet)):
            with self.subTest(end=end), self.assertRaises((CANBlockError, ValueError)):
                decode_block(packet[:end])
        with self.assertRaises(CANBlockError):
            decode_block(packet+b'x')
        # 长度也同步伪造仍不能容许未消费内容。
        mutated = packet[:4] + struct.pack('!I', len(packet)-7) + packet[8:] + b'x'
        with self.assertRaises(CANBlockError):
            decode_block(mutated)

    def test_invalid_counts_and_huge_declared_strings_rejected(self):
        """核伪造容器数量在分配前被拒绝。

        参数: 无。
        返回: None。
        异常: 断言失败或被测接口意外错误。
        """
        packet = encode_block(0, [], True, facts())
        for count in (0xffffffff, LIMIT):
            mutated = packet[:8] + struct.pack('!I', count) + packet[12:]
            with self.assertRaises(CANBlockError):
                decode_block(mutated)

    def test_row_and_byte_limits(self):
        """核64条及512KiB原边界仍有效。

        参数: 无。
        返回: None。
        异常: 断言失败或被测接口意外错误。
        """
        with self.assertRaises(CANBlockError):
            encode_block(0, [record()] * 65, True, facts())
        with self.assertRaises(CANBlockError):
            encode_block(0, [record(raw_time='0.'+'1'*LIMIT)], True, facts())



class CANBlockExpansionTests(unittest.TestCase):
    """用旧组批的实际费用和边界证明新展开限制没有拒绝原合法块。"""

    def old_cost(self, item):
        """按旧组批原式计算费用。

        参数: item为合成解码记录。
        返回: 原估算字节整数。
        异常: 原元数据类型或深度错误。
        """
        from chronaxis.execution.history import _metadata_bytes
        return 16384+32*_metadata_bytes((item.values,item.frame_values,item.frame_layout,
            str(item.raw.path),getattr(item.raw,'raw_time',None),bytes(item.raw.frame.data)))

    def pass_old_blocks(self, items):
        """用旧分批器交付全部输入并核新协议。

        参数: items为原合法记录列表。
        返回: 实际块数及展开计数峰值。
        异常: 断言、旧预算或新编码错误。
        """
        from chronaxis.execution.parallel_can_worker import read_block,RECORD_RAM_LIMIT,BLOCK_RAM
        from chronaxis.execution.can_block_codec import _Reader
        from unittest.mock import patch
        self.assertTrue(all(self.old_cost(item)<=RECORD_RAM_LIMIT for item in items))
        peak=[0]
        charge=_Reader.charge
        def tracked(reader,amount):
            """观察实际展开计数而不修改限额。

            参数: reader当前块读取器，amount本次新增费用。
            返回: None。
            异常: 原展开限制错误。
            """
            charge(reader,amount)
            peak[0]=max(peak[0],reader.expansion)
        iterator=iter(items)
        recovered=[]
        block_count=0
        with patch.object(_Reader,'charge',tracked):
            while True:
                rows,eof=read_block(iterator)
                packet=encode_block(block_count,rows,eof,facts())
                self.assertLessEqual(len(packet),LIMIT)
                result=decode_block(packet)
                recovered.extend(result[1])
                block_count+=1
                if eof:break
        self.assertEqual(recovered,items)
        self.assertLessEqual(peak[0],BLOCK_RAM-2*1048576)
        return block_count,peak[0]

    def test_sixty_four_records_keep_existing_bounded_batches(self):
        """核64条输入按旧费用提前分批后完整交付。

        参数: 无。
        返回: None。
        异常: 断言失败或被测接口意外错误。
        """
        from chronaxis.execution.parallel_can_worker import read_block
        original=record()
        items=[replace(original,sequence=i,raw=replace(original.raw,sequence=i,raw_time=None),
                       values=(),frame_values=(),frame_layout=(),status='non_data') for i in range(64)]
        rows,eof=read_block(iter(items))
        self.assertGreater(len(rows),0)
        self.assertLessEqual(len(rows),64)
        self.assertFalse(eof)
        self.pass_old_blocks(items)

    def test_nearly_four_mib_single_record_accepted(self):
        """核旧单条费用恰好4MiB的记录仍可交付。

        参数: 无。
        返回: None。
        异常: 断言失败或被测接口意外错误。
        """
        from chronaxis.execution.parallel_can_worker import RECORD_RAM_LIMIT
        original=record(raw_time='1.')
        added=(RECORD_RAM_LIMIT-self.old_cost(original))//32
        boundary=replace(original,raw=replace(original.raw,raw_time='1.'+'0'*added))
        cost=self.old_cost(boundary)
        self.assertLessEqual(RECORD_RAM_LIMIT-cost,31)
        blocks,peak=self.pass_old_blocks([boundary,boundary])
        self.assertGreaterEqual(blocks,2)
        self.assertLess(peak,1048576)

    def test_wide_repeated_names_and_large_integer_preserved(self):
        """核宽字段、重复字段名引用及巨大原整数不误拒。

        参数: 无。
        返回: None。
        异常: 断言失败或被测接口意外错误。
        """
        from chronaxis.execution.parallel_can_worker import RECORD_RAM_LIMIT
        original=record()
        keys=[LegacyCANField(0,'signal_'+str(i)+'x'*4096,0x123,False,False).key for i in range(20)]
        wide=replace(original,values=tuple((name,i) for i,name in enumerate(keys)),frame_values=(),frame_layout=())
        self.assertLess(self.old_cost(wide),RECORD_RAM_LIMIT)
        huge=replace(record(1<<850000),frame_values=(),frame_layout=())
        self.assertLess(self.old_cost(huge),RECORD_RAM_LIMIT)
        self.pass_old_blocks([wide,wide,huge,wide])



class CANDiskProtocolTests(unittest.TestCase):
    """不依赖摘要开启与否，磁盘块仍需满足文件身份、次序和EOF结构。"""

    def cursor(self, packets, *, integrity=False):
        """建立纯内存磁盘回读夹具。

        参数: packets完整字节包序列，integrity控制原SHA选项。
        返回: 仅具备_push所需字段的游标。
        异常: 夹具结构错误。
        """
        from io import BytesIO
        from hashlib import sha256
        from types import SimpleNamespace
        from chronaxis.execution.parallel_can_decode import ParallelCANDecodeRead
        cursor=object.__new__(ParallelCANDecodeRead)
        cursor.spec=SimpleNamespace(name='bus',inputs=(SimpleNamespace(path=Path('C:/资料/数据.asc')),))
        body=b''.join(packet[:8]+(sha256(packet).digest() if integrity else b'')+packet[8:] for packet in packets)
        cursor._handles=[BytesIO(body)]
        cursor._stream_records=[((),0)]
        cursor._disk_blocks=[0]
        cursor._disk_eof=[False]
        cursor._integrity=integrity
        cursor._heap=[]
        return cursor

    def test_valid_file_and_eof(self):
        """核有摘要和无摘要的合法磁盘文件及EOF。

        参数: 无。
        返回: None。
        异常: 断言失败或被测接口意外错误。
        """
        from chronaxis.execution.parallel_can_decode import ParallelCANDecodeRead
        item=record()
        for integrity in (False,True):
            cursor=self.cursor([encode_block(0,[item],False,facts()),encode_block(1,[],True,facts())],integrity=integrity)
            cursor._push(0)
            self.assertEqual(cursor._heap.pop()[-1],item)
            cursor._push(0)
            self.assertFalse(cursor._heap)

    def test_reordered_missing_eof_and_data_after_eof(self):
        """拒绝乱序块、缺EOF及EOF后数据。

        参数: 无。
        返回: None。
        异常: 断言失败或被测接口意外错误。
        """
        from chronaxis.sources.protocol import SourceReadError
        cases=[
            [encode_block(1,[],True,facts())],
            [encode_block(0,[],False,facts())],
            [encode_block(0,[],True,facts()),encode_block(1,[],True,facts())],
        ]
        for packets in cases:
            with self.subTest(count=len(packets)),self.assertRaises(SourceReadError):
                self.cursor(packets)._push(0)

    def test_wrong_file_or_source_not_opened(self):
        """拒绝与当前槽不符的原文件或来源身份。

        参数: 无。
        返回: None。
        异常: 断言失败或被测接口意外错误。
        """
        from chronaxis.sources.protocol import SourceReadError
        for item in (replace(record(),source='another'),replace(record(),raw=replace(record().raw,path=Path('C:/other.asc')))):
            with self.assertRaises(SourceReadError):
                self.cursor([encode_block(0,[item],True,facts())])._push(0)

    def test_pickle_bytes_on_disk_rejected_without_evaluation(self):
        """核磁盘入口不解释pickle指令。

        参数: 无。
        返回: None。
        异常: 断言失败或被测接口意外错误。
        """
        from chronaxis.sources.protocol import SourceReadError
        with self.assertRaises(SourceReadError):
            self.cursor([b'cos\nsystem\n(S"echo forbidden"\ntR.'])._push(0)



class CANMetadataCodecTests(unittest.TestCase):
    """宽DBC事实保留原512KiB上限，不用重复JSON键造成新的合法输入拒绝。"""

    def metadata(self, fields):
        """建立当前固定READY事实。参数: fields字段事实列表。返回: dict。异常: 无。"""
        return dict(profile='can-text-v1',dbc_path='C:/资料/vehicle.dbc',dbc_sha256='a'*64,
            fields=fields,decode_choices=False,allow_truncated=True,decode_scope='requested',
            cantools_version='41.2',selected_length_check='partial',
            record_check_scope='source',time_order_check_scope='selected_ids')

    def test_full_metadata_optional_fields(self):
        """核所有可选事实。参数: 无。返回: None。异常: 断言或编码错误。"""
        from chronaxis.execution.can_block_codec import encode_metadata,decode_metadata
        from chronaxis.legacy.records import field_to_dict
        value=self.metadata([dict(locator=field_to_dict(LegacyCANField(0,'Power',1,None,False)),
            unit='W',dbc_frames=[[False,True],[True,True]],cycle_ns=100000000,
            frame_format_compatibility=dict(code='dbc_fd_classic_selector',dbc_is_fd=True,requested_is_fd=False))])
        self.assertEqual(decode_metadata(encode_metadata(value)),value)

    def test_wide_4096_field_metadata_remains_bounded(self):
        """核4096个合法字段及包长。参数: 无。返回: None。异常: 断言或编码错误。"""
        from chronaxis.execution.can_block_codec import encode_metadata,decode_metadata
        from chronaxis.legacy.records import field_to_dict
        import pickle
        value=self.metadata([dict(locator=field_to_dict(LegacyCANField(0,'Signal_'+str(i),i,True,False)),
                                  unit='V') for i in range(4096)])
        # 仅对已构造的有限测试事实做旧编码包长对照，从不调用pickle.loads。
        previous=pickle.dumps(value,protocol=5)
        self.assertLessEqual(len(previous),LIMIT)
        encoded=encode_metadata(value)
        self.assertLessEqual(len(encoded),LIMIT)
        self.assertEqual(decode_metadata(encoded),value)

    def test_metadata_cannot_be_read_as_record_block(self):
        """核两个固定入口不混淆。参数: 无。返回: None。异常: 断言失败。"""
        from chronaxis.execution.can_block_codec import encode_metadata,decode_metadata
        with self.assertRaises(CANBlockError):
            decode_block(encode_metadata(self.metadata([])))
        with self.assertRaises(CANBlockError):
            decode_metadata(encode_block(0,[],True,facts()))



class CANReadyBudgetTests(unittest.TestCase):
    """READY费用覆盖真实同时对象和D2退款重试，不借用远端worker预算。"""

    def metadata(self, fields):
        """建立固定事实。参数: fields为字段列表。返回: dict。异常: 无。"""
        return CANMetadataCodecTests().metadata(fields)

    def owner(self, budget):
        """创建真实接收拥有者并预付原8MiB槽，不启动无关工作进程。

        参数: budget共享账本。返回: ParallelCANDecodeRead。
        异常: 原构造或预算错误。
        """
        from chronaxis.sources.text_can_spec import CANTextSpec
        from chronaxis.sources.asc import ASCSpec
        from chronaxis.core.models import TimebaseSpec
        from chronaxis.core.types import TimeType
        from chronaxis.execution.parallel_can_decode import ParallelCANDecodeRead
        from chronaxis.results.budget import _reserve_owned_ram
        source=CANTextSpec('bus',(ASCSpec(Path('input.asc')),),Path('vehicle.dbc'),0,
            TimebaseSpec('time',TimeType.RELATIVE,'clock'))
        value=ParallelCANDecodeRead(source,budget,(),process_count=1,work_dir=Path('.'))
        _reserve_owned_ram(value,8*1048576,'_workers_cost')
        self.addCleanup(value.close)
        return value

    def test_long_old_legal_metadata_and_all_optional_shapes(self):
        """旧512KiB内的长名和全部固定可选字段不受数据块6MiB阈值限制。"""
        from chronaxis.execution.can_block_codec import encode_metadata,decode_metadata
        from chronaxis.legacy.records import field_to_dict
        import pickle
        for full in (False,True):
            fields=[]
            for i in range(4096):
                item=dict(locator=field_to_dict(LegacyCANField(0,'X'*(20 if full else 90)+str(i),i,True,False)),unit='V')
                if full:
                    item.update(dbc_frames=[[False,False],[False,True],[True,False],[True,True]],
                        cycle_ns=100000000,frame_format_compatibility=dict(code='dbc_fd_classic_selector',dbc_is_fd=True,requested_is_fd=False))
                fields.append(item)
            value=self.metadata(fields)
            with self.subTest(all_fixed_optional_shapes=full):
                self.assertLessEqual(len(pickle.dumps(value,protocol=5)),LIMIT)
                self.assertEqual(decode_metadata(encode_metadata(value)),value)

    def test_long_dbc_unit_survives_worker_exit_and_second_ready(self):
        """不在声明中的长单位单独付持久差额，第二次READY及worker退出不丢账。"""
        from chronaxis.execution.can_block_codec import encode_metadata
        from chronaxis.results.budget import ResourceBudget
        from chronaxis.legacy.records import field_to_dict
        budget=ResourceBudget(64*1048576)
        owner=self.owner(budget)
        value=self.metadata([dict(locator=field_to_dict(LegacyCANField(0,'Power',1)),unit='u'*460000+'🌡',cycle_ns=100000000)])
        packet=encode_metadata(value)
        owner._accept_metadata(packet)
        extra=owner._metadata_extra_cost
        self.assertGreater(extra,0)
        first=owner.metadata
        owner._accept_metadata(packet)
        self.assertIs(owner.metadata,first)
        self.assertEqual(owner._metadata_extra_cost,extra)
        owner._stop_workers()
        self.assertEqual(budget.ram_bytes,owner._fixed_cost+extra)
        self.assertEqual(owner.metadata['fields'][0]['unit'],value['fields'][0]['unit'])
        owner.close()
        self.assertEqual(budget.ram_bytes,0)

    def test_failed_ready_retains_primary_error_and_refund_owner(self):
        """事实冲突与首次退款失败同现时保首错，未退款费用可随owner重试。"""
        from unittest.mock import patch
        from chronaxis.execution.can_block_codec import encode_metadata
        from chronaxis.execution import parallel_can_decode as implementation
        from chronaxis.results.budget import ResourceBudget
        from chronaxis.sources.protocol import SourceReadError
        from chronaxis.legacy.records import field_to_dict
        class FailingRefund(ResourceBudget):
            """在指定首次退款前失败，真实账本保持原金额。"""
            armed=False
            def release_ram(self,amount):
                """仅注入一次退款失败。参数: amount。返回: None。异常: 首次OSError。"""
                if self.armed and amount:
                    self.armed=False
                    raise OSError('first metadata refund')
                return super().release_ram(amount)
        budget=FailingRefund(64*1048576)
        owner=self.owner(budget)
        owner._accept_metadata(encode_metadata(self.metadata([])))
        fields=[]
        for i in range(4096):
            fields.append(dict(locator=field_to_dict(LegacyCANField(0,'Signal_'+str(i),i,True,False)),
                unit='V',dbc_frames=[[False,False],[False,True],[True,False],[True,True]],
                cycle_ns=100000000,frame_format_compatibility=dict(code='dbc_fd_classic_selector',dbc_is_fd=True,requested_is_fd=False)))
        packet=encode_metadata(self.metadata(fields))
        original=implementation.freeze_metadata
        def freeze_then_arm(value):
            """先真实冻结当前图，随后注入退款失败。参数: value。返回: 冻结图。异常: 原错误。"""
            result=original(value)
            budget.armed=True
            return result
        with patch.object(implementation,'freeze_metadata',side_effect=freeze_then_arm):
            with self.assertRaisesRegex(SourceReadError,'元数据不一致') as caught:
                owner._accept_metadata(packet)
        self.assertTrue(any('退款失败' in note for note in caught.exception.__notes__))
        self.assertGreater(owner._metadata_extra_cost,max(0,owner._metadata_model_cost-owner._metadata_credit))
        self.assertEqual(budget.ram_bytes,owner._held_cost)
        owner.close()
        self.assertEqual(budget.ram_bytes,0)

    def test_ready_reserve_after_effect_cancel_returns_actual_fee(self):
        """READY差额已入账后取消，仍退真实申请并保取消首因。"""
        from chronaxis.execution.can_block_codec import encode_metadata
        from chronaxis.results.budget import ResourceBudget
        from chronaxis.legacy.records import field_to_dict
        class CancelAfterReserve(ResourceBudget):
            """在差额预约真实完成后触发一次取消。"""
            armed=False
            def reserve_ram(self,amount):
                """先入账再取消。参数: amount。返回: None。异常: 首次KeyboardInterrupt。"""
                super().reserve_ram(amount)
                if self.armed:
                    self.armed=False
                    raise KeyboardInterrupt('after metadata reserve')
        budget=CancelAfterReserve(64*1048576)
        owner=self.owner(budget)
        initial=budget.ram_bytes
        value=self.metadata([dict(locator=field_to_dict(LegacyCANField(0,'Power',1)),unit='u'*460000+'🌡')])
        budget.armed=True
        with self.assertRaisesRegex(KeyboardInterrupt,'after metadata reserve'):
            owner._accept_metadata(encode_metadata(value))
        self.assertEqual(budget.ram_bytes,initial)
        self.assertEqual(owner._metadata_extra_cost,0)
        owner.close()
        self.assertEqual(budget.ram_bytes,0)
