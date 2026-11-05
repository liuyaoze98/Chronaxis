"""从真实公开计划核对枚举原码与标签视图，并保护旧版和按需投影。"""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from chronaxis import AnalysisPlan, AnalysisRunner, PlanValidationError
from chronaxis.core.types import SignalDType as D, QualityFlag as Q
from chronaxis.core import (SignalBindings, SignalDefinition, SessionSpec, SourceSpec,
                            TimebaseSpec, TimeType, compile_expression)
from chronaxis.core.models import Interval, MemoryRow
from chronaxis.core.calculations import CalculationDefinition
from chronaxis.core.calculations_memory_reference import select_memory_reference
from chronaxis.core.calculations_memory_numpy import select_memory_numpy


class EnumCodeV4Tests(unittest.TestCase):
    """同标签原码、未映射整数、显式无效及缺值用同一可复现输入对照。"""

    def config(self):
        """构造明确给出原码类型的内存计划。参数: 无。返回: 配置字典。异常: 无。"""
        values = (7, 9, 33, None, 19, 7)
        return dict(config_version=4, dataset=dict(name='codes'),
            sources=[dict(name='table',source_type='memory',rows=[
                dict(time=f'{i}s',values=dict(raw=value)) for i,value in enumerate(values)])],
            signals=[dict(name='mode',dtype='enum',code_dtype='uint64',unit='1',field='raw',
                          choices=[[7,'On'],[9,'On']],invalid_values=[19],valid_for='3s')],
            calculations=[dict(name='code',operation='select',expr='enum_code(mode)'),
                          dict(name='label',operation='select',expr='mode')])

    def test_public_rows_keep_integer_and_independent_mapping_quality(self):
        """7、9 同标签，33 无标签但有合法原码，缺失和无效值影响两视图。

        参数: 无。返回: None。异常: 任一后端丢原码、标签或质量时断言失败。
        """
        for backend in ('reference','numpy'):
            with self.subTest(backend=backend), TemporaryDirectory(dir='work',prefix='enum-code-') as folder:
                with AnalysisRunner(backend).run(AnalysisPlan.from_dict(self.config()),work_dir=Path(folder)/'run') as result:
                    items = tuple(result.iter_selections())
                    codes = [row for row in items if row.calculation_id == 'code']
                    labels = [row for row in items if row.calculation_id == 'label']
                    self.assertEqual([r.value for r in codes], [7,9,33,None,None])
                    self.assertTrue(all(r.dtype == D.UINT64.value for r in codes))
                    self.assertEqual([r.value for r in labels], ['On','On',None,None,None])
                    self.assertEqual([r.quality for r in codes], [Q.NONE,Q.NONE,Q.NONE,Q.MISSING,Q.OUT_OF_RANGE])
                    self.assertEqual(labels[2].quality,Q.OUT_OF_RANGE)

    def test_original_type_is_required_only_for_the_code_view(self):
        """内存正整数不能证明有符号性，标签单独可用。参数: 无。返回: None。异常: 断言错误。"""
        raw = self.config()
        del raw['signals'][0]['code_dtype']
        with self.assertRaisesRegex(PlanValidationError,'code_dtype'):
            AnalysisPlan.from_dict(raw)
        raw['calculations'].pop(0)
        AnalysisPlan.from_dict(raw)

    def test_projection_allocates_no_code_column_for_label_only_reads(self):
        """即使声明原码类型，只读标签仍无单独整数列。参数: 无。返回: None。异常: 投影或范围断言失败。"""
        from dataclasses import replace
        from chronaxis.sources.packing import pack_message_values
        signal = AnalysisPlan.from_dict(self.config()).signals[0].definition
        for backend in ('reference','numpy'):
            values = (7,9,-1,True,1.5)
            labels = pack_message_values(signal,values,backend)
            self.assertIsNone(labels.code)
            requested = pack_message_values(replace(signal,capture_code=True),values,backend)
            self.assertEqual(requested.code.values[:2].tolist(),[7,9])
            self.assertEqual(requested.code.quality.tolist(),[0,0,Q.OVERFLOW,Q.DECODE_ERROR,Q.DECODE_ERROR])

    def test_csv_keeps_exact_unsigned_integer_without_any_label_reverse_lookup(self):
        """从独立信号表读取大于2^63的未映射整数。参数: 无。返回: None。异常: 精度丢失或符号错误。"""
        with TemporaryDirectory(dir='work', prefix='enum-csv-') as folder:
            path = Path(folder).resolve() / 'input.csv'
            large = 2 ** 63 + 3
            path.write_text(f't,raw\n0,7\n1,{large}\n2,9\n',encoding='utf-8')
            raw = self.config()
            raw['sources'] = [dict(name='table',source_type='signal_csv',path=str(path),
                                  time_column='t',time=dict(unit='s'))]
            for backend in ('reference','numpy'):
                with AnalysisRunner(backend).run(AnalysisPlan.from_dict(raw),work_dir=path.parent/backend) as result:
                    codes = [row for row in result.iter_selections() if row.calculation_id=='code']
                    self.assertEqual([row.value for row in codes],[7,large])

    def test_dbc_proves_raw_integer_dtype_for_records_and_current_messages(self):
        """DBC 的未缩放有符号字段在普通保持和逐消息内核中保留相同原码。

        参数: 无。返回: None。异常: 自动原码类型、累计值、缩放或符号冲突未检出。
        """
        import test_current_message_calculation as message
        with TemporaryDirectory(dir='work',prefix='enum-dbc-') as folder:
            base = Path(folder).resolve()
            dbc, asc = base/'mode.dbc', base/'mode.asc'
            text = ('VERSION ""\nNS_ :\nBS_:\nBU_: Node\nBO_ 256 Frame: 1 Node\n'
                    ' SG_ Power : 0|8@1- (1,0) [-128|127] "1" Node\n'
                    'VAL_ 256 Power 7 "On" 9 "On";\n')
            dbc.write_text(text,encoding='utf-8')
            asc.write_text('date Mon Jan 01 00:00:00.000 2024\nbase hex timestamps absolute\n'
                           'internal events logged\n0 1 100 Rx d 1 07\n1 1 100 Rx d 1 09\n2 1 100 Rx d 1 FF\n',
                           encoding='ascii')
            raw = message.config('can_asc')
            raw.update(config_version=4,dataset=dict(name='enum'))
            raw['sources'][0].update(path=str(asc),dbc_by_channel={'1':str(dbc)})
            signal = raw['signals'][0]
            signal.update(dtype='enum',unit='1',valid_for='3s')
            signal.pop('conversion', None)  # 本例由自己的枚举DBC推导单位，不继承功率夹具的W。
            raw['message_calculations'][0].update(expr='enum_code(power)',unit='1')
            raw['calculations'] = [dict(name='code',operation='select',expr='enum_code(power)')]
            plan = AnalysisPlan.from_dict(raw)
            self.assertIs(plan.signals[0].definition.code_dtype,D.INT64)
            for backend in ('reference','numpy'):
                with AnalysisRunner(backend).run(plan,work_dir=base/backend) as result:
                    self.assertEqual([r.value for r in result.iter_selections()],[7,9])
                    self.assertEqual([r.value for r in result.iter_calculations()],[15.])
            signal['code_dtype'] = 'uint64'
            with self.assertRaisesRegex(PlanValidationError,'code_dtype'):
                AnalysisPlan.from_dict(raw)
            signal['code_dtype'] = 'int64'
            dbc.write_text(text.replace('(1,0)','(2,0)'),encoding='utf-8')
            with self.assertRaisesRegex(PlanValidationError,'enum_code'):
                AnalysisPlan.from_dict(raw)

    def test_real_history_and_independent_memory_backends(self):
        """在真实封存历史与两个独立内存归约器中验证相同选择、原码及过期边界。

        参数: 无。返回: None。异常: 历史解码、保持、类型或预算与期望不符。
        """
        import test_historical_selection_rows as fixture_module
        definitions = (SignalDefinition('a','table','raw.a',D.ENUM,'1',3,choices=((7,'On'),(9,'On')),
                                        code_dtype=D.INT64,config_version=4),
                       SignalDefinition('b','other','raw.b',D.INT64,'1',6,config_version=4))
        rows = {'table':tuple(MemoryRow(i,{'raw.a':x},i) for i,x in enumerate((7,9,44,None,7))),
                'other':(MemoryRow(0,{'raw.b':1},0),MemoryRow(4,{'raw.b':1},1))}
        clock = TimebaseSpec('clock',TimeType.RELATIVE,'enum-test')
        sources = tuple(SourceSpec(name,clock,data,observation_start_ns=0,observation_end_ns=4)
                        for name,data in rows.items())
        bindings = SignalBindings(SessionSpec('session',clock,0,4,sources),definitions)
        spec = CalculationDefinition('code','select',Interval(0,4),config_version=4)
        compiled = compile_expression('enum_code(a)',bindings)
        expected = [(7,Q.NONE),(9,Q.NONE),(44,Q.NONE),(None,Q.MISSING)]
        for kernel in (select_memory_reference,select_memory_numpy):
            self.assertEqual([(r.value.value,r.quality) for r in kernel(compiled,spec)],expected)
        factory = fixture_module.HistoricalSelectionRowsTests('runTest')
        self.addCleanup(factory.doCleanups)
        for backend in ('reference','numpy'):
            fixture,owner,baseline = factory.prepare(backend=backend,definitions=definitions,rows_by_source=rows,
                texts=('enum_code(a)','b > 0'),domain=(0,4),spec=spec)
            self.assertEqual([(r.value.value,r.quality) for r in owner],expected)
            factory.close_and_check(fixture,owner,baseline)
