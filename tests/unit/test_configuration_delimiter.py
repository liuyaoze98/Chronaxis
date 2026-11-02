"""[home] 核对信号CSV和原始CSV统一使用delimiter，不保留sep别名。

用实际分号表验证两后端的面积；配置展开必须可重载，错误字段不能被默认值掩盖。
仅在临时目录写合成输入和结果，不读取历史资源。
"""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from chronaxis import AnalysisPlan, AnalysisRunner, PlanValidationError
from chronaxis.configuration.resolution import resolved_configuration


class ConfigurationDelimiterTests(unittest.TestCase):
    """统一字段名称不改变CSV解析和积分结果。"""

    def test_semicolon_defaults_resolve_and_reject_old_name(self):
        """分号表0/1/2秒功率3/1/3W，前值保持积分为4J；两种配置展开均保持。"""
        with TemporaryDirectory(prefix='chronaxis-delimiter-') as folder:
            root=Path(folder);data=root/'input.csv'
            data.write_text('time;power\n0;3\n1;1\n2;3\n',encoding='utf-8')
            raw=dict(config_version=3,dataset=dict(name='csv',domain=dict(start='0s',end='2s')),
                sources=[dict(source_type='signal_csv',path=str(data),time_column='time',
                              time=dict(unit='s'),reader=dict(delimiter=';'))],
                signals=[dict(name='power',field='power',dtype='float64',unit='W',valid_for='3s')],
                calculations=[dict(name='energy',operation='integral',expr='power')])
            plan=AnalysisPlan.from_dict(raw)
            self.assertEqual(plan.sources[0].config.delimiter,';')
            for backend in ('reference','numpy'):
                with AnalysisRunner(backend).run(plan,work_dir=root/backend) as result:
                    row=next(result.iter_calculations())
                    self.assertEqual((row.value,row.unit),(4.,'J'))
            path=root/'plan.json';path.write_text(json.dumps(raw),encoding='utf-8')
            for defaults in (False,True):
                resolved=resolved_configuration(path,defaults=defaults)
                self.assertNotIn('sep',resolved['sources'][0])
                self.assertEqual(AnalysisPlan.from_dict(resolved).sources[0].config.delimiter,';')
            raw['sources'][0]['sep']=';'
            with self.assertRaises(PlanValidationError):AnalysisPlan.from_dict(raw)
            raw['sources'][0].pop('sep');raw['sources'][0]['reader'].pop('delimiter')
            self.assertEqual(AnalysisPlan.from_dict(raw).sources[0].config.delimiter,',')
