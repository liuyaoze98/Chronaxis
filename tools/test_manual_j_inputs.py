"""核对 DOC-REVIEW-10 的输入范围、静态选择和内存教学例。

使用真实生产配置/worker，CAN循环只替换文件和连接为有限内存夹具，不读业务日志。
解码仍使用教学DBC和cantools；结果例只生成本测试临时目录并在关闭后删除。
运行前将src及tests/unit加入PYTHONPATH，不改变产品、旧测试或用户数据。
"""

from collections import deque
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import struct
import re
import unittest
from unittest.mock import patch

from chronaxis import AnalysisPlan, AnalysisRunner, load_analysis_plan
from chronaxis.configuration import load_configuration, parse_configuration
from chronaxis.legacy import batch_worker, decode_policy, worker
from chronaxis.legacy.batch_wire import MAX_BATCH_BYTES, MAX_BATCH_ROWS
from chronaxis.legacy.records import LegacyCANField, LegacyCANRequest, decode_packet, encode_packet
from chronaxis.planning.backend_selection import select_backend
from chronaxis.planning.process_execution import source_execution_facts
from test_legacy_batch_validation import message


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / 'Docs/Current/examples'


class MemoryConnection:
    """交付一批明确许可，worker读到真实EOF后关闭；保留实际输出。"""

    def __init__(self):
        """参数: 无。返回: 内存连接。异常: 分配失败。"""
        self.commands = deque(({'op': 'init', 'version': 1, 'path': 'memory.blf',
            'dbc_path': 'memory.dbc', 'fields': []},
            {'op': 'pull_batch', 'request_id': 0, 'rows': MAX_BATCH_ROWS,
             'bytes': MAX_BATCH_BYTES, 'frame_ids': None}))
        self.sent = []
        self.closed = False

    def recv_bytes(self, limit):
        """参数: limit为许可字节上限。返回: 下一控制包。异常: 脚本耗尽或超限。"""
        payload = encode_packet(self.commands.popleft())
        assert len(payload) <= limit
        return payload

    def send_bytes(self, payload):
        """参数: payload为生产响应。返回: None。异常: 内存不足。"""
        self.sent.append(payload)

    def close(self):
        """参数: 无。返回: None；标记连接关闭。异常: 无。"""
        self.closed = True


