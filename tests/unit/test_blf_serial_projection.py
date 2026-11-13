"""纯BLF串行沿用旧ID级交付与时间检查，绑定仍按通道决定实际贡献。"""
from pathlib import Path
from unittest.mock import patch
import unittest
from workspace_fixtures import TemporaryDirectory
from configuration_fixtures import current_fixture
from test_optional_contribution_execution import make_can_fixture
from chronaxis import AnalysisPlan, AnalysisRunner
from chronaxis.execution.text_can_reader import TextCANObservationRead
from chronaxis.sources.text_can_decode import CANTextDecodeRead
import test_blf_reader_convergence as convergence


class BLFSerialProjectionTests(unittest.TestCase):
    """使用真实两通道BLF；解码完成后的选择不省略完整诊断。"""

    def test_same_id_other_channel_retained_but_not_contributed(self):
        """保留另一通道同ID的交付记录，但不把其900W计入绑定通道。

        参数: 无。返回: None。异常: 记录顺序、手算700/-200J或清理不符时失败。
        """
        import can
        for scope,check in (("requested","auto"),("requested","full"),("all","full")):
            with self.subTest(scope=scope,check=check), TemporaryDirectory(prefix="blf-channel-") as area:
                root=Path(area);config,_=make_can_fixture(root/"inputs")
                source=config["sources"][0];path=Path(source["path"])
                with can.BLFReader(path) as reader: frames=list(reader)
                frames.insert(4,can.Message(timestamp=1700000002.5,arbitration_id=256,
                    is_extended_id=False,channel=1,data=(9000).to_bytes(2,"little",signed=True)))
                with can.BLFWriter(path) as writer:
                    for frame in frames:writer.on_message_received(frame)
                source.update(decode_scope=scope,input_check=check)
                plan=AnalysisPlan.from_dict(current_fixture(config),base_dir=root)
                observations=[];delivered=[];original_close=TextCANObservationRead.close
                original_next=CANTextDecodeRead.__next__
                def close(read):
                    """观察实际完成计数。参数: read。返回: 原关闭结果。异常: 原关闭错误。"""
                    if read.exhausted and not read.closed and read._observation is not None:observations.append(read.observation)
                    return original_close(read)
                def advance(read):
                    """摘取实际交付通道/ID。参数: read。返回: 原记录。异常: EOF或原读取错误。"""
                    record=original_next(read);delivered.append((record.raw.frame.channel,record.raw.frame.arbitration_id));return record
                with patch.object(TextCANObservationRead,"close",close),patch.object(CANTextDecodeRead,"__next__",advance):
                    with AnalysisRunner().run(plan,root/"run") as result:
                        self.assertEqual([row.value for row in result.iter_calculations()],[700.,-200.]);budget=result.spool.budget
                self.assertEqual((observations[0].row_count,observations[0].retained_record_count),(7,6))
                self.assertEqual(delivered,[(0,256)]*4+[(1,256),(0,256)])
                self.assertEqual(budget.ram_bytes,0)

    def test_other_channel_same_id_time_regression_is_rejected(self):
        """同ID另一通道沿旧串行政策检查回退。

        参数: 无。返回: None。异常: 未拒绝时间回退或诊断无时间依据时断言失败。
        """
        import can
        for check in ("auto","full"):
            with self.subTest(input_check=check),TemporaryDirectory(prefix="blf-time-channel-") as area:
                root=Path(area);config,_=make_can_fixture(root/"inputs")
                source=config["sources"][0];path=Path(source["path"])
                with can.BLFReader(path) as reader:frames=list(reader)
                frames.insert(4,can.Message(timestamp=1700000001.5,arbitration_id=256,
                    is_extended_id=False,channel=1,data=(9000).to_bytes(2,"little",signed=True)))
                with can.BLFWriter(path) as writer:
                    for frame in frames:writer.on_message_received(frame)
                source.update(decode_scope="requested",input_check=check)
                plan=AnalysisPlan.from_dict(current_fixture(config),base_dir=root)
                with self.assertRaises(Exception) as caught:AnalysisRunner().run(plan,root/"run")
                chain=[];error=caught.exception
                while error is not None:chain.append(str(error));error=error.__cause__
                self.assertTrue(any("时间" in text and ("回退" in text or "递减" in text) for text in chain),chain)


class BLFPostDecodeChecks(unittest.TestCase):
    """复用真实DBC夹具，核对all解码检查与交付筛选的先后。"""
    setUp=convergence.BLFConvergenceTests.setUp
    fixture=convergence.BLFConvergenceTests.fixture
    reader=convergence.BLFConvergenceTests.reader

    def test_all_validates_before_discard(self):
        """all解码值检查先于输出选择，不让无消费者帧隐藏非法值。

        参数: 无。返回: None。异常: 未拒非法值、解码次数或退款不符时失败。
        """
        plan=self.fixture(("blf",),"legacy");read,budget=self.reader(plan,"all")
        read._post_decode_frame_ids=frozenset()
        try:
            with patch.object(read._db,"decode_message",return_value={"Other":"invalid"}):
                with self.assertRaises((TypeError,ValueError)):next(read)
            self.assertEqual(read.decode_calls,1)
        finally:read.close()
        self.assertEqual(budget.ram_bytes,0)


if __name__=="__main__":unittest.main()
