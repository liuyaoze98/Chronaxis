"""回归J19—J21的成品定位与字节规则。

以小型内存文件映射复现错误目录、坏JSON Pointer、丢失宿主链接和换行漂移。
不运行业务分析或写文件；最终完整分发另由交付流程遍历。
"""
from copy import deepcopy
from hashlib import sha256
import json
import unittest

from ai_resource_bytes import resource_bytes
from build_ai_guide import public_card, validate_api_links, validate_field_references
from example_inventory import INPUT_DIGEST_POLICY, configuration_hash, validate_example_inventory


def fields_fixture():
    """构造双语字段指针。参数: 无。返回: bytes映射。异常: 无。"""
    files = {'schemas/a.json': json.dumps({'properties': {'a/b~c': {'type': 'integer'}}, 'allOf': [{}]}).encode()}
    for language in ('', 'en/'):
        root = '../' if language else ''
        ref = root + 'schemas/a.json#/properties/a~1b~0c'
        files[language+'fields/a/one.json'] = json.dumps({'original':ref,'fields':[{
            'source':ref,'conditions':[root+'schemas/a.json#/allOf/0']}]}).encode()
    return files


def inventory_fixture():
    """构造同时使用语义和字节摘要的清单。参数: 无。返回: 文件映射。异常: 无。"""
    config=b'name: example\n'; data=b't,v\r\n0,1\r\n'; result=b'value\r\n1\r\n'
    index={'inputs':{'a.yaml':configuration_hash(config),'data/a.csv':sha256(data).hexdigest()},
           'files':{'one/result.csv':sha256(result).hexdigest()},'input_digest_policy':INPUT_DIGEST_POLICY}
    return {'examples/a.yaml':config,'examples/data/a.csv':data,'examples/results/one/result.csv':result,
            'examples/results/index.json':json.dumps(index).encode()}


class ManualGenerationJ(unittest.TestCase):
    """检查源生成器确实拒绝原故障，而非只核外层ZIP摘要。"""

    def test_every_field_reference_in_both_languages(self):
        """参数: 无。返回: None。异常: 断言失败；含转义键和数组定位。"""
        files=fields_fixture()
        self.assertEqual(validate_field_references(files),6)
        page=json.loads(files['en/fields/a/one.json']); page['original']=page['original'].removeprefix('../')
        files['en/fields/a/one.json']=json.dumps(page).encode()
        with self.assertRaisesRegex(ValueError,'定位无效'):
            validate_field_references(files)

    def test_existing_file_with_broken_pointer_is_rejected(self):
        """参数: 无。返回: None。异常: 断言失败；文件存在不代表片段有效。"""
        for index in ('9', '-1', '00', '+0'):
            with self.subTest(index=index):
                files=fields_fixture();page=json.loads(files['fields/a/one.json'])
                page['fields'][0]['conditions']=['schemas/a.json#/allOf/'+index]
                files['fields/a/one.json']=json.dumps(page).encode()
                with self.assertRaisesRegex(ValueError,'JSON Pointer'):
                    validate_field_references(files)

    def test_host_links_from_each_card_reach_program_and_configuration(self):
        """参数: 无。返回: None。异常: 断言失败；卡片位置与命令起点分开。"""
        source='<a id="api-X"></a>\n[完整宿主示例](../host-extensions.md)\n[函数](X.md#api-X)\n'
        files={'examples/temporal/host_extensions.py':b'pass','examples/temporal/host-analysis.yaml':b'a: 1'}
        for language in ('','en/'):
            files[language+'api/X.md']=public_card(source,language=language,api_names=['X']).encode()
        self.assertEqual(validate_api_links(files),6)
        del files['examples/temporal/host-analysis.yaml']
        with self.assertRaisesRegex(ValueError,'缺少随包文件'):
            validate_api_links(files)

    def test_known_internal_type_keeps_nested_type_text(self):
        """参数: 无。返回: None。异常: 断言失败；类型括号不能被链接转换吞掉。"""
        text=public_card('<a id="api-X"></a>\n`tuple[[Item](../reference/internal.md), ...]`')
        self.assertIn('tuple[Item, ...]',text)

    def test_configuration_formatting_does_not_change_semantic_digest(self):
        """参数: 无。返回: None。异常: 断言失败；业务值变化仍拒绝。"""
        files=inventory_fixture();files['examples/a.yaml']=b'# note\r\nname: example\r\n'
        self.assertEqual(validate_example_inventory(files),{'inputs':2,'configurations':1,'results':1})
        files['examples/a.yaml']=b'name: changed\n'
        with self.assertRaisesRegex(ValueError,'摘要不符'):
            validate_example_inventory(files)

    def test_raw_input_newlines_are_preserved_and_verified(self):
        """参数: 无。返回: None。异常: 断言失败；结果和输入都使用实际字节。"""
        files=inventory_fixture();original=files['examples/data/a.csv']
        self.assertEqual(resource_bytes('Docs/Current/examples/data/a.csv',original),original)
        self.assertEqual(resource_bytes('Docs/Current/examples/power.csv',original),original)
        for name in ('fast/data/power.dbc', 'fast/data/run2.asc', 'temporal/meter.asc', 'temporal/meter.dbc'):
            self.assertEqual(resource_bytes('Docs/Current/examples/'+name,original),original)
        changed=deepcopy(files);changed['examples/data/a.csv']=original.replace(b'\r\n',b'\n')
        with self.assertRaisesRegex(ValueError,'摘要不符'):
            validate_example_inventory(changed)
        changed=deepcopy(files);changed['examples/results/one/result.csv']=b'value\n1\n'
        with self.assertRaisesRegex(ValueError,'摘要不符'):
            validate_example_inventory(changed)


if __name__=='__main__':
    unittest.main()
