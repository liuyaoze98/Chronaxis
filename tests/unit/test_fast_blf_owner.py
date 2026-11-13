"""fast复用BLF文件owner的临界预算与失败责任，所有夹具为合成输入。"""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from chronaxis.fast.config import compile_config
from chronaxis.fast.session import run_session, effective_spec, _checked_file_specs
from chronaxis.fast.blocks import RAM
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.errors import BudgetExceededError
from chronaxis.sources.blf import BLFRead
import test_fast_session as fixtures


class FastBLFOwnerTests(unittest.TestCase):
    """检查实际文件、预算和返回值，不把模拟成功当作文件关闭。"""

    setUp=fixtures.FastSessionTests.setUp
    asc=fixtures.FastSessionTests.asc
    config=fixtures.FastSessionTests.config

    def blf_spec(self, merge='concatenate'):
        """把两份实际合成BLF交给现有编译器，每条400J，总计1600J。"""
        import can
        paths=[]
        for index in range(2):
            path=self.folder/f'owner-{index}.blf'
            with can.BLFWriter(path) as writer:
                for offset in (0,1):
                    writer.on_message_received(can.Message(timestamp=1704067200+index+offset,
                        channel=0,arbitration_id=256,is_extended_id=False,data=b'\xa0\x0f'))
            paths.append(str(path))
        self.raw['sources'][0]['paths']=paths
        return compile_config(self.config(merge,1))

    def threshold(self,spec):
        """按旧会话固定费手算门槛，新的64KiB读取费必须从中移交而不叠加。"""
        for attempt in range(4):
            prepared=effective_spec(copy.deepcopy(spec));files=_checked_file_specs(prepared,False)
            cost=RAM*(2+(len(files) if prepared.get('file_merge')=='time_order' else 1))
            cost+=len(json.dumps({k:v for k,v in prepared.items() if k!='_database'}).encode())*32
            if spec.get('memory_budget_bytes')==cost:return cost
            spec['memory_budget_bytes']=cost
        self.fail('固定费用字节数未收敛')

    def test_inline_blf_old_budget_boundary_and_one_live_reader(self):
        """接续/内联归并均最多一个实际reader；旧临界值成功，少1字节失败并清零。"""
        for merge in ('concatenate','time_order'):
            spec=self.blf_spec(merge);cost=self.threshold(spec);ledger=ResourceBudget(cost)
            opened=[];live=set();maximum=[0]
            class ObservedRead(BLFRead):
                def __init__(reader,*args,**kwargs):
                    super().__init__(*args,**kwargs)
                    opened.append(reader);live.add(id(reader));maximum[0]=max(maximum[0],len(live))
                def close(reader):
                    super().close()
                    if reader.closed:live.discard(id(reader))
            stats={}
            with self.subTest(merge=merge),patch('chronaxis.fast.session.ResourceBudget',return_value=ledger),patch('chronaxis.sources.blf.BLFRead',ObservedRead):
                rows,_=run_session(spec,work_dir=self.folder,statistics=stats)
                self.assertEqual(rows[0]['value'],1600.)
                self.assertEqual(len(opened),2);self.assertEqual(maximum[0],1)
                self.assertTrue(all(reader.closed for reader in opened));self.assertFalse(live)
                self.assertEqual(ledger.peak_ram_bytes,cost);self.assertEqual(ledger.ram_bytes,0)
            low=dict(spec,memory_budget_bytes=cost-1);ledger=ResourceBudget(cost-1)
            with patch('chronaxis.fast.session.ResourceBudget',return_value=ledger):
                with self.assertRaises(BudgetExceededError):run_session(low,work_dir=self.folder)
            self.assertEqual(ledger.ram_bytes,0)

    def test_blf_header_failure_closes_actual_file_and_restores_budget(self):
        """第三方读取器尚未返回便失败时，同一实际文件和全部费用都归还。"""
        spec=self.blf_spec();ledger=ResourceBudget();files=[];sentinel=ValueError('BLF header sentinel')
        def fail(file):
            files.append(file);raise sentinel
        with patch('chronaxis.fast.session.ResourceBudget',return_value=ledger),patch('can.BLFReader',side_effect=fail):
            with self.assertRaises(ValueError) as caught:run_session(spec)
        self.assertIs(caught.exception,sentinel);self.assertEqual(len(files),1)
        self.assertTrue(files[0].closed);self.assertEqual(ledger.ram_bytes,0)

    def test_failed_blf_close_preserves_session_recovery_owner(self):
        """文件头与持续关闭故障同时发生时，原错携带实际会话owner，恢复后清零。"""
        spec=self.blf_spec();ledger=ResourceBudget();files=[];blocked=[True]
        original=Path.open;sentinel=ValueError('BLF header sentinel')
        class BlockedClose:
            def __init__(self,file):self.file=file
            def __getattr__(self,name):return getattr(self.file,name)
            def close(self):
                if blocked[0]:raise OSError('BLF close sentinel')
                self.file.close()
        def open_file(path,*args,**kwargs):
            actual=original(path,*args,**kwargs)
            if path.suffix.lower()=='.blf':
                wrapped=BlockedClose(actual);files.append(wrapped);return wrapped
            return actual
        with patch('chronaxis.fast.session.ResourceBudget',return_value=ledger),patch.object(Path,'open',open_file),patch('can.BLFReader',side_effect=sentinel):
            with self.assertRaises(ValueError) as caught:run_session(spec)
        self.assertIs(caught.exception,sentinel);self.assertFalse(files[0].closed)
        owner=caught.exception.fast_session_cleanup_owner
        self.assertGreater(ledger.ram_bytes,0)
        blocked[0]=False;owner.close();owner.close()
        self.assertTrue(owner._closed);self.assertTrue(files[0].closed);self.assertEqual(ledger.ram_bytes,0)


if __name__=='__main__':unittest.main()