class ManualInputContractTests(unittest.TestCase):
    """将正文关键保证对应到真实解码、计划选择及示例结果。"""

    def test_all_scope_attempts_and_length_checks(self):
        """参数: 无。返回: None。异常: 表中解码尝试、长度或失败范围不符时断言失败。"""
        import can
        import cantools
        database = cantools.database.load_file(str(EXAMPLES/'data/can/teaching.dbc'))
        # 已绑定功率、未绑定有定义ID、未知ID、远程帧、错误帧均使用可核实的有限输入。
        frames = [message(timestamp=float(i), arbitration_id=frame_id, data=bytearray(data),
                          dlc=len(data), is_remote_frame=remote, is_error_frame=error)
                  for i,(frame_id,data,remote,error) in enumerate((
                      (256,struct.pack('<d',2.0),False,False),
                      (258,b'\x01\x00',False,False),
                      (999,b'\x00',False,False),
                      (256,b'',True,False),
                      (256,struct.pack('<d',4.0),False,True)))]
        field = LegacyCANField(0,'Power',256,False,False)
        request = LegacyCANRequest(Path('memory.blf'),Path('memory.dbc'),(field,))
        for policy in ('strict','partial','legacy'):
            with self.subTest(policy=policy):
                connection = MemoryConnection()
                # 包装生产函数只观察调用；DBC解析、返回空值与编码仍执行真实逻辑。
                with patch.object(worker,'_request',return_value=request), \
                     patch.object(worker,'_load_can_runtime',return_value=(can,cantools)), \
                     patch.object(batch_worker,'load_dbc_file',return_value=database), \
                     patch.object(worker,'_iter_blf',return_value=(frame for frame in frames)), \
                     patch.object(batch_worker,'_parse_selected',wraps=batch_worker._parse_selected) as decode, \
                     patch.object(decode_policy,'check_decode_length',wraps=decode_policy.check_decode_length) as length:
                    try:
                        batch_worker.batch_worker_main(connection,decode_policy=policy)
                    except SystemExit:
                        self.fail('worker异常：'+str(decode_packet(connection.sent[-1])))
                self.assertTrue(connection.closed)
                self.assertFalse(connection.commands)
                self.assertEqual(decode_packet(connection.sent[0])['op'],'ready')
                expected = [256,258,999] + ([256,256] if policy=='legacy' else [])
                self.assertEqual([call.args[1].arbitration_id for call in decode.call_args_list],expected)
                expected_length_calls=[256,256,256] if policy=='legacy' else [256]
                self.assertEqual([call.args[0].arbitration_id for call in length.call_args_list],expected_length_calls)
                # legacy的检查函数立即返回；即使同ID缓存带入空远程帧，也不会新增DBC长度校验。
                if policy=='legacy':
                    self.assertIsNone(decode_policy.check_decode_length(frames[3],8,policy))
                # Unknown ID不能因all变成已验证值；长度检查不覆盖未绑定的2字节Enabled帧。
                self.assertEqual(batch_worker._parse_selected(database,frames[2],None,set()),{})

    def test_semantic_version_requires_named_meaning(self):
        """参数: 无。返回: None。异常: 普通信号语义版本依赖不符时失败。"""
        document = load_configuration(EXAMPLES/'input-memory-minimal.yaml').data
        document['signals'][0]['semantic_contract_version']='2'
        with self.assertRaisesRegex(ValueError,'semantic_contract_version需要semantic_id'):
            AnalysisPlan.from_dict(document,base_dir=EXAMPLES)
        document['signals'][0]['semantic_id']='example.power'
        self.assertIsNotNone(AnalysisPlan.from_dict(document,base_dir=EXAMPLES))

    def test_read_process_limits(self):
        """参数: 无。返回: None。异常: 单/双卷接续或归并的计划上限不符时失败。"""
        for name,count in (('analysis.yaml',1),('input-can-directory.yaml',2)):
            plan=load_analysis_plan(EXAMPLES/name)
            for requested in (1,4):
                for merge in ('concatenate','time_order'):
                    source=replace(plan.sources[0],config=replace(plan.sources[0].config,file_merge=merge))
                    selected=replace(plan,sources=(source,),execution=replace(plan.execution,process_count=requested))
                    expected=min(count,requested) if merge=='time_order' or min(count,requested)>1 else 0
                    self.assertEqual(source_execution_facts(selected)[0]['read_process_limit'],expected)

    def test_condition_changes_auto_selection(self):
        """参数: 无。返回: None。异常: 条件积分选择不符时失败；不运行日志。"""
        document=load_configuration(EXAMPLES/'calculation-minimal.yaml').data
        plain=AnalysisPlan.from_dict(document,base_dir=EXAMPLES)
        conditional=deepcopy(document)
        conditional['calculations'][0]['condition']='power > 0'
        selected=AnalysisPlan.from_dict(conditional,base_dir=EXAMPLES)
        self.assertEqual(select_backend(plain).selected,'reference')
        self.assertEqual(select_backend(selected).selected,'numpy')

    def test_memory_minimum_is_six_joules(self):
        """参数: 无。返回: None。异常: 2W一秒加4W一秒不是完整6J时失败。"""
        plan=load_analysis_plan(EXAMPLES/'input-memory-minimal.yaml')
        with TemporaryDirectory(prefix='chronaxis-manual-j-memory-') as temporary:
            result=AnalysisRunner().run(plan,work_dir=Path(temporary)/'work')
            try:
                rows=list(result.iter_calculations())
                self.assertEqual(len(rows),1)
                self.assertEqual((rows[0].value,rows[0].unit,rows[0].status),(6.0,'J','complete'))
            finally:
                result.close()

    def test_bilingual_memory_examples_match_download(self):
        """参数: 无。返回: None。异常: 中英文完整示例与下载配置含义不同或语法损坏时失败。"""
        expected=load_configuration(EXAMPLES/'input-memory-minimal.yaml').data
        for relative,heading in (('inputs.md','## 内存：把记录直接写进配置'),
                                 ('en/inputs.md','## Memory: put records directly in configuration')):
            text=(ROOT/'Docs/Current'/relative).read_text(encoding='utf-8').split(heading,1)[1]
            block=re.search(r'```yaml\n(.*?)\n```',text,re.S).group(1)
            self.assertEqual(parse_configuration(block,format='yaml').data,expected)


if __name__ == '__main__':
    unittest.main()
