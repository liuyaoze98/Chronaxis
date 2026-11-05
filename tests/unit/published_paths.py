"""从公开返回值定位本次导出文件，避免测试依赖固定文件名或扫描旧目录。"""
from pathlib import Path
import json


def published_file(result, logical_name):
    """按本次清单找到指定逻辑表。参数: 返回清单/旧逻辑名。返回: Path。异常: 缺项或重名。"""
    if logical_name in ('manifest.json', 'run_manifest.json'):
        return result.manifest_path
    name = Path(logical_name)
    matches = [p for p in result.output_files if p.name.startswith(name.stem + '_') and p.suffix == name.suffix]
    if len(matches) != 1:
        raise AssertionError((logical_name, result.output_files))
    return matches[0]


def export_root(result):
    """读取本次清单中的导出目录。参数: OutputManifest。返回: Path。异常: 原IO/缺项。"""
    document = json.loads(result.manifest_path.read_text(encoding='utf-8'))
    return result.output_dir / document['exports']['directory']
