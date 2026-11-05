"""验证当前格式门禁与已撤下的旧入口，不读取业务数据或写入文件。

输入使用最小格式标识和CLI参数；旧版本与INI映射必须拒绝，批量版本独立保留。
"""
import contextlib
import io
import json
from pathlib import Path
import unittest

from chronaxis.cli import _parser
from chronaxis.configuration.file_tools import configuration_type


class CurrentConfigurationOnlyTests(unittest.TestCase):
    """对照独立预期检查入口，没有使用自动迁移或静默回退。"""

    def test_current_and_batch_versions(self):
        """参数无；返回无；门禁未按当前约定接受时断言失败。"""
        self.assertEqual(configuration_type({'config_version': 4}), 'analysis')
        self.assertEqual(configuration_type({'batch_version': 1}), 'batch')
        for value in (3, 2, True, '4', 4.0, None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                configuration_type({'config_version': value})

    def test_old_mapping_and_command_rejected(self):
        """参数无；返回无；旧格式或CLI被接收时断言失败，不创建文件。"""
        with self.assertRaises(ValueError):
            configuration_type({'mapping_version': 1, 'analysis': {'config_version': 4}})
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            _parser().parse_args(['legacy', 'import'])
        self.assertEqual(error.exception.code, 2)

    def test_schema_matches_current_contract(self):
        """参数无；返回无；规范未限制当前值或仍给错误自动系数默认时失败。"""
        root = Path(__file__).resolve().parents[2]
        schema = json.loads((root / 'Docs/Schema/analysis.schema.json').read_bytes())
        self.assertEqual(schema['properties']['config_version']['const'], 4)
        conversion = schema['properties']['signals']['items']['oneOf'][0]['properties']['conversion']['properties']
        self.assertEqual(conversion['input_unit']['type'], 'string')
        self.assertNotIn('default', conversion['scale'])
        self.assertNotIn('default', conversion['offset'])
