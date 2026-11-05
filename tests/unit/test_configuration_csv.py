"""[home] CSV简写与按需字段：检查真实读帧、两后端计算和导出拒绝未知方向。"""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from chronaxis import AnalysisPlan, AnalysisRunner, PlanValidationError
from chronaxis.sources.raw_csv_layout import CANCSVLayout, ColumnMapping
from chronaxis.sources.raw_csv import CANCSVSpec, CANCSVRead, _uint
from chronaxis.legacy.records import frame_to_dict, frame_from_dict
from chronaxis.results.budget import ResourceBudget
from chronaxis.results.frame_exports import ExportCANFrame, _asc_line
from chronaxis.legacy.export_worker import _message


class ConfigurationCSVTests(unittest.TestCase):
    """样例的0/1/2秒电压为3/1/3V，独立手算面积4Vs。"""

    def setUp(self):
        """建立本例临时表；所有测试关闭reader并回收文件。"""
        self.temp = TemporaryDirectory(prefix='chronaxis-config-csv-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'input.csv'
        self.path.write_text('time,id,data\n0,0x100,01 00\n1,0b100000000,00 00\n2,256,01 00\n',encoding='utf-8')
        dbc = Path(__file__).parents[2] / 'src/chronaxis/configuration/templates/shared/sample.dbc'
        self.raw = dict(config_version=4,dataset=dict(name='csv',domain=dict(start='0s',end='2s')),
            sources=[dict(source_type='raw_can_csv',path=str(self.path),time=dict(unit='s'),
                dbc_by_channel={'1':str(dbc)},reader=dict(time_format='numeric',layout=dict(fields={
                    'timestamp':'time','frame_id':'id','data':'data'})))],
            signals=[dict(name='voltage',field=dict(frame_id='0x100',signal='Voltage'),
                dtype='float64',unit='V',valid_for='3s')],
            calculations=[dict(name='area',operation='integral',expr='voltage')])

    def spec(self, fields=None):
        """独立reader没有来源配置，因此明确提供通道和帧型。"""
        values={'timestamp':'time','frame_id':'id','data':'data',
                'channel':{'fixed':0},'is_extended':{'fixed':False},'is_fd':{'fixed':False}}
        values.update(fields or {})
        return CANCSVSpec(self.path,CANCSVLayout.from_dict({'fields':values}))

    def test_prefixes_shorthand_unknown_direction_and_inferred_length(self):
        """三种进制都得到256；缺方向保持None，实际载荷推导DLC2。"""
        budget=ResourceBudget()
        with CANCSVRead(self.spec(),budget) as reader:
            rows=list(reader)
        self.assertEqual([(r.frame.arbitration_id,r.frame.dlc,r.frame.is_rx) for r in rows],[(256,2,None)]*3)
        self.assertEqual(frame_from_dict(frame_to_dict(rows[0].frame)),rows[0].frame)
        self.assertEqual(budget.ram_bytes,0)
        self.assertEqual(ColumnMapping.from_dict(2),ColumnMapping(column=2))
        for invalid in (True,0,{},None):
            with self.subTest(invalid=invalid),self.assertRaises((ValueError,TypeError)):
                ColumnMapping.from_dict(invalid)

    def test_id_auto_and_explicit_base_are_not_guesses(self):
        """前缀决定进制，无前缀即十进制；显式16仍可读取裸十六进制表。"""
        for value,expected in [('100',100),('0100',100),('0X100',256),('0B100',4)]:
            self.assertEqual(_uint(value,'auto',0x1fffffff,'ID'),expected)
        self.assertEqual(_uint('100',16,0x1fffffff,'ID'),256)
        for value in ('1a','0b2','0x','-1','+1','1_0',True,'0x20000000'):
            with self.subTest(value=value),self.assertRaises(ValueError):
                _uint(value,'auto',0x1fffffff,'ID')

    def test_common_values_and_explicit_mapping_priority(self):
        """方向/帧种类常见文字可直接使用；手动映射优先，未知值报错。"""
        fields={'timestamp':1,'frame_id':2,'data':3,'channel':{'fixed':0},
                'is_rx':4,'frame_kind':5}
        bound=CANCSVLayout.from_dict(dict(fields=fields,has_header=False)).bind_header()
        for text,expected in [('Rx',True),('tx',False),('接收',True),('发送',False)]:
            row=bound.map_row(['0','256','00',text,'数据帧'])
            self.assertEqual((row['is_rx'],row['frame_kind']),(expected,'data'))
        with self.assertRaises(ValueError):bound.map_row(['0','256','00','maybe','data'])
        fields['is_rx']={'column':4,'value_map':{'Rx':False}}
        mapped=CANCSVLayout.from_dict(dict(fields=fields,has_header=False)).bind_header()
        self.assertFalse(mapped.map_row(['0','256','00','Rx','data'])['is_rx'])
        with self.assertRaisesRegex(ValueError,'value_map'):mapped.map_row(['0','256','00','Tx','data'])

    def test_public_minimal_schema_and_two_backends(self):
        """缺方向/长度/通道/帧种类的配置实际分析4Vs，与完整配置相同。"""
        from test_configuration_schema import ConfigurationSchemaTests
        # 使用测试套件已有离线Schema注册，避免网络或另一套手工校验。
        ConfigurationSchemaTests.setUpClass()
        ConfigurationSchemaTests.validators['analysis.schema.json'].validate(self.raw)
        original=deepcopy(self.raw)
        for backend in ('reference','numpy'):
            plan=AnalysisPlan.from_dict(self.raw)
            self.assertEqual(plan.sources[0].config.inputs[0].layout.fields['channel'].fixed,0)
            with AnalysisRunner(backend).run(plan,work_dir=self.root/backend) as result:
                self.assertEqual([row.value for row in result.iter_calculations()],[4.0])
            complete=deepcopy(self.raw)
            fields=complete['sources'][0]['reader']['layout']['fields']
            for key,value in (('channel',0),('is_rx',True),('frame_kind','data'),('payload_length',2)):
                fields[key]={'fixed':value}
            with AnalysisRunner(backend).run(AnalysisPlan.from_dict(complete),work_dir=self.root/(backend+'-full')) as result:
                self.assertEqual([row.value for row in result.iter_calculations()],[4.0])
        self.assertEqual(self.raw,original)

    def test_channel_inheritance_respects_input_origin(self):
        """输入按1基标通道时，继承值先加1，reader最终仍得到来源通道0。"""
        self.raw['sources'][0]['reader']['channel_origin']=1
        spec=AnalysisPlan.from_dict(self.raw).sources[0].config.inputs[0]
        self.assertEqual(spec.layout.fields['channel'].fixed,1)
        with CANCSVRead(spec,ResourceBudget(),flag_resolver=lambda *args:(False,False)) as read:
            self.assertEqual(next(read).frame.channel,0)

    def test_exports_require_direction_before_reading(self):
        """公共输出和底层写出都拒绝未知方向，不会默认为Tx。"""
        self.raw['outputs']={'can_frames':{'format':'asc'}}
        with self.assertRaisesRegex(PlanValidationError,'is_rx'):AnalysisPlan.from_dict(self.raw)
        self.raw['sources'][0]['reader']['layout']['fields']['is_rx']={'fixed':True}
        AnalysisPlan.from_dict(self.raw)
        with CANCSVRead(self.spec(),ResourceBudget()) as reader:frame=next(reader).frame
        record=ExportCANFrame(0,0,0,frame,())
        with self.assertRaisesRegex(ValueError,'is_rx'):_asc_line(record,0)
        with self.assertRaisesRegex(ValueError,'is_rx'):_message(None,frame)

    def test_declared_bad_length_and_remote_missing_dlc_still_fail(self):
        """允许省略数据帧长度不等于忽略显式错误或替远程帧猜DLC。"""
        for fields in ({'payload_length':{'fixed':3}}, {'frame_kind':{'fixed':'remote'}}):
            with self.subTest(fields=fields),self.assertRaises(ValueError):
                with CANCSVRead(self.spec(fields),ResourceBudget()) as read:list(read)
