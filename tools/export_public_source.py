"""从已提交版本白名单导出独立公开源码，不带入内部Git历史或工作区文件。

公开Markdown去除末尾开发履历；随后只更新被明确转换的指南输入摘要。
不修改源仓库、运行代码或运行源码摘要。目标必须不存在，输出可供人工审阅。
"""
import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import subprocess
from zipfile import ZipFile
from public_docs import reading_text

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_TESTS = {
    'test_acceptance_configuration_tools.py', 'test_asc_repository.py',
    'test_current_tool_entrypoints.py', 'test_energy_pipeline_profiler.py',
    'test_legacy_energy_benchmark_tool.py', 'test_measurement_current_results.py',
    'test_real_energy_acceptance_execution.py', 'test_real_energy_acceptance_time.py',
    'test_ten_file_energy_driver.py',
}
PUBLIC_TOOLS = {
    'build_ai_guide.py', 'ai_field_views.py', 'english_docs.py', 'public_docs.py', 'doc_sources.py',
    'build_m2_docs.py', 'doc_type_links.py', 'doc_public_api.py', 'verify_m2_docs.py',
    'render_m2_docs.mjs', 'render_current_docs.mjs', 'manual_search.js',
    'check_current_html.py', 'test_manual_search.mjs', 'package_current_docs.py',
    'check_ai_install.py', 'verify_ai_distribution.py', 'lock_ai_inputs.py',
    'test_public_docs.py', 'test_doc_sources.py', 'test_docs_reference.py', 'test_current_html.py',
    'test_manual_example_comments.py', 'test_manual_r2.py',
    'export_public_source.py', 'pypi_readme.py',
}


def included(name):
    """检查提交内的相对文件名；默认排除未列入的目录和工具。"""
    p = Path(name)
    if any(part in {'_build', '__pycache__', '.git'} for part in p.parts):
        return False
    if '冲突副本' in name or p.suffix in {'.pyc', '.7z'}:
        return False
    if name in {'README.md', 'README.en.md', 'LICENSE', 'pyproject.toml', 'setup.py', 'MANIFEST.in', '.gitattributes'}:
        return True
    if name == '.github/workflows/pypi-publish.yml':
        return True
    if name.startswith(('src/chronaxis/', 'examples/', 'tests/fixtures/',
                        'Docs/Current/', 'Docs/AI/', 'Docs/Schema/', 'Docs/Release/')):
        return True
    if name.startswith('tests/unit/'):
        return p.name not in EXCLUDED_TESTS
    if name.startswith('tests/ai_release/'):
        return p.name in {'check_bundle.py', 'check_behavior.py'}
    return name.startswith('tools/') and p.name in PUBLIC_TOOLS


def export(destination, revision='HEAD'):
    """创建新导出目录及清单；源仓库不变，缺文件或转换前摘要不匹配即失败。"""
    destination = Path(destination).resolve()
    if destination.exists() or 'RefProjects' in destination.parts:
        raise ValueError('导出目标必须是不存在的独立目录，且不能位于历史项目中')
    revision = subprocess.check_output(['git', 'rev-parse', revision+'^{commit}'], cwd=ROOT, text=True).strip()
    paths = ['src', 'tests', 'examples', 'tools', 'Docs/Current', 'Docs/AI',
             'Docs/Schema', 'Docs/Release', 'README.md', 'README.en.md', 'LICENSE',
             'pyproject.toml', 'setup.py', 'MANIFEST.in', '.gitattributes']
    # 旧提交可能尚无发布工作流；只导出该版本实际存在的明确文件。
    workflow = '.github/workflows/pypi-publish.yml'
    if subprocess.check_output(['git', 'ls-tree', '--name-only', revision, '--', workflow], cwd=ROOT).strip():
        paths.append(workflow)
    data = subprocess.check_output(['git', 'archive', '--format=zip', revision, *paths], cwd=ROOT)
    files = {}
    with ZipFile(BytesIO(data)) as archive:
        for item in archive.infolist():
            if not item.is_dir() and included(item.filename):
                files[item.filename] = archive.read(item)
    lock = json.loads(files['Docs/AI/inputs.lock.json'])
    # 先核输入确属已审核版本；公开正文转换不能掩盖原始资料漂移。
    for name, digest in lock['inputs'].items():
        original = files[name].replace(b'\r\n', b'\n')
        if sha256(original).hexdigest() != digest:
            raise ValueError('提交中的指南输入与锁不符：'+name)
    transformed = []
    for name, content in tuple(files.items()):
        if name.startswith(('Docs/Current/', 'Docs/AI/')) and name.endswith('.md'):
            public = reading_text(content.decode('utf8')).encode('utf8')
            if public != content:
                files[name] = public
                transformed.append(name)
    for name in lock['inputs']:
        lock['inputs'][name] = sha256(files[name].replace(b'\r\n', b'\n')).hexdigest()
    files['Docs/AI/inputs.lock.json'] = (json.dumps(lock, indent=2)+'\n').encode()
    files['.gitignore'] = b'__pycache__/\n*.py[cod]\n.venv/\nwork/\nbuild/\ndist/\n*.egg-info/\nDocs/Current/_build/\n'
    # 所有路径来自Git受审白名单，仍核对最终目标避免意外越界。
    destination.mkdir(parents=True)
    for name, content in files.items():
        target = destination/name
        if not target.resolve().is_relative_to(destination):
            raise ValueError('非法公开成员路径：'+name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    manifest = dict(source_revision=revision, author='liuyaoze',
                    transformed_markdown=transformed, excluded_internal_tests=sorted(EXCLUDED_TESTS),
                    files={name: sha256(content).hexdigest() for name, content in sorted(files.items())})
    (destination/'PUBLIC-SOURCE.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    return dict(directory=str(destination), files=len(files), transformed_markdown=len(transformed), revision=revision)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--revision', default='HEAD')
    args = parser.parse_args()
    print(json.dumps(export(args.destination, args.revision), ensure_ascii=False))
