"""在全新工作进程里检查单文件结果和解码所需依赖。"""
import csv
import json
import multiprocessing
from pathlib import Path
import sys
from workspace_fixtures import TemporaryDirectory
import unittest


def observed_worker(connection, monitor, cancel, target):
    """真实worker使用固定控制协议，另经测试管道报告依赖，不新增产品消息类型。"""
    from chronaxis._control_wire import ControlChannel
    original_send=ControlChannel.send

    def send_observed(channel, payload):
        """只观察本次端点的成功结果；监测数据独立编码，业务消息仍交原方法。"""
        if channel is connection and payload[0]=='fast_result':
            loaded=sorted(set(sys.modules) & {
                'numpy','jsonschema','chronaxis.planning','chronaxis.batch','cantools'})
            monitor.send_bytes(json.dumps(loaded).encode('utf-8'))
        return original_send(channel,payload)

    ControlChannel.send=send_observed
    try:
        target(connection,cancel)
    finally:
        ControlChannel.send=original_send
        monitor.close()


class FastWorkerImportTests(unittest.TestCase):
    """保留真实BLF数值与冷进程依赖集合，通信适配不能替代计算断言。"""

    def test_cold_worker_loads_only_execution_dependencies(self):
        """运行真实 BLF 的 800 J 计划，不能在文件进程中重复加载通用规划和校验库。"""
        import can
        from chronaxis.batch.process_transport import worker_main
        from chronaxis.fast.config import compile_config
        root = Path(__file__).resolve().parents[2]
        spec = compile_config(root/'Docs/Current/examples/message-minimal.yaml')
        spec['table_format']='csv'
        ctx = multiprocessing.get_context('spawn')
        from chronaxis._control_wire import ControlChannel
        parent_raw, child_raw = ctx.Pipe()
        parent=ControlChannel(parent_raw,'batch',parent=True)
        child=ControlChannel(child_raw,'batch',parent=False)
        monitor_parent,monitor_child=ctx.Pipe(duplex=False)
        self.addCleanup(child.close)
        self.addCleanup(monitor_child.close)
        cancel = ctx.Event()
        process = ctx.Process(target=observed_worker,args=(child,monitor_child,cancel,worker_main))
        with TemporaryDirectory(dir=root/'work',prefix='hpc-import-') as folder, parent, monitor_parent:
            source = Path(folder)/'power.blf'
            with can.BLFWriter(str(source)) as writer:
                for _ in range(2):
                    writer.on_message_received(can.Message(timestamp=1.,channel=0,is_extended_id=False,
                                                            arbitration_id=0x100,data=b'\xa0\x0f'))
            spec.update(path=str(source),inputs=[dict(path=str(source),offset_ns=0)],domain_ns=None)
            process.start()
            child.close()
            monitor_child.close()
            try:
                parent.send(('fast',dict(job_id='one',path=None,spec=spec,total=False),
                             str(Path(folder)/'one'),None))
                self.assertTrue(monitor_parent.poll(30))
                self.assertEqual(json.loads(monitor_parent.recv_bytes(4096)),['cantools'])
                self.assertTrue(parent.poll(30))
                kind,fields,pending=parent.recv()
                self.assertEqual((kind,fields['status'],pending),('fast_result','completed',False))
                manifest = Path(fields['manifest_path'])
                record = json.loads(manifest.read_bytes())
                with (manifest.parent/record['outputs'][0]['name']).open(encoding='utf8') as f:
                    row,=csv.DictReader(f)
                self.assertEqual((row['name'],float(row['value']),row['unit']),('energy',800.,'J'))
                parent.send(('close',))
                process.join(10)
                self.assertEqual(process.exitcode,0)
            finally:
                if process.is_alive():
                    process.kill()
                process.join()
                process.close()
