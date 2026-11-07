"""验证多信号记录按预付对象空间提前分块，且不多读、丢失或提前报告EOF。"""
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from chronaxis.execution.parallel_can_worker import (
    BLOCK_OBJECT_TARGET, BLOCK_RAM, RECORD_RAM_LIMIT, WIRE_LIMIT, read_block,
)


class ParallelCANBlockTests(unittest.TestCase):
    """记录大小由独立费用值控制，断言分块边界与原始对象顺序。"""

    def record(self, cost):
        """构造带目标估算费用的记录。参数: 字节整数。返回: 测试记录。异常: 无。"""
        return SimpleNamespace(values=cost,frame_values=(),frame_layout=(),
                               raw=SimpleNamespace(path='fixture.asc',frame=SimpleNamespace(data=b'')))

    def estimate(self, value):
        """从测试记录读取费用，保持产品估算公式。参数: 元数据tuple。返回: 基础费用。"""
        return (value[0]-16384)//32

    def test_wide_records_split_without_overreading_or_losing_order(self):
        """70条记录旧式64条块会超4MiB；新块仍完整交付且每次只读返回的记录。"""
        records=[self.record(71424) for _ in range(70)]
        read=[]
        def source():
            """依次交付记录并记实际读取数。参数: 无。返回: 记录生成器。异常: 无。"""
            for record in records:
                read.append(record)
                yield record
        reader=source();output=[];sizes=[]
        with patch('chronaxis.execution.history._metadata_bytes',side_effect=self.estimate):
            while True:
                block,eof=read_block(reader)
                output.extend(block);sizes.append(len(block))
                self.assertEqual(len(read),len(output))
                if eof:break
        self.assertEqual(sizes,[30,30,10])
        self.assertTrue(all(actual is expected for actual,expected in zip(output,records)))
        self.assertEqual(len(output),len(records))

    def test_last_record_and_serialization_stay_within_original_reservation(self):
        """不足2MiB的已有记录加最多4MiB末条，仍留出四份512KiB传输空间。"""
        first=self.record(BLOCK_OBJECT_TARGET-32)
        second=self.record(RECORD_RAM_LIMIT)
        reader=iter([first,second])
        with patch('chronaxis.execution.history._metadata_bytes',side_effect=self.estimate):
            block,eof=read_block(reader)
            self.assertEqual(block,[first,second]);self.assertFalse(eof)
            self.assertEqual(read_block(reader),([],True))
        self.assertLess(sum(r.values for r in block)+4*WIRE_LIMIT,BLOCK_RAM)

    def test_oversize_single_record_still_fails(self):
        """单条超过原4MiB上限不能通过缩小批次绕过。"""
        with patch('chronaxis.execution.history._metadata_bytes',side_effect=self.estimate):
            with self.assertRaisesRegex(ValueError,'CAN单条记录对象超过已预约空间'):
                read_block(iter([self.record(RECORD_RAM_LIMIT+32)]))

    def test_row_limit_does_not_claim_eof_until_source_is_exhausted(self):
        """小记录保持64条上限，最后一块必须实际探测结束。"""
        records=[self.record(16384) for _ in range(65)]
        reader=iter(records)
        with patch('chronaxis.execution.history._metadata_bytes',side_effect=self.estimate):
            first,eof=read_block(reader)
            self.assertEqual(len(first),64);self.assertFalse(eof)
            self.assertEqual(read_block(reader),([records[-1]],True))


if __name__=='__main__':
    unittest.main()
