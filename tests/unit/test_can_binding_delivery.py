"""验证简化CAN绑定在schema、模板和报文重建入口中的实际行为。

输入为声明的合成DBC与原帧；用不同帧类型共享ID构造歧义，核对输出仍保留
原帧身份。只使用临时目录，不读取或修改历史项目；费用必须在关闭后归零。
"""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from jsonschema import Draft202012Validator
from chronaxis.execution.frame_capture import FrameDBCContext
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.frame_patch import FrameRebuildRule, DBCFramePatch
from chronaxis.configuration import load_configuration
from chronaxis.configuration.initialization import initialize_configuration
from chronaxis.legacy.records import field_from_dict
from test_frame_exports import raw


class CANBindingDeliveryTests(unittest.TestCase):
    """每例使用独立资源，验证用户声明与实际帧型之间的边界。"""

    def test_binding_schema_and_optional_validity(self):
        """新结构允许进制文本及省略项，拒绝message和显式null。

        参数: 无。返回: None。异常: 断言失败表示schema与新契约不一致。
        """
        schema=json.loads(Path('Docs/Schema/analysis.schema.json').read_text(encoding='utf-8'))
        Draft202012Validator.check_schema(schema)
        signal_schema=schema['properties']['signals']['items']
        validator=Draft202012Validator(signal_schema)
        base={'name':'voltage','source':'bus','field':{'channel':1,'frame_id':'0x100','signal':'V'},
              'dtype':'float64','unit':'V'}
        for identifier in ('0x100','0b100000000','0256',256):
            candidate=deepcopy(base); candidate['field']['frame_id']=identifier
            self.assertEqual(list(validator.iter_errors(candidate)),[])
        candidate=deepcopy(base); candidate['period']='100ms'
        self.assertEqual(list(validator.iter_errors(candidate)),[])
        for key,value in (('message','Frame'),('is_extended',None),('is_fd',None),
                          ('frame_id','0o400'),('frame_id','+256'),('frame_id','2_56'),('frame_id','256\n')):
            candidate=deepcopy(base); candidate['field'][key]=value
            self.assertTrue(list(validator.iter_errors(candidate)),key)
        # Schema核文本形式；数值转换后的标准帧范围由实际加载器继续核实。
        candidate=deepcopy(base); candidate['field'].update(frame_id='0x800',is_extended=False)
        self.assertEqual(list(validator.iter_errors(candidate)),[])
        with self.assertRaises(ValueError):
            field_from_dict(candidate['field'])
        candidate['field']['frame_id']=2048
        self.assertTrue(list(validator.iter_errors(candidate)))
        # 未限定帧型时大于0x7FF可用于扩展帧，不能被标准帧条件误伤。
        candidate['field'].pop('is_extended')
        self.assertEqual(list(validator.iter_errors(candidate)),[])

    def test_actual_frame_selects_definition_and_later_conflict_fails(self):
        """相同数值ID的标准和扩展定义由实际帧区分，后续换类型要求补参数。

        参数: 无。返回: None。异常: DBC、资源或断言失败。
        """
        text=('VERSION ""\nNS_ :\nBS_:\nBU_: Node\n'
              'BO_ 256 Standard: 8 Node\n SG_ V : 0|8@1+ (1,0) [0|255] "V" Node\n'
              'BO_ 2147483904 Extended: 8 Node\n SG_ V : 0|8@1+ (2,0) [0|510] "V" Node\n')
        budget=ResourceBudget()
        with tempfile.TemporaryDirectory(prefix='can-binding-export-') as folder:
            path=Path(folder)/'signals.dbc'; path.write_text(text,encoding='utf-8')
            context=FrameDBCContext(path,(FrameRebuildRule(0,'0x100',('V',)),),budget,integrity=False)
            try:
                frame=raw(0,0,identifier=256,data=bytes(8),is_extended_id=True).frame
                with patch('cantools.database.load',side_effect=AssertionError('不得重复加载DBC')):
                    context.observe(frame)
                    pairs=context.pairs()
                    self.assertEqual(len(pairs),1)
                    self.assertEqual(pairs[0][1].name,'Extended')
                    # 输出仍使用实际扩展帧，不按小ID改成标准帧。
                    owner=DBCFramePatch(*pairs[0],budget)
                    try:
                        result,_=owner.patch(frame,{'V':20},())
                        self.assertTrue(result.is_extended_id)
                        self.assertEqual(result.data[0],10)
                    finally:
                        owner.close()
                    with self.assertRaisesRegex(ValueError,'is_extended'):
                        context.observe(raw(1,1,identifier=256,data=bytes(8)).frame)
            finally:
                context.close()
        self.assertEqual(budget.ram_bytes,0)

    def test_explicit_type_filters_unrelated_identity(self):
        """显式扩展帧只处理扩展帧，同ID标准帧仍按未选输出处理。

        参数: 无。返回: None。异常: 断言或资源错误。
        """
        rule=FrameRebuildRule(0,'0b100000000',('V',),is_extended=True)
        self.assertTrue(rule.matches(raw(0,0,identifier=256,is_extended_id=True).frame))
        self.assertFalse(rule.matches(raw(0,0,identifier=256).frame))
        self.assertIsNone(rule.is_fd)
        with self.assertRaises(ValueError):
            FrameRebuildRule(0,'0x1000',('V',),is_extended=False)



if __name__=='__main__':
    unittest.main()
