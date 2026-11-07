"""在全新的 Windows 工作进程里检查单文件结果和解码所需依赖。"""
import csv
import json
import multiprocessing
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest


def observed_worker(connection, cancel, target):
    """在真实 worker 发布结果时报告已导入模块，不改变输入任务和结果。"""
    class Observer:
        def __getattr__(self, name):
            return getattr(connection, name)

        def send(self, payload):
            if payload[0] == 'fast_result':
                connection.send(('imports', sorted(set(sys.modules) & {
                    'numpy','jsonschema','chronaxis.planning','chronaxis.batch','cantools'})))
            connection.send(payload)

    target(Observer(), cancel)


class FastWorkerImportTests(unittest.TestCase):
    def test_cold_worker_loads_only_execution_dependencies(self):
        """运行真实 BLF 的 800 J 计划，不能在文件进程中重复加载通用规划和校验库。"""
        import can
        from chronaxis.batch.process_transport import worker_main
        from chronaxis.fast.config import compile_config
        root = Path(__file__).resolve().parents[2]
        spec = compile_config(root/'Docs/Current/examples/message-minimal.yaml')
        spec['table_format']='csv'
        ctx = multiprocessing.get_context('spawn')
        parent, child = ctx.Pipe()
        cancel = ctx.Event()
        process = ctx.Process(target=observed_worker,args=(child,cancel,worker_main))
        with TemporaryDirectory(dir=root/'work',prefix='hpc-import-') as folder, parent:
            source = Path(folder)/'power.blf'
            with can.BLFWriter(str(source)) as writer:
                for _ in range(2):
                    writer.on_message_received(can.Message(timestamp=1.,channel=0,is_extended_id=False,
                                                            arbitration_id=0x100,data=b'\xa0\x0f'))
            spec.update(path=str(source),inputs=[dict(path=str(source),offset_ns=0)],domain_ns=None)
            process.start()
            child.close()
            try:
                parent.send(('fast',dict(job_id='one',path=None,spec=spec,total=False),
                             str(Path(folder)/'one'),None))
                self.assertTrue(parent.poll(30))
                self.assertEqual(parent.recv(),('imports',['cantools']))
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
