"""比较官方无缓存文件入口与共用文本入口，不使用实际业务DBC或持久缓存。

每个依赖环境分别以自身load_file无缓存分支为对照，再核手算值和公开元数据。
环境变量只在独立测试进程的上下文中设置，产品代码不得修改它。
"""
from contextlib import ExitStack
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from workspace_fixtures import TemporaryDirectory
import cantools
from chronaxis.dbc_loading import load_dbc_file


DBC = '''VERSION "sample"
NS_ :
BS_:
BU_: Node
BO_ 256 Frame: 4 Node
 SG_ State : 16|8@1+ (1,0) [0|255] "" Node
 SG_ Current : 0|16@1- (0.1,-2) [-100|100] "A" Node
BO_ 257 Multiplex: 2 Node
 SG_ Selector M : 0|8@1+ (1,0) [0|255] "" Node
 SG_ First m1 : 8|8@1+ (2,1) [0|511] "V" Node
 SG_ Second m2 : 8|8@1+ (2,1) [0|511] "V" Node
CM_ SG_ 256 Current "café CORRUPT";
VAL_ 256 State 1 "MODE_IDLE" 2 "MODE_ACTIVE";
BA_DEF_ BO_ "GenMsgCycleTime" INT 0 65535;
BA_ "GenMsgCycleTime" BO_ 256 100;
'''


class _ReadCount:
    """只给实际文件句柄附读取计数，退出仍由其原上下文处理。"""

    def __init__(self, handle):
        """保存本次真实句柄。参数: handle为文本文件。返回: None。异常: 无主动异常。"""
        self.handle = handle
        self.reads = 0

    def __enter__(self):
        """进入真实文件上下文。参数: 无。返回: 本包装。异常: 原上下文错误。"""
        self.handle.__enter__()
        return self

    def __exit__(self, kind, value, traceback):
        """按原参数关闭真实文件。参数: 原异常三元组。返回: 原结果。异常: 原关闭错误。"""
        return self.handle.__exit__(kind, value, traceback)

    def read(self, *args):
        """计一次实际文本读取。参数: read原参数。返回: 文本。异常: 原读取错误。"""
        self.reads += 1
        return self.handle.read(*args)


