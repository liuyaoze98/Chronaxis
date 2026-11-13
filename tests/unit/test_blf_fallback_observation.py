"""纯BLF非原生消息完整检查回退的单文件及跨文件计数，不把主动全检记成回退。"""
from pathlib import Path
from unittest.mock import patch
import unittest
from workspace_fixtures import TemporaryDirectory
from configuration_fixtures import current_fixture
from test_optional_contribution_execution import make_can_fixture
from chronaxis import AnalysisPlan,AnalysisRunner
from chronaxis.execution.text_can_reader import TextCANObservationRead
from chronaxis.sources.blf import BLFRead


class BLFFallbackObservationTests(unittest.TestCase):
    """每文件6条原帧/5条目标，强制非原生时按实际检查成功数量累计。"""

    def test_one_and_two_files_auto_and_full(self):
        """核对跨文件累积，不将显式全检计入自动回退。

        参数: 无。返回: None。异常: 真实读取失败或计数/退款不符时测试失败。
        """
        import can
        workspace=Path(__file__).resolve().parents[2]/'work'
        for count in (1,2):
            for policy in ('auto','full'):
                with self.subTest(files=count,input_check=policy),TemporaryDirectory(dir=workspace,prefix='blf-count-') as area:
                    root=Path(area);config,_=make_can_fixture(root/'inputs',mixed=True)
                    source=config['sources'][0];first=Path(source.pop('path'));paths=[str(first)]
                    if count==2:
                        second=root/'part2.blf'
                        with can.BLFReader(first) as reader,can.BLFWriter(second) as writer:
                            for frame in reader:
                                frame.timestamp+=5;writer.on_message_received(frame)
                        paths.append(str(second))
                    source.update(paths=paths,input_check=policy)
                    plan=AnalysisPlan.from_dict(current_fixture(config),base_dir=root)
                    observations=[];original_init=BLFRead.__init__;original_close=TextCANObservationRead.close
                    def fallback(read,*args,**kwargs):
                        """强制真实消息走非原生回退。参数: read及原参数。返回: None。异常: 原构造错误。"""
                        original_init(read,*args,**kwargs);read._native_message_type=object
                    def close(read):
                        """关闭前摘取已完成观测。参数: read。返回: 原关闭结果。异常: 原关闭错误。"""
                        if read.exhausted and not read.closed and read._observation is not None:
                            observations.append(read.observation)
                        return original_close(read)
                    with patch.object(BLFRead,'__init__',fallback),patch.object(TextCANObservationRead,'close',close):
                        with AnalysisRunner().run(plan,root/'run') as result:budget=result.spool.budget
                    self.assertEqual(len(observations),1)
                    fact=observations[0]
                    self.assertEqual((fact.row_count,fact.retained_record_count,fact.full_check_count),
                        (6*count,5*count,6*count if policy=='auto' else 0))
                    self.assertEqual(budget.ram_bytes,0)


if __name__=='__main__':unittest.main()
