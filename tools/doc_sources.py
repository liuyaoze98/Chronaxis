"""显式选择固定Git对象或已锁定的公开源码树供文档构建和校核读取。

默认沿用Git基线；环境变量CHRONAXIS_DOC_SOURCE_TREE=1只用于Current导出树。
源码树模式先核对运行源码和配置规范摘要，不接受缺失、漂移或隐式降级。
"""
import hashlib
import json
import os
from pathlib import Path
from runpy import run_path
import subprocess


class DocSources:
    """只读来源适配器；实例化时校验显式源码树模式的全部输入。"""

    def __init__(self, root, baseline, edition):
        """保存根目录和基线；树模式不适用或摘要漂移时抛出ValueError。"""
        self.root = Path(root)
        self.baseline = baseline
        self.tree = os.environ.get('CHRONAXIS_DOC_SOURCE_TREE') == '1'
        if self.tree:
            if edition != 'Current':
                raise ValueError('源码树模式仅适用于Current手册')
            lock = json.loads((self.root/'Docs/AI/inputs.lock.json').read_bytes())
            run_path(str(self.root/'tools/build_ai_guide.py'))['check_runtime'](lock)
            for name, digest in lock['inputs'].items():
                if name.startswith('Docs/Schema/'):
                    data = (self.root/name).read_bytes().replace(b'\r\n', b'\n')
                    if hashlib.sha256(data).hexdigest() != digest:
                        raise ValueError('规范与发行清单不一致：'+name)

    def paths(self):
        """返回排序稳定的Python模块路径；不读取未选择来源。"""
        if self.tree:
            return sorted(p.relative_to(self.root).as_posix()
                          for p in (self.root/'src/chronaxis').rglob('*.py')
                          if '__pycache__' not in p.parts)
        return subprocess.check_output(
            ['git', 'ls-tree', '-r', '--name-only', self.baseline, 'src/chronaxis'],
            cwd=self.root, text=True).splitlines()

    def text(self, relative):
        """读取源码；Windows 检出文本还原为 Git 换行，原样保存的旧模块保留字节。"""
        if self.tree:
            data = (self.root/relative).read_bytes()
            # .gitattributes 将这三份历史模块标为 -text，Git 也保留其原始换行。
            if not Path(relative).match('src/chronaxis/legacy/vendor/sclicer_functions_v1/*.py'):
                data = data.replace(b'\r\n', b'\n')
            return data.decode('utf-8-sig')
        return subprocess.check_output(
            ['git', 'show', self.baseline+':'+relative], cwd=self.root).decode('utf-8-sig')

    def revision(self):
        """返回来源标识；公开导出树不要求私有Git提交存在。"""
        if self.tree:
            return self.baseline
        return subprocess.check_output(
            ['git', 'rev-parse', self.baseline], cwd=self.root, text=True).strip()
