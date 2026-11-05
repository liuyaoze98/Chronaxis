"""从单次测试输出的完成清单取得实际文件路径。

旧测试仍按逻辑表名指定要核对的结果，此辅助函数只读取测试专用目录中唯一的
完成清单，不按时间挑最新文件。多次输出测试必须直接使用API返回值，不能使用此函数。
"""

import json
from pathlib import Path


def published_path(logical_path):
    """解析单次输出路径。参数: 旧逻辑Path。返回: 实际Path。异常: 缺失/多清单/多候选。"""
    path = Path(logical_path)
    prefix = 'batch_report_' if path.name == 'batch_report.json' else 'run_manifest_'
    manifests = tuple(path.parent.glob(prefix + '*.json'))
    if len(manifests) != 1:
        raise AssertionError(f'测试需要唯一完成清单：{path.parent}，实际{len(manifests)}')
    if path.name in ('batch_report.json', 'run_manifest.json'):
        return manifests[0]
    # 候选来自完成清单，不扫描旧数据表或读取其内容。
    document = json.loads(manifests[0].read_text(encoding='utf-8'))
    names = [item['name'] for item in document['outputs']
             if item['name'].startswith(path.stem + '_')
             and item['name'].endswith(path.suffix)]
    if len(names) != 1:
        raise AssertionError(f'清单中{path.name}应恰有一个实际文件：{names}')
    return path.parent / names[0]