class DBCGatewayEquivalenceTests(unittest.TestCase):
    """格式、编码、元数据、解码、无缓存及句柄生命周期共同核对。"""

    def setUp(self):
        """创建独立合成DBC。参数: 无。返回: None。异常: 原临时目录或文件错误。"""
        self.directory = TemporaryDirectory(prefix='dbc-gateway-')
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.path = self.root / 'sample.DBC'
        self.path.write_bytes(DBC.encode('cp1252').replace(b'CORRUPT', b'\x81'))

    def baseline(self, path):
        """在测试进程禁用环境缓存后调用原入口。参数: 路径。返回: 数据库。异常: 原加载错。"""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('CANTOOLS_CACHE_DIR', None)
            return cantools.database.load_file(path)

    def facts(self, database):
        """列出公开解析事实。参数: 数据库。返回: 有序tuple。异常: 原属性访问错误。"""
        return (database.version, tuple(node.name for node in database.nodes), tuple(
            (message.frame_id, message.name, message.length, message.is_extended_frame,
             message.is_fd, message.cycle_time, tuple(
                 (signal.name, signal.start, signal.length, signal.is_signed, signal.is_float,
                  signal.byte_order, signal.scale, signal.offset, signal.minimum, signal.maximum,
                  signal.unit, signal.comment, signal.is_multiplexer,
                  tuple(signal.multiplexer_ids or ()), signal.multiplexer_signal,
                  tuple((key,str(value)) for key,value in (signal.choices or {}).items()))
                 for signal in message.signals)) for message in database.messages))

    def test_metadata_sort_choices_cycles_and_decoding_match_original(self):
        """元数据和复用解码一致，独立核0A/7V。参数: 无。返回: None。异常: 断言或解析错。"""
        expected = self.baseline(str(self.path))
        actual = load_dbc_file(self.path, cantools)
        self.assertEqual(self.facts(actual), self.facts(expected))
        frame = actual.get_message_by_frame_id(256)
        self.assertEqual([signal.name for signal in frame.signals], ['Current', 'State'])
        self.assertEqual(frame.cycle_time, 100)
        self.assertEqual(frame.signals[0].comment, 'café \ufffd')
        self.assertEqual(str(frame.signals[1].choices[2]), 'MODE_ACTIVE')
        self.assertEqual(actual.decode_message(256, bytes([20,0,2,0]), decode_choices=False),
                         {'Current': 0.0, 'State': 2})
        for payload, result in [(bytes([1,3]), {'Selector': 1,'First':7}),
                                (bytes([2,4]), {'Selector': 2,'Second':9})]:
            self.assertEqual(actual.decode_message(257,payload,decode_choices=False),result)
            self.assertEqual(expected.decode_message(257,payload,decode_choices=False),result)

    def test_formats_and_failures_match_original_no_cache_path(self):
        """原后缀与错误类型文字保持。参数: 无。返回: None。异常: 对照断言失败。"""
        for name, contents in [('copy.dbc',self.path.read_bytes()),
                               ('unknown.extension',self.path.read_bytes()),
                               ('no_extension',self.path.read_bytes()),
                               ('broken.dbc',b'not a dbc'),('broken.sym',b'bad sym'),
                               ('broken.kcd','不是合法XML'.encode('utf8'))]:
            with self.subTest(name=name):
                path=self.root/name
                path.write_bytes(contents)
                try:
                    expected=self.baseline(path)
                except Exception as error:
                    with self.assertRaises(type(error)) as raised:
                        load_dbc_file(path,cantools)
                    self.assertEqual(str(raised.exception),str(error))
                else:
                    self.assertEqual(self.facts(load_dbc_file(path,cantools)),self.facts(expected))
        missing=self.root/'missing.dbc'
        for reader in (self.baseline,lambda path:load_dbc_file(path,cantools)):
            with self.assertRaises(FileNotFoundError) as raised:
                reader(missing)
            self.assertEqual(raised.exception.filename,str(missing))

    def test_one_open_one_read_and_close_on_success_or_parser_failure(self):
        """一次打开与读取，解析失败也关闭。参数: 无。返回: None。异常: 原I/O错或断言。"""
        real_open=open
        for corrupt in (False,True):
            with self.subTest(corrupt=corrupt):
                path=self.root/('bad.dbc' if corrupt else 'sample.DBC')
                if corrupt:path.write_text('bad dbc',encoding='ascii')
                owners=[]
                def opened(*args,**kwargs):
                    """包装同次真实句柄。参数: 原open参数。返回: 计数包装。异常: 原open错误。"""
                    owner=_ReadCount(real_open(*args,**kwargs))
                    owners.append(owner)
                    return owner
                with patch('builtins.open',side_effect=opened) as opening:
                    if corrupt:
                        with self.assertRaises(cantools.database.UnsupportedDatabaseFormatError):
                            load_dbc_file(path,cantools)
                    else:load_dbc_file(path,cantools)
                opening.assert_called_once_with(path,encoding='cp1252',errors='replace')
                self.assertEqual(len(owners),1)
                self.assertEqual(owners[0].reads,1)
                self.assertTrue(owners[0].handle.closed)

    def test_environment_cache_never_constructed_or_changed(self):
        """即使缓存依赖存在且环境指定目录也不访问。参数: 无。返回: None。异常: 缓存调用或断言。"""
        existing=self.root/'existing-cache'
        existing.mkdir()
        marker=existing/'untouched'
        marker.write_bytes(b'keep')
        new=self.root/'new-cache'
        for setting in (None,'',str(existing),str(new)):
            with self.subTest(setting=setting),patch.dict(os.environ,{},clear=False),ExitStack() as stack:
                if setting is None:os.environ.pop('CANTOOLS_CACHE_DIR',None)
                else:os.environ['CANTOOLS_CACHE_DIR']=setting
                before=dict(os.environ)
                blocked=Mock(side_effect=AssertionError('Cache must not be constructed'))
                stack.enter_context(patch.object(cantools.database,'diskcache',SimpleNamespace(Cache=blocked),create=True))
                stack.enter_context(patch.object(cantools.database,'_DISKCACHE_AVAILABLE',True,create=True))
                stack.enter_context(patch.object(cantools.database,'load_file',side_effect=AssertionError('cache-capable entry forbidden')))
                result=load_dbc_file(self.path,cantools)
                self.assertEqual(result.get_message_by_frame_id(256).cycle_time,100)
                blocked.assert_not_called()
                self.assertEqual(dict(os.environ),before)
                self.assertFalse(new.exists())
                self.assertEqual(marker.read_bytes(),b'keep')
                self.assertEqual(list(existing.iterdir()),[marker])


if __name__ == '__main__':
    unittest.main()
