"""核对 DOC-REVIEW-11 的规范说明与字段视图，避免正文正确而派生卡片残留。

在内存展开 analysis/definitions 的本地引用并翻译说明，不生成交付文件。
配置探测只加载教学 DBC，不运行分析、不读取报文或创建工作目录。
运行时将 src 加入 PYTHONPATH，并使用 -B，避免生成字节码缓存。
"""

from copy import deepcopy
import json
from pathlib import Path
from runpy import run_path
import unittest

from chronaxis import AnalysisPlan, validate_analysis_plan


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / 'Docs/Current/examples'


def schemas():
    """返回当前三份规范的解析值；只读 JSON，格式错误直接传播。"""
    return {name: json.loads((ROOT / 'Docs/Schema' / name).read_text(encoding='utf-8'))
            for name in ('analysis.schema.json', 'batch-v1.schema.json',
                         'definitions.schema.json')}


def configuration():
    """返回无 domain 的纯 BLF 串行积分声明；调用者可独立修改这个新字典。"""
    return {
        'config_version': 4,
        'dataset': {'name': 'scope_probe'},
        'sources': [{'paths': 'data/power.blf',
                     'dbc_by_channel': {'1': 'data/power.dbc'},
                     'reader': {'decode_scope': 'all', 'decode_policy': 'strict'}}],
        'signals': [{'name': 'power', 'field': {'frame_id': 256, 'signal': 'Power'},
                     'valid_for': '1s'}],
        'calculations': [{'name': 'energy', 'operation': 'integral',
                          'expr': 'power', 'unit': 'J'}],
        'execution': {'process_count': 1},
    }


class FollowupFieldTests(unittest.TestCase):
    """把中英字段说明对应到引用展开结果和既有配置行为。"""

    def test_descriptions_reach_both_schema_field_views(self):
        """analysis 与 definitions 的每个来源/信号分支都必须取得修正后的说明。"""
        original = schemas()
        translations = json.loads((ROOT / 'Docs/Current/en/schema-translations.json')
                                  .read_text(encoding='utf-8'))['translations']
        translate = run_path(str(ROOT / 'tools/english_docs.py'))['translate_schema']
        fields_for = run_path(str(ROOT / 'tools/ai_field_views.py'))['fields_for']
        english = {name: translate(schema, translations)
                   for name, schema in original.items()}
        for language, collection in (('zh', original), ('en', english)):
            for document in ('analysis.schema.json', 'definitions.schema.json'):
                with self.subTest(language=language, document=document):
                    rows = list(fields_for(collection, document, '',
                                           collection[document], '', None))
                    scopes = [row for row in rows
                              if row['path'] == 'sources.reader.decode_scope']
                    self.assertEqual(len(scopes), 2)
                    for row in scopes:
                        details = row['constraints']
                        self.assertEqual(details['default'], 'requested')
                        self.assertEqual(details['enum'], ['all', 'requested'])
                        text = details['description']
                        for token in ('strict/partial', 'dataset.domain', 'time_order'):
                            self.assertIn(token, text)
                        self.assertIn('不保证' if language == 'zh' else 'does not guarantee', text)
                        self.assertIn('本身不要求' if language == 'zh' else 'does not itself require', text)
                        self.assertIn('对纯BLF串行接续，strict/partial' if language == 'zh'
                                      else 'In serial pure-BLF concatenation, strict/partial', text)
                        self.assertNotIn('all用于纯BLF', text)
                    versions = [row for row in rows if row['path'] in (
                        'signals.semantic_contract_version',
                        'signals.signals.semantic_contract_version')]
                    self.assertEqual(len(versions), 2)
                    for row in versions:
                        text = row['constraints']['description']
                        self.assertIn('semantic_id', text)
                        self.assertIn('任意非null值' if language == 'zh' else 'every non-null value', text)

    def test_all_without_domain_retains_existing_process_rules(self):
        """all 不强制 domain，但文件并行与时间归并仍须 requested。"""
        for policy in ('strict', 'partial'):
            raw = configuration()
            raw['sources'][0]['reader']['decode_policy'] = policy
            with self.subTest(policy=policy, execution='serial'):
                report = validate_analysis_plan(AnalysisPlan.from_dict(raw, base_dir=EXAMPLES))
                self.assertTrue(report.valid)
            parallel = deepcopy(raw)
            parallel['execution']['process_count'] = 4
            merged = deepcopy(raw)
            merged['sources'][0]['file_merge'] = 'time_order'
            for modified in (parallel, merged):
                with self.subTest(policy=policy, execution=modified['execution'],
                                  merge=modified['sources'][0].get('file_merge')):
                    report = validate_analysis_plan(AnalysisPlan.from_dict(modified, base_dir=EXAMPLES))
                    self.assertFalse(report.valid)

    def test_signal_version_dependency_in_both_declaration_forms(self):
        """普通信号及报文组子信号均按已有联填规则处理任意非空版本。"""
        for grouped in (False, True):
            for version in ('1', '2', 'lab-contract'):
                raw = configuration()
                if grouped:
                    raw['signals'] = [{'frame_id': 256, 'valid_for': '1s',
                                       'signals': [{'name': 'power', 'signal': 'Power'}]}]
                    signal = raw['signals'][0]['signals'][0]
                else:
                    signal = raw['signals'][0]
                signal['semantic_contract_version'] = version
                with self.subTest(grouped=grouped, version=version):
                    with self.assertRaisesRegex(ValueError, 'semantic_contract_version需要semantic_id'):
                        AnalysisPlan.from_dict(raw, base_dir=EXAMPLES)
                    signal['semantic_id'] = 'example.power'
                    AnalysisPlan.from_dict(raw, base_dir=EXAMPLES)
                    signal['semantic_id'] = None
                    signal['semantic_contract_version'] = None
                    AnalysisPlan.from_dict(raw, base_dir=EXAMPLES)

    def test_definitions_version_and_derived_metadata_stay_distinct(self):
        """公共定义说明当前版本；不把信号联填说明添加到独立的派生元数据。"""
        documents = schemas()
        self.assertIn('config_version: 4', documents['definitions.schema.json']['description'])
        derived = documents['analysis.schema.json']['properties']['derived']
        self.assertEqual(derived['additionalProperties']['properties']
                         ['semantic_contract_version']['description'],
                         '该语义契约的版本，与分析配置版本独立；不表示实际输入已核验。')


if __name__ == '__main__':
    unittest.main()
