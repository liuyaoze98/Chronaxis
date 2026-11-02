"""读取随包发布的合成场景模板；初始化命令与模板验收使用同一套资源。

目录中保存最小版和完整注释版YAML及小型合成输入。本模块仅提供有限模板清单
和文件内容，不创建用户目录、不执行分析、不把模板阈值当作真实设备参数。
"""
from dataclasses import dataclass
from importlib.resources import files
import json
from pathlib import PurePosixPath


@dataclass(frozen=True)
class ConfigurationTemplate:
    """可选场景及其入口；名称用于CLI选择，说明同时注明合成数据和预期行为。"""
    name: str
    title: str
    config_type: str
    entrypoint: str
    expected: str


def _catalog():
    """读取包内固定清单。参数: 无。返回: dict。异常: 缺失或损坏资源不隐藏。"""
    root=files('chronaxis.configuration').joinpath('templates')
    return root,json.loads(root.joinpath('catalog.json').read_text(encoding='utf-8'))


def available_templates():
    """列出当前所有场景。参数: 无。返回: ConfigurationTemplate tuple。异常: 包资源错误。"""
    _,catalog=_catalog()
    return tuple(ConfigurationTemplate(item['name'],item['title'],item['config_type'],
        item['entrypoint'],item['expected']) for item in catalog['templates'])


def _relative_path(text):
    """限制包内及新目录内的相对路径。参数: 文本。返回: PurePosixPath。异常: ValueError。

    清单由项目维护；仍拒绝绝对路径、返回父目录和Windows反斜线，防止资源误配越界。
    """
    path=PurePosixPath(text)
    if not text or not path.parts or '\\' in text or ':' in text or path.is_absolute() or '..' in path.parts:
        raise ValueError('模板资源必须使用目录内的相对路径')
    return path


def template_files(name,*,style='annotated'):
    """取得一个场景的完整文件集。参数: 场景名、minimal/annotated。返回: (相对路径,bytes) tuple。

    异常: 未知场景/风格为ValueError，包内文件错误直接传播；不读取用户配置或写文件。
    两种风格只有注释不同，批量子计划也按同一风格选择。资源不含环境变量或模板执行。
    """
    if style not in ('minimal','annotated'):
        raise ValueError('模板风格需要minimal或annotated')
    root,catalog=_catalog()
    match=next((item for item in catalog['templates'] if item['name']==name),None)
    if match is None:
        raise ValueError('未知配置场景：'+str(name))
    entries=[dict(source=name+'/'+style+'.yaml',target=match['entrypoint']),*match['files']]
    result=[]
    targets=set()
    for item in entries:
        source=_relative_path(item['source'].replace('{style}',style))
        target=_relative_path(item['target'])
        if target.as_posix().casefold() in targets:
            raise ValueError('模板输出路径重复：'+str(target))
        targets.add(target.as_posix().casefold())
        result.append((target.as_posix(),root.joinpath(*source.parts).read_bytes()))
    return tuple(result)
