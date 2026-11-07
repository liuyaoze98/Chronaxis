"""从明确的产品基线取得根导出和公开子模块的真实Python签名。

临时目录展开同一基线的src及pyproject版本，子进程只导入声明；不读取业务日志。未知根导出必须先补分组，
不能静默遗漏。源码树发行模式复用已经由DocSources校验的当前src。
"""
import argparse
import importlib
import inspect
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
EXTRA = (
    ('fast.run', 'chronaxis.fast', 'run', '高性能积分器'),
    ('fast.batch.run_batch', 'chronaxis.fast.batch', 'run_batch', '高性能积分器'),
    ('ExtensionRegistry', 'chronaxis.extensions', 'ExtensionRegistry', '宿主扩展'),
    ('FunctionSpec', 'chronaxis.extensions', 'FunctionSpec', '宿主扩展'),
    ('ReductionSpec', 'chronaxis.extensions', 'ReductionSpec', '宿主扩展'),
    ('TransformSpec', 'chronaxis.extensions', 'TransformSpec', '宿主扩展'),
)


def collect(source, previous):
    """在独立进程读取选定src。返回清单；缺少分组或符号时明确失败。"""
    sys.path.insert(0, str(source))
    package = importlib.import_module('chronaxis')
    old = {row['name']: row for row in previous['objects']}
    declarations = [(name, 'chronaxis', name, old[name]['group']) for name in package.__all__]
    rows = []
    for name, module, symbol, group in (*declarations, *EXTRA):
        obj = getattr(importlib.import_module(module), symbol)
        parameters = []
        try:
            spec = inspect.signature(obj)
            signature = str(spec)
            for parameter in spec.parameters.values():
                parameters.append(dict(name=parameter.name, kind=parameter.kind.name,
                                       type=inspect.formatannotation(parameter.annotation) if parameter.annotation is not inspect.Parameter.empty else '',
                                       required=parameter.default is inspect.Parameter.empty and parameter.kind not in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD),
                                       default=None if parameter.default is inspect.Parameter.empty else repr(parameter.default)))
        except ValueError:
            if not inspect.isclass(obj) or not issubclass(obj, BaseException):
                raise
            # 内置异常继承签名没有可反射的参数；不编造构造参数。
            signature = None
        rows.append(dict(name=name, import_module=module, import_name=symbol,
                         module=obj.__module__, qualified=obj.__qualname__,
                         group=group, kind='class' if inspect.isclass(obj) else 'function',
                         signature=signature, parameters=parameters,
                         target=f'public-api/{name}.md#api-{obj.__qualname__.replace(".", "-")}'))
    return rows


def refresh(root, baseline, *, source_tree=False):
    """显式基线生成清单。只更新Current/public-api.json，不刷新基线或输入锁。"""
    root = Path(root)
    target = root / 'Docs/Current/public-api.json'
    previous = json.loads(target.read_bytes())
    with TemporaryDirectory(prefix='chronaxis-public-api-') as temporary:
        temp = Path(temporary)
        if source_tree:
            source = root / 'src'
        else:
            # 反射的默认软件版本必须来自同一冻结提交，不能借用当前工作区的pyproject。
            archive = subprocess.check_output(['git', 'archive', baseline, 'src', 'pyproject.toml'], cwd=root)
            with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
                stream.extractall(temp, filter='data')
            source = temp / 'src'
        result = subprocess.check_output([sys.executable, '-X', 'utf8', '-B', '-I', str(Path(__file__).resolve()),
                                          '--collect', str(source), '--previous', str(target)], cwd=root)
    previous['objects'] = json.loads(result)
    previous['baseline'] = baseline
    metadata = json.loads((root/'Docs/Current/documentation.json').read_bytes())
    for key in ('updated_at', 'device_label'):
        previous[key] = metadata[key]
    target.write_text(json.dumps(previous, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    return previous


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--collect')
    parser.add_argument('--previous')
    parser.add_argument('--baseline')
    args = parser.parse_args()
    if args.collect:
        print(json.dumps(collect(Path(args.collect), json.loads(Path(args.previous).read_bytes())), ensure_ascii=False))
    elif args.baseline:
        refresh(ROOT, args.baseline)
    else:
        parser.error('Specify --baseline, or internal --collect with --previous')
