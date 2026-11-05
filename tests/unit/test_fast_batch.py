"""从批量公开入口核实文件顺序、失败隔离、取消与固定模板总计。"""

import json
from copy import deepcopy
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from unittest.mock import Mock, patch

from chronaxis.configuration import load_configuration
from chronaxis.fast.batch import prepare_batch, run_batch
from chronaxis.planning.checks import PlanValidationError


def _worker_waiting_for_cancellation(pipe, cancel):
    """用私有进程等待共享取消通知，让测试能在实际任务已经开始后发出取消。"""
    import os
    from chronaxis.batch.models import BatchJobResult
    with pipe:
        _,packet,directory,_ = pipe.recv()
        Path(directory).parent.joinpath('test-reader-entered').touch()
        if not cancel.wait(15):
            raise RuntimeError('主进程未传递在途取消')
        row=BatchJobResult(packet['job_id'],'cancelled',worker_pid=os.getpid(),error_type='InterruptedError')
        pipe.send(('result',row,False))
        pipe.recv()


class FastBatchTests(unittest.TestCase):
    """两份真实 ASC 分别为800J和400J，通过实际 spawn 进程及公开报告判断。"""

    def setUp(self):
        root = Path(__file__).resolve().parents[2]
        folder = TemporaryDirectory(prefix='fast-batch-', dir=root/'work')
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        data = self.folder/'data'
        data.mkdir()
        examples = root/'Docs/Current/examples'
        original = (examples/'data/message-clean.asc').read_text()
        (data/'file2.asc').write_text(original,encoding='utf8')
        (data/'file10.asc').write_text(original.replace('0.000000 1 100 Rx d 2 A0 0F','',1),encoding='utf8')
        shutil.copyfile(examples/'data/power.dbc',data/'power.dbc')
        self.raw = load_configuration(examples/'message-minimal.yaml').data
        self.raw['outputs']={'tables':'jsonl'}
        self.raw['sources'][0]['paths']='data/file2.asc'
        self.path = self.save('analysis.json',self.raw)

    def save(self,name,data):
        """在本例目录写指定配置。"""
        path = self.folder/name
        path.write_text(json.dumps(data),encoding='utf8')
        return path

    def test_template_order_two_processes_total_and_repeated_output(self):
        """自然序为2、10，求和采用同一指标，其它次运行的报告保持完整。"""
        batch=self.save('batch.json',dict(batch_version=1,template=self.path.name,
                                          inputs=['data/file2.asc','data/file10.asc'],process_count=2))
        root=self.folder/'published'
        first=run_batch(batch,root,total=True)
        old=first.read_bytes()
        report=json.loads(old)
        self.assertEqual(report['status'],'completed')
        self.assertEqual([row['job_id'] for row in report['jobs']],['job_1','job_2'])
        self.assertEqual(report['worker_process_count'],2)
        self.assertEqual(report['totals'][0]['value'],1200.)
        second=run_batch(batch,root,process_count=1)
        self.assertNotEqual(first,second)
        self.assertEqual(first.read_bytes(),old)
        self.assertNotIn('totals',json.loads(second.read_bytes()))

    def test_bad_target_file_does_not_discard_completed_sibling(self):
        """一个合法短帧在解码时失败，另一文件继续，报告按原顺序呈现。"""
        source=self.folder/'data/file2.asc'
        (self.folder/'data/bad.asc').write_text(source.read_text().replace('d 2 A0 0F','d 1 A0'),encoding='utf8')
        self.raw['sources'][0]['paths']='data/bad.asc'
        bad=self.save('bad.json',self.raw)
        batch=self.save('batch.json',dict(batch_version=1,jobs=[{'plan':bad.name},{'plan':self.path.name}]))
        report=json.loads(run_batch(batch,self.folder/'results').read_bytes())
        self.assertEqual(report['status'],'failed')
        self.assertEqual([job['status'] for job in report['jobs']],['failed','completed'])
        self.assertIsNone(report['jobs'][0]['manifest_path'])
        self.assertTrue(Path(report['jobs'][1]['manifest_path']).exists())

    def test_preflight_collects_both_errors_before_dispatch(self):
        """两个文件的独立错误一次返回。无论是否请求总量，都不会创建工作目录。"""
        self.raw['execution']={'backend':'numpy'}
        one=self.save('one.json',self.raw)
        two=self.save('two.json',self.raw)
        batch=self.save('batch.json',dict(batch_version=1,jobs=[{'plan':one.name},{'plan':two.name}]))
        output=self.folder/'results'
        with self.assertRaises(PlanValidationError) as caught:
            run_batch(batch,output)
        self.assertIn('one.json',str(caught.exception))
        self.assertIn('two.json',str(caught.exception))
        self.assertFalse(output.exists())
        batch=self.save('batch.json',dict(batch_version=1,jobs=[{'plan':self.path.name}],backend='numpy'))
        with self.assertRaisesRegex(PlanValidationError,'backend'):
            run_batch(batch,output)

    def test_pre_cancelled_batch_records_unstarted_file(self):
        """取消后报告说明未派发的文件，无分析工作进程。"""
        cancel=Event()
        cancel.set()
        batch=self.save('batch.json',dict(batch_version=1,jobs=[{'plan':self.path.name}]))
        report=json.loads(run_batch(batch,self.folder/'results',cancel_event=cancel).read_bytes())
        self.assertEqual(report['status'],'cancelled')
        self.assertEqual(report['jobs'][0]['error_type'],'not_started')
        self.assertEqual(report['worker_process_count'],0)

    def test_preflight_loads_shared_dbc_once(self):
        """两个模板输入的类型、单位与 fast 表达式绑定复用同一份 DBC。"""
        import cantools
        batch=self.save('batch.json',dict(batch_version=1,template=self.path.name,
                                           inputs=['data/file2.asc','data/file10.asc']))
        with patch('cantools.database.load_file',wraps=cantools.database.load_file) as load:
            _,specs,_=prepare_batch(batch)
            self.assertEqual(len(specs),2)
            self.assertEqual(load.call_count,1)

    def test_conflicting_definitions_fail_before_creating_batch(self):
        """两个指标各自能绑定，但同一原帧不能同时用两套 DBC 定义解码。"""
        dbc=self.folder/'data/power.dbc'
        with dbc.open('a',encoding='utf8') as stream:
            stream.write('\nBO_ 256 Other: 2 Node\n SG_ Other : 0|16@1+ (1,0) [0|65535] "W" Node\n')
        signal=deepcopy(self.raw['signals'][0])
        signal.update(name='other',field={'frame_id':256,'signal':'Other'})
        self.raw['signals'].append(signal)
        calculation=deepcopy(self.raw['message_calculations'][0])
        calculation.update(name='other_energy',expr='other * period')
        self.raw['message_calculations'].append(calculation)
        self.save(self.path.name,self.raw)
        batch=self.save('batch.json',dict(batch_version=1,jobs=[{'plan':self.path.name}]))
        root=self.folder/'published'
        with self.assertRaisesRegex(PlanValidationError,'多个 DBC 定义'):
            run_batch(batch,root)
        self.assertFalse(root.exists())

    def test_stuck_worker_gets_cooperative_notice_before_owned_cleanup(self):
        """模拟不返回的底层读取，先通知取消，到时限后复用已有受控回收路径。"""
        from chronaxis.batch.process_transport import ProcessWorker
        worker=ProcessWorker.__new__(ProcessWorker)
        worker.fast_cancel=Event()
        worker.cancel_deadline=None
        worker.close=Mock()
        with patch('chronaxis.batch.process_transport.monotonic',side_effect=[1.,5.,6.]):
            self.assertFalse(worker.cancel_fast())
            self.assertTrue(worker.fast_cancel.is_set())
            self.assertFalse(worker.cancel_fast())
            worker.close.assert_not_called()
            self.assertTrue(worker.cancel_fast())
        self.assertTrue(worker._pipe_lost)
        worker.close.assert_called_once_with()

    def test_cancel_running_file_does_not_dispatch_next(self):
        """第一个任务确认进入进程后取消，第二个任务没有 PID 且注明未启动。"""
        from time import sleep
        cancel=Event()
        root=self.folder/'published'
        batch=self.save('batch.json',dict(batch_version=1,jobs=[{'plan':self.path.name}]*2))

        def pause():
            if (root/'test-reader-entered').is_file():
                cancel.set()
            sleep(.01)

        with patch('chronaxis.batch.runner._pause',pause),patch(
                'chronaxis.batch.process_transport.worker_main',_worker_waiting_for_cancellation):
            report=json.loads(run_batch(batch,root,cancel_event=cancel).read_bytes())
        first,second=report['jobs']
        self.assertEqual(report['status'],'cancelled')
        self.assertIsNotNone(first['worker_pid'])
        self.assertEqual(first['error_type'],'InterruptedError')
        self.assertIsNone(second['worker_pid'])
        self.assertEqual(second['error_type'],'not_started')

    def test_failed_member_invalidates_total_and_preserves_good_file(self):
        """同一模板第二文件损坏时不发完整总数，第一份文件的结果仍为 800 J。"""
        (self.folder/'data/file10.asc').write_text(
            (self.folder/'data/file2.asc').read_text().replace('d 2 A0 0F','d 1 A0'), encoding='utf8')
        batch=self.save('batch.json',dict(batch_version=1,template=self.path.name,
                                          inputs=['data/file2.asc','data/file10.asc']))
        report=json.loads(run_batch(batch,self.folder/'results',total=True).read_bytes())
        self.assertEqual(report['status'],'failed')
        self.assertIsNone(report['totals'][0]['value'])
        manifest=Path(report['jobs'][0]['manifest_path'])
        table=manifest.parent/json.loads(manifest.read_bytes())['outputs'][0]['name']
        self.assertEqual(json.loads(table.read_bytes())['value'],800.)
