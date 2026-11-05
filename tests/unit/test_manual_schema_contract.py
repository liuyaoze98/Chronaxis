"""核对审查发现的Schema与公开配置入口差异，不修改解析器行为。

输入为当前三份规范及小型配置副本；输出unittest断言。通过本地标准验证器
与AnalysisPlan/ColumnMapping分别检查可空和边界，不读取CAN数据或写工作目录。
"""

from configuration_fixtures import current_fixture
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator
from chronaxis import AnalysisPlan, PlanValidationError
from chronaxis.sources.raw_csv_layout import ColumnMapping
import test_configuration_schema as schema_support
from test_analysis_plan import config_fixture


class ManualSchemaContractTests(unittest.TestCase):
    """每项保留独立配置副本，Schema通过与运行入口接受须分别成立。"""

    @classmethod
    def setUpClass(cls):
        """参数: 无。返回: None。异常: 本地规范读取或标准验证失败传播。"""
        # 复用离线注册，不从网络补齐规范。
        schema_support.ConfigurationSchemaTests.setUpClass()
        cls.documents=schema_support.ConfigurationSchemaTests.documents
        cls.validators=schema_support.ConfigurationSchemaTests.validators

    def test_nullable_metadata_matches_analysis_and_definitions(self):
        """参数: 无。返回: None。异常: 省略/null/空文本的合同不一致时断言失败。"""
        # 默认省略的合法配置必须保持可用；逐字段null不应被编辑器误报。
        fields=('input_unit','semantic_id','semantic_contract_version','mapping_version','sign_convention','measurement_location')
        for name in fields:
            for value,valid in ((None,name != 'input_unit'),('',False)):
                with self.subTest(field=name,value=value):
                    config=config_fixture();config['signals'][0][name]=value
                    self.assertEqual(self.validators['analysis.schema.json'].is_valid(current_fixture(config)),valid)
                    definitions={key:current_fixture(config)[key] for key in ('sources','signals')}
                    self.assertEqual(self.validators['definitions.schema.json'].is_valid(current_fixture(definitions)),valid)
                    if valid:AnalysisPlan.from_dict(current_fixture(config))
                    else:
                        with self.assertRaises(PlanValidationError):AnalysisPlan.from_dict(current_fixture(config))

    def test_nullable_derived_metadata_matches_plan(self):
        """参数: 无。返回: None。异常: 派生声明误套信号的可空规则时失败。"""
        # 派生字段省略合法，显式null不合法；同名字段不能据名称推定相同合同。
        for name in ('semantic_id','semantic_contract_version','measurement_location'):
            config=config_fixture(); source=config['signals'][0]
            config.setdefault('derived',{})['manual_alias']={'expr':source['name'],'unit':source['unit']}
            self.validators['analysis.schema.json'].validate(current_fixture(config))
            AnalysisPlan.from_dict(current_fixture(config))
            config['derived']['manual_alias'][name]=None
            self.assertFalse(self.validators['analysis.schema.json'].is_valid(current_fixture(config)))
            with self.assertRaises(PlanValidationError):AnalysisPlan.from_dict(current_fixture(config))

    def test_value_map_boundaries_for_every_column(self):
        """参数: 无。返回: None。异常: 项数/键长/值长/可空的两侧结论不同即失败。"""
        # 独立列模型校验不读CAN文件；每个重复字段规范都要检查。
        props=self.documents['analysis.schema.json']['properties']
        raw=next(x for x in props['sources']['items']['oneOf'] if x['properties']['source_type'].get('const')=='raw_can_csv')
        fields=raw['properties']['reader']['properties']['layout']['properties']['fields']['properties']
        cases=[(None,True),({},False),({'0':0},True),({str(i):i for i in range(256)},True),
               ({str(i):i for i in range(257)},False),({'x'*256:0},True),({'x'*257:0},False),
               ({'x':'a'*256},True),({'x':'a'*257},False)]
        for name,field in fields.items():
            for value,valid in cases:
                with self.subTest(field=name,value_size=len(value) if value is not None else None):
                    document={'column':'raw','value_map':value}
                    self.assertEqual(Draft202012Validator(field).is_valid(current_fixture(document)),valid)
                    if valid:ColumnMapping.from_dict(document)
                    else:
                        with self.assertRaises(ValueError):ColumnMapping.from_dict(document)
            # fixed与value_map的字符串上限不同，不能共享错误限制。
            fixed={'fixed':'a'*16384}
            Draft202012Validator(field).validate(current_fixture(fixed))
            ColumnMapping.from_dict(fixed)

    def test_nullable_value_map_through_full_plan(self):
        """参数: 无。返回: None。异常: 完整CAN配置入口不接受null映射时失败。"""
        # 以真实配置结构通过规划入口，避免只验证孤立子规范。
        path=Path(__file__).resolve().parents[2]/'examples/m3_text_input/csv-plan.json'
        config=json.loads(path.read_text(encoding='utf8'))
        for item in config['sources'][0]['reader']['layout']['fields'].values():item['value_map']=None
        self.validators['analysis.schema.json'].validate(current_fixture(config))
        AnalysisPlan.from_dict(current_fixture(config),base_dir=path.parent)


if __name__=='__main__':
    unittest.main()
