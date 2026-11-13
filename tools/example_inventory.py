"""核验最终教学资源中的输入与结果摘要，供源码和手册打包共用。

配置按解析后的JSON值计算语义摘要；其他输入及结果按交付原字节计算SHA256。
只读取调用者提供的文件映射，不运行分析，不修改摘要来掩盖内容变化。
"""
from hashlib import sha256
import json
from pathlib import PurePosixPath

from ruamel.yaml import YAML


INPUT_DIGEST_POLICY = {
    'configuration': 'SHA256 of UTF-8 json.dumps(safe YAML value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False); .yaml and .json inputs only',
    'other_inputs': 'SHA256 of delivered file bytes without encoding or newline conversion',
}


def configuration_hash(data):
    """计算配置语义摘要。参数: UTF-8配置bytes。返回: SHA256。异常: 解析错误或非映射。"""
    value = YAML(typ='safe').load(data.decode('utf-8-sig'))
    if not isinstance(value, dict):
        raise ValueError('教学配置必须是映射')
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return sha256(text.encode('utf8')).hexdigest()


def validate_example_inventory(files):
    """逐项检查最终交付的教学清单。

    参数: files为相对于手册根的路径到原始bytes映射。返回: 输入/配置/结果检查数量。
    异常: ValueError表示路径、摘要算法或文件内容与清单不符；只读内存。
    """
    inventory = json.loads(files['examples/results/index.json'])
    if inventory.get('input_digest_policy') != INPUT_DIGEST_POLICY:
        raise ValueError('教学输入清单缺少当前摘要算法说明')
    configurations = inputs = results = 0
    for group, prefix in (('inputs', 'examples/'), ('files', 'examples/results/')):
        for relative, expected in inventory[group].items():
            path = PurePosixPath(relative)
            if path.is_absolute() or '..' in path.parts or '\\' in relative or ':' in relative:
                raise ValueError('教学清单路径无效：' + relative)
            destination = prefix + relative
            if destination not in files:
                raise ValueError('教学清单文件缺失：' + destination)
            data = files[destination]
            if group == 'inputs' and path.suffix in ('.yaml', '.json'):
                actual = configuration_hash(data)
                configurations += 1
            else:
                actual = sha256(data).hexdigest()
            if actual != expected:
                raise ValueError('教学清单摘要不符：' + destination)
            if group == 'inputs':
                inputs += 1
            else:
                results += 1
    return dict(inputs=inputs, configurations=configurations, results=results)
