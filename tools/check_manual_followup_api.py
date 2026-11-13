"""从最终手册和独立AI包提取共享注册实例例，按各自目录原样执行。

输入为HTML目录、AI ZIP、已安装对应发行版的Python和全新证据目录。
不改写示例代码，不借用仓库示例；只执行加载、校验和解释，不运行分析。
输出四份调用结果及JSON摘要；资料缺失、重复片段或结果不符即失败。
"""

import argparse
from datetime import datetime, timezone, timedelta
from hashlib import sha256
from html.parser import HTMLParser
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from zipfile import ZipFile


class PythonBlocks(HTMLParser):
    """提取渲染后的Python代码，解码实体并去除高亮span，不改变文本内容。"""

    def __init__(self):
        """参数: 无。返回: 无。异常: 无；结果保存在blocks中。"""
        super().__init__(convert_charrefs=True)
        self.blocks = []
        self.pre = False
        self.current = None

    def handle_starttag(self, tag, attrs):
        """参数: HTML标签和属性。返回: 无。异常: 无；只选pre中的Python代码。"""
        if tag == 'pre':
            self.pre = True
        if tag == 'code' and self.pre:
            classes = dict(attrs).get('class', '').split()
            if 'language-python' in classes:
                self.current = []

    def handle_data(self, data):
        """参数: 解码后的文本。返回: 无。异常: 无；代码围栏外的文本忽略。"""
        if self.current is not None:
            self.current.append(data)

    def handle_endtag(self, tag):
        """参数: 结束标签。返回: 无。异常: 无；保留代码中的换行及空白。"""
        if tag == 'code' and self.current is not None:
            self.blocks.append(''.join(self.current))
            self.current = None
        if tag == 'pre':
            self.pre = False


def registry_fragment(text, *, html=False):
    """选择完整共享实例片段，不重组其代码。

    参数: HTML或Markdown文本及格式标志。返回: 原样代码文本。
    异常: ValueError表示缺失或重复片段，不能静默挑选可能过时的一个。
    """
    if html:
        parser = PythonBlocks()
        parser.feed(text)
        parser.close()
        blocks = parser.blocks
    else:
        blocks = re.findall(r'^```python\r?\n(.*?)^```\s*$', text, re.M | re.S)
    selected = [block for block in blocks if all(marker in block for marker in (
        'registry = ExtensionRegistry()', 'extensions=registry',
        'runner.validate(plan)', 'runner.explain(plan)'))]
    if len(selected) != 1:
        raise ValueError(f'共享注册实例的完整片段应恰好一个，实际{len(selected)}个')
    return selected[0]


def execute_fragment(python, code, cwd):
    """在指定目录用已安装包执行原片段；不追加导入、路径修复或替代断言。

    参数: Python路径、代码、工作目录。返回: 退出码、输出、原片段摘要及是否通过。
    异常: 启动或超时错误传播；代码失败保留原错误，不把检查失败转成通过。
    """
    completed = subprocess.run([str(python), '-I', '-B', '-X', 'utf8', '-c', code],
                               cwd=cwd, capture_output=True, text=True,
                               encoding='utf-8', timeout=60)
    return {'cwd': str(cwd), 'code_sha256': sha256(code.encode('utf-8')).hexdigest(),
            'exit_code': completed.returncode, 'stdout': completed.stdout,
            'stderr': completed.stderr,
            'passed': completed.returncode == 0 and
            completed.stdout.splitlines() == ['True True', 'ExplainReport']}


def unpack_guide(archive, destination):
    """将独立AI包解到全新证据子目录，保留原始字节供相对路径调用。

    参数: ZIP路径及新目录。返回: 无。异常: 非法或重复相对路径拒绝；I/O错误传播。
    """
    destination.mkdir()
    seen = set()
    with ZipFile(archive) as package:
        for item in package.infolist():
            path = PurePosixPath(item.filename)
            key = path.as_posix().casefold()
            if path.is_absolute() or '..' in path.parts or ':' in item.filename or '\\' in item.filename:
                raise ValueError('AI包路径不在解压目录内：' + item.filename)
            if key in seen:
                raise ValueError('AI包路径重复：' + item.filename)
            seen.add(key)
            target = destination.joinpath(*path.parts)
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(package.read(item))


def main():
    """解析输入并验证四份成品代码。返回: 退出码。异常: 无效输入及I/O错误传播。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manual-root', required=True, type=Path)
    parser.add_argument('--ai-zip', required=True, type=Path)
    parser.add_argument('--work-dir', required=True, type=Path)
    parser.add_argument('--python', default=sys.executable, type=Path)
    parser.add_argument('--device-label', required=True)
    args = parser.parse_args()
    manual = args.manual_root.resolve()
    archive = args.ai_zip.resolve()
    work = args.work_dir.resolve()
    python = args.python.resolve()
    work.mkdir(parents=True, exist_ok=False)
    guide = work/'ai-guide'
    unpack_guide(archive, guide)
    checks = {}
    for name, path, cwd, is_html in (
        ('html_zh', manual/'public-api/AnalysisRunner.html', manual, True),
        ('html_en', manual/'en/public-api/AnalysisRunner.html', manual, True),
        ('ai_zh', guide/'api/AnalysisRunner.md', guide, False),
        ('ai_en', guide/'en/api/AnalysisRunner.md', guide/'en', False),
    ):
        try:
            code = registry_fragment(path.read_text(encoding='utf-8'), html=is_html)
            result = execute_fragment(python, code, cwd)
            (work/(name+'.py')).write_text(code, encoding='utf-8')
        except Exception as exc:
            result = {'passed': False, 'error_type': type(exc).__name__, 'error': str(exc)}
        checks[name] = dict(source=str(path), **result)
    report = {'device_label': args.device_label, 'author': 'liuyaoze',
              'checked_at': datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds'),
              'manual_root': str(manual), 'ai_zip': str(archive),
              'ai_zip_sha256': sha256(archive.read_bytes()).hexdigest(),
              'python': str(python), 'checks': checks,
              'passed': all(row['passed'] for row in checks.values())}
    target = work/'api-fragments.json'
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'passed': report['passed'], 'checks': len(checks),
                      'report': str(target)}, ensure_ascii=False))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
