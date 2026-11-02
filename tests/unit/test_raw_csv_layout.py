"""用明确的中文列/枚举证明原始报文表可配置，未知含义不会被猜测。

核心用例仅使用内存表头与行，构造/绑定不得打开文件。两个仓库原样GBK样例
只读前两行单列验证，不把映射完成写成时间/帧解析或DBC分析已经完成。
"""

from configuration_fixtures import current_fixture

import csv
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from chronaxis.sources.raw_csv_layout import CANCSVLayout, ColumnMapping, BoundCANCSVLayout


class RawCSVLayoutTests(unittest.TestCase):
    """隔离配置校验、表头绑定和值映射，时间与载荷数值转换留B2。"""

    def fields(self):
        """提供可直接审阅的规范声明。参数: 无。返回: 新字段dict。异常: 无。
        """
        # 把随记录变化的列与明确固定身份分开，后续样例只换表头映射。
        return {'timestamp':ColumnMapping(column='时间'), 'frame_id':ColumnMapping(column='ID'),
                'payload_length':ColumnMapping(column='长度'), 'data':ColumnMapping(column='数据'),
                'channel':ColumnMapping(fixed=0), 'is_rx':ColumnMapping(fixed=True),
                'is_extended':ColumnMapping(fixed=False), 'is_fd':ColumnMapping(fixed=False),
                'frame_kind':ColumnMapping(fixed='data')}

    def test_construction_binding_and_mapping_do_not_open_files(self):
        """配置与取列均不扫描输入/DBC。参数: 无。返回: None。异常: 断言失败。
        """
        # 禁止实际打开，证明配置/绑定不偷偷扫描来源；只读结果也不可被事后改写。
        with patch.object(Path,'open',side_effect=AssertionError('must not open')):
            layout = CANCSVLayout(self.fields())
            row = layout.bind_header(['时间','ID','长度','数据']).map_row(['0','123','1',' FF '])
        self.assertEqual((row['data'],row['channel'],row['is_rx'],row['bitrate_switch']), ('FF',0,True,False))
        with self.assertRaises(TypeError):
            row['channel'] = 9

    def test_chinese_enums_and_column_meanings_are_explicit(self):
        """帧格式/帧类型名字交换时只以配置为准。参数: 无。返回: None。异常: 断言失败。
        """
        # 故意交换常见中文列的含义，结果只能取决于显式映射，未知值应拒绝。
        fields = self.fields()
        fields.update(is_extended=ColumnMapping(column='帧格式',value_map={'标准帧':False,'扩展帧':True}),
                      frame_kind=ColumnMapping(column='帧类型',value_map={'数据帧':'data','远程帧':'remote'}),
                      is_rx=ColumnMapping(column='方向',value_map={'接收':True,'发送':False}))
        bound = CANCSVLayout(fields).bind_header(['时间','ID','长度','数据','帧格式','帧类型','方向'])
        row = bound.map_row(['0','123','1','ff','扩展帧','数据帧','发送'])
        self.assertEqual((row['is_extended'],row['frame_kind'],row['is_rx']), (True,'data',False))
        with self.assertRaisesRegex(ValueError,'value_map'):
            bound.map_row(['0','123','1','ff','不知道','数据帧','接收'])

    def test_indices_are_one_based_and_numeric_strings_are_names(self):
        """列号从1开始，字符串3不偷偷变成第3列。参数: 无。返回: None。异常: 断言失败。
        """
        # 无表头只用明确整数列号；另验证字符串数字通过名字绑定。
        fields = self.fields()
        fields.update(timestamp=ColumnMapping(column=1), frame_id=ColumnMapping(column=2),
                      payload_length=ColumnMapping(column=3),data=ColumnMapping(column=4))
        row = CANCSVLayout(fields,has_header=False).bind_header().map_row(['0','123','1','ff'])
        self.assertEqual(row['frame_id'],'123')
        with self.assertRaisesRegex(ValueError,'无表头'):
            CANCSVLayout(self.fields(),has_header=False)
        fields['timestamp'] = ColumnMapping(column='3')
        bound = CANCSVLayout(fields).bind_header(['3','ID','长度','数据'])
        self.assertEqual(bound.map_row(['0','123','1','ff'])['timestamp'],'0')

    def test_frozen_input_copies_and_json_roundtrip(self):
        """调用方后改dict不能改变已计划的映射。参数: 无。返回: None。异常: 断言失败。
        """
        # 绑定创建后更改外部字典，已冻结布局仍须保持原来的通道/方向。
        values = {'接收':True}
        mapping = ColumnMapping(column=5,value_map=values)
        fields = self.fields(); fields['is_rx'] = mapping
        layout = CANCSVLayout(fields)
        values['接收'] = False; fields['channel'] = ColumnMapping(fixed=99)
        row = layout.bind_header(['时间','ID','长度','数据','方向']).map_row(['0','123','1','ff','接收'])
        self.assertEqual((row['channel'],row['is_rx']),(0,True))
        # 完整声明可用JSON往返，默认False也不能在序列化中丢失。
        restored = CANCSVLayout.from_dict(json.loads(json.dumps(current_fixture(layout.to_dict()),ensure_ascii=False)))
        self.assertEqual(layout.to_dict(),restored.to_dict())
        with self.assertRaises(FrozenInstanceError):
            restored.delimiter = '\t'

    def test_header_duplicates_missing_columns_and_short_rows(self):
        """缺列和重名不能选第一个或默默补空。参数: 无。返回: None。异常: 断言失败。
        """
        # 不取重复列的第一个值；行中缺少所需列也不能用空字符串补齐。
        layout = CANCSVLayout(self.fields())
        for header in (['时间','ID','长度','数据','ID'],['时间','ID','长度']):
            with self.assertRaises(ValueError):
                layout.bind_header(header)
        bound = layout.bind_header(['时间','ID','长度','数据',''])
        with self.assertRaises(ValueError):
            bound.map_row(['0','123','1'])
        # 空的未选中尾表头允许；未使用列不检查其值，也不制造无用转换。
        self.assertEqual(bound.map_row(['0','123','1','ff',object()])['data'],'ff')

    def test_strict_options_field_types_and_bounds(self):
        """未知键/列号/错误标志在配置或绑定处拒绝。参数: 无。返回: None。异常: 断言失败。
        """
        # 逐项拒绝来源不唯一、错误列号、空枚举以及无法匹配的带空白映射键。
        for options in ({}, {'column':0}, {'column':True}, {'column':4097},
                        {'column':1,'fixed':0}, {'fixed':None}, {'column':1,'value_map':{}},
                        {'column':1,'value_map':{' 接收':True}}):
            with self.subTest(options=options), self.assertRaises((ValueError,TypeError)):
                ColumnMapping(**options)
        # 固定值和静态配置无需读数据就能发现身份/载荷类型错误。
        fields = self.fields()
        for name,value in (('is_rx',ColumnMapping(fixed='未知方向')),
                           ('data',ColumnMapping(fixed=123)),
                           ('channel',ColumnMapping(fixed=True)),
                           ('frame_kind',ColumnMapping(fixed='未知帧'))):
            with self.subTest(field=name), self.assertRaises(ValueError):
                CANCSVLayout({**fields,name:value})
        for options in ({'delimiter':'::'},{'delimiter':'\n'},{'skip_rows':True},{'has_header':1}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                CANCSVLayout(fields,**options)
        with self.assertRaises(ValueError):
            CANCSVLayout.from_dict({**CANCSVLayout(fields).to_dict(),'guess_format':True})
        with self.assertRaises(ValueError):
            ColumnMapping.from_dict({'column':1,'default':False})
        layout = CANCSVLayout({k:v for k,v in fields.items() if k!='payload_length'})
        self.assertNotIn('payload_length',layout.fields)

    def test_two_real_gbk_tables_keep_actual_cell_values(self):
        """原CSV和制表TXT只读前两行，保留原时间/载荷文字。参数: 无。返回: None。异常: 断言失败。
        """
        # 两类源文件只读头两条，GBK/分隔符和列名都由本用例明确给出。
        cases = [('RefProjects/CSVConvert/test/原始报文.csv',',','时间标识','帧ID','数据长度','数据(HEX)',
                  '14:05:40.151.0','0x0055ffff',True),
                 ('RefProjects/CSVConvert/test/Frame(0-9999).txt','\t','时间戳','ID','长度','数据',
                  '15:24:15.364.0','0x00000218',False)]
        for path,delimiter,time_column,id_column,length_column,data_column,time_text,identifier,extended in cases:
            with self.subTest(path=path):
                if not Path(path).exists():
                    self.skipTest('本环境缺仓库原样表格，合成映射测试独立保留')
                with Path(path).open('r',encoding='gbk',newline='') as stream:
                    rows = csv.reader(stream,delimiter=delimiter,strict=True)
                    header,first = next(rows),next(rows)
                fields = self.fields()
                fields.update(timestamp=ColumnMapping(column=time_column), frame_id=ColumnMapping(column=id_column),
                              payload_length=ColumnMapping(column=length_column),data=ColumnMapping(column=data_column),
                              is_rx=ColumnMapping(column='传输方向',value_map={'接收':True,'发送':False}),
                              frame_kind=ColumnMapping(column='帧格式',value_map={'数据帧':'data','远程帧':'remote'}),
                              is_extended=ColumnMapping(column='帧类型',value_map={'标准帧':False,'扩展帧':True}))
                layout = CANCSVLayout(fields,encoding='gbk',delimiter=delimiter)
                result = layout.bind_header(header).map_row(first)
                self.assertEqual((result['timestamp'],result['frame_id'],result['is_extended']),
                                 (time_text,identifier,extended))
                self.assertEqual((result['channel'],result['frame_kind'],result['is_fd']), (0,'data',False))

    def test_direct_bound_constructor_rejects_false_position(self):
        """公开绑定模型不能让整数列号与实际位置矛盾。参数: 无。返回: None。异常: 断言失败。
        """
        # 故意把第2列伪装成0基位置0，结构校验必须在取值前拒绝。
        bound = CANCSVLayout(self.fields()).bind_header(['时间','ID','长度','数据'])
        entries = list(bound.bindings)
        entries[0] = ('timestamp',ColumnMapping(column=2),0)
        with self.assertRaisesRegex(ValueError,'矛盾'):
            BoundCANCSVLayout(tuple(entries))
