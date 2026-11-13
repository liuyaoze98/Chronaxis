"""共用BLF读写owner的实际文件与失败边界，不依赖退出进程代替句柄关闭。"""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import unittest
from workspace_fixtures import TemporaryDirectory
from chronaxis.legacy.worker import _iter_blf
from chronaxis.legacy.decode_policy import decode_serial_frame
from chronaxis.results.blf_writer import BLFWrite


class BLFIOOwnershipTests(unittest.TestCase):
    """覆盖首次许可、单次最终写入、构造失败以及持续关闭失败恢复。"""

    def setUp(self):
        """建立独占测试目录。参数: 无。返回: None。异常: 临时目录创建失败。"""
        self.temp=TemporaryDirectory(prefix='blf-owner-',dir=Path(__file__).resolve().parents[2]/'work')
        self.addCleanup(self.temp.cleanup);self.path=Path(self.temp.name)/'new.blf'

    def test_protocol_generator_is_lazy_and_closes_actual_file(self):
        """创建生成器不打开输入；读首帧后关闭会释放同一个实际句柄。"""
        import can
        with can.BLFWriter(self.path) as writer:
            writer.on_message_received(can.Message(timestamp=1700000000.,arbitration_id=256,
                is_extended_id=False,channel=0,data=b'\x01'))
        original=Path.open;opened=[]
        def observed(path,*args,**kwargs):
            """观察本例文件打开，不拦截依赖元数据。参数: 路径及原参数。返回: 真实文件。异常: 原打开错误。"""
            result=original(path,*args,**kwargs)
            if path==self.path:opened.append(result)
            return result
        with patch.object(Path,'open',observed):
            reader=_iter_blf(self.path)
            self.assertEqual(opened,[])
            self.assertEqual(next(reader).data,b'\x01')
            self.assertEqual(len(opened),1);self.assertFalse(opened[0].closed)
            reader.close();reader.close()
        self.assertTrue(opened[0].closed)

    def test_serial_decoder_keeps_distinct_exception_policies(self):
        """唯一ID普通异常为缺值，多定义仅解码错误为缺值，不吞取消或程序错误。"""
        from cantools.database.errors import DecodeError
        frame=SimpleNamespace(arbitration_id=256,data=b'\x01')
        database=SimpleNamespace(decode_message=lambda *a,**k:(_ for _ in ()).throw(RuntimeError('unique')))
        message=SimpleNamespace(decode=lambda *a,**k:(_ for _ in ()).throw(DecodeError('multiplex')))
        self.assertEqual(decode_serial_frame(database,frame,message,set()),{})
        self.assertEqual(decode_serial_frame(database,frame,message,{256}),{})
        message.decode=lambda *a,**k:(_ for _ in ()).throw(RuntimeError('duplicate'))
        with self.assertRaisesRegex(RuntimeError,'duplicate'):decode_serial_frame(database,frame,message,{256})
        database.decode_message=lambda *a,**k:(_ for _ in ()).throw(KeyboardInterrupt())
        with self.assertRaises(KeyboardInterrupt):decode_serial_frame(database,frame,message,set())

    def test_writer_claim_is_exclusive_and_roundtrip_fields_preserved(self):
        """直接库回读验证真实经典、扩展、FD、远程和错误帧；已有文件不覆盖。"""
        import can
        messages=[can.Message(timestamp=1700000000.+i*.125,arbitration_id=256+i,
            channel=0,is_extended_id=extended,is_fd=fd,is_remote_frame=remote,is_error_frame=error,
            dlc=length,data=b'' if remote else bytes(range(length)),is_rx=i%2==0,
            bitrate_switch=fd,error_state_indicator=fd)
            for i,(extended,fd,remote,error,length) in enumerate([
                (False,False,False,False,2),(True,False,False,False,3),
                (False,True,False,False,12),(False,False,True,False,4),
                (False,False,False,True,0)])]
        writer=BLFWrite(self.path)
        for message in messages:writer.write(message)
        writer.finish();writer.close();self.assertTrue(writer.closed)
        with can.BLFReader(self.path) as reader:actual=list(reader)
        self.assertEqual(len(actual),len(messages))
        fields=('arbitration_id','channel','is_extended_id','is_fd','is_remote_frame','is_error_frame','dlc','data')
        for expected,record in zip(messages,actual):
            self.assertEqual(tuple(getattr(record,k) for k in fields),tuple(getattr(expected,k) for k in fields))
            self.assertAlmostEqual(record.timestamp,expected.timestamp,places=6)
        before=self.path.read_bytes()
        with self.assertRaises(FileExistsError):BLFWrite(self.path)
        self.assertEqual(self.path.read_bytes(),before)

    def test_constructor_failure_closes_same_claim(self):
        """BLF头构造尚未返回时失败，实际独占文件仍关闭，原错保持身份。"""
        opened=[];sentinel=ValueError('header')
        def fail(file):
            """记录实际文件并注入头错误。参数: file已独占取得的文件。返回: 无。异常: 原sentinel。"""
            opened.append(file);raise sentinel
        with patch('can.BLFWriter',side_effect=fail):
            with self.assertRaises(ValueError) as caught:BLFWrite(self.path)
        self.assertIs(caught.exception,sentinel);self.assertEqual(len(opened),1)
        self.assertTrue(opened[0].closed)

    def test_stop_failure_does_not_retry_flush_or_publish(self):
        """最终写入在关闭前或后失败均保原错；恢复close不再次执行第三方stop。"""
        for after in (False,True):
            path=self.path.with_name(str(after)+'.blf');calls=[];sentinel=OSError('finalize')
            class Writer:
                def __init__(self,file):
                    """保存借用的实际文件。参数: file实际输出。返回: None。异常: 无主动异常。"""
                    self.file=file
                def stop(self):
                    """在指定关闭阶段注入错误。参数: 无。返回: 无。异常: 本例finalize哨兵。"""
                    calls.append(1)
                    if after:self.file.close()
                    raise sentinel
            with patch('can.BLFWriter',Writer):writer=BLFWrite(path)
            with self.assertRaises(OSError) as caught:writer.finish()
            self.assertIs(caught.exception,sentinel);self.assertTrue(writer.closed)
            writer.close();writer.close();self.assertEqual(calls,[1])
            with self.assertRaises(RuntimeError):writer.finish()

    def test_constructor_and_file_close_failures_expose_real_owner(self):
        """原构造错及未关闭文件责任一起保留，恢复只关闭原句柄。"""
        original=Path.open;opened=[];blocked=[True];sentinel=ValueError('header')
        class File:
            def __init__(self,actual):
                """包装同一句柄用于关闭故障。参数: actual真实文件。返回: None。异常: 无主动异常。"""
                self.actual=actual
            def __getattr__(self,name):
                """透传文件属性。参数: name属性名。返回: 原属性。异常: 原属性查找错误。"""
                return getattr(self.actual,name)
            def close(self):
                """在恢复前拒绝关闭，恢复后关闭原句柄。参数: 无。返回: None。异常: 注入关闭错误或原关闭错误。"""
                if blocked[0]:raise OSError('close')
                self.actual.close()
        def claim(path,*args,**kwargs):
            """仅包装本例目标文件。参数: 路径及原打开参数。返回: 本例包装器或原文件。异常: 原打开错误。"""
            actual=original(path,*args,**kwargs)
            if path!=self.path:return actual
            file=File(actual);opened.append(file);return file
        with patch.object(Path,'open',claim),patch('can.BLFWriter',side_effect=sentinel):
            with self.assertRaises(ValueError) as caught:BLFWrite(self.path)
        self.assertIs(caught.exception,sentinel);self.assertFalse(opened[0].closed)
        owner=caught.exception.blf_write_cleanup_owner
        blocked[0]=False;owner.close();owner.close()
        self.assertTrue(owner.closed);self.assertTrue(opened[0].closed);self.assertEqual(len(opened),1)


if __name__=='__main__':unittest.main()
