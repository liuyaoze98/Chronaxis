"""打包Current离线手册并核对版本、文件摘要和搬移后的本地链接。

输出写入Current/_build，解压副本保留在系统临时目录供复查；不修改手册正文。
运行前按项目规则核对设备，并通过CHRONAXIS_DEVICE_LABEL传入实际来源标签。
"""
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from zipfile import ZipFile
from build_ai_guide import build as build_ai_guide
from english_docs import check_reviewed


def hashes(folder, *, exclude_cache=False):
    """参数: folder为目录，exclude_cache控制排除源示例缓存。返回相对路径摘要；读取错误传播。"""
    return {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in folder.rglob('*') if p.is_file() and
            (not exclude_cache or ('__pycache__' not in p.relative_to(folder).parts and p.suffix != '.pyc'))}


def main():
    """参数: 无。返回: None。异常: 版本/内容差异或检查失败时中止，不报告交付成功。"""
    repo = Path(__file__).resolve().parents[1]
    docs = repo / 'Docs/Current'
    build = docs / '_build'
    html = build / 'html'
    label = os.environ['CHRONAXIS_DEVICE_LABEL']
    assert label in ('home', 'work'), '必须传入已实测的设备标签'

    # 生成页、源码清单、随附配置规范必须属于同一交付内容。
    metadata = json.loads((docs / 'documentation.json').read_text(encoding='utf8'))
    baseline = metadata['baseline']
    check_reviewed()
    english_digest = hashlib.sha256((docs / 'en/translation-status.json').read_bytes()).hexdigest()
    if json.loads((html / 'build-manifest.json').read_bytes())['englishReview'] != english_digest:
        raise ValueError('英文明细或来源已变化；请重建双语HTML。')
    # 发布前从受审核的原始资料重建一次；不让旧ZIP跟着新版手册完成发布。
    if (html / 'Chronaxis-AI.zip').read_bytes() != build_ai_guide(verify_runtime=False):
        raise ValueError('用户AI资料已过期；请先重建Current HTML。')
    # 直接阅读目录与可选压缩副本逐文件相同，不让页面仍只依赖ZIP入口。
    with ZipFile(html / 'Chronaxis-AI.zip') as guide:
        assert set(hashes(html / 'ai-guide')) == set(guide.namelist())
        for name in guide.namelist():
            assert (html / 'ai-guide' / name).read_bytes() == guide.read(name), name
    for path in (docs / 'reference/inventory.json', html / 'documentation.json',
                 html / 'build-manifest.json', html / 'reference/inventory.json'):
        assert json.loads(path.read_text(encoding='utf8'))['baseline'] == baseline, path
    for name in ('documentation.json', 'public-api.json', 'navigation.json', 'reference/inventory.json'):
        assert (docs / name).read_bytes() == (html / name).read_bytes(), name
    for source in (repo / 'Docs/Schema').glob('*.json'):
        assert source.read_bytes() == (html / 'attachments/Docs/Schema' / source.name).read_bytes(), source
    assert hashes(docs / 'examples',exclude_cache=True) == hashes(html / 'examples'), '随册示例不一致'
    caches=[str(p.relative_to(html)) for p in html.rglob('*') if p.name=='__pycache__' or p.suffix=='.pyc']
    assert not caches, ('交付目录包含Python缓存',caches)

    # 哈希在打包前后及独立解压目录三方比较，检测打包期间的文件变化。
    expected = hashes(html)
    archive = Path(shutil.make_archive(str(build / 'Chronaxis-Manual'), 'zip', html))
    relocated = Path(tempfile.mkdtemp(prefix='chronaxis-offline-'))
    shutil.unpack_archive(archive, relocated)
    assert expected == hashes(html) == hashes(relocated), 'ZIP与页面文件不一致'
    check = subprocess.run([sys.executable, '-B', str(repo / 'tools/check_current_html.py'),
                            '--root', str(relocated)], capture_output=True, text=True, encoding='utf8')
    assert check.returncode == 0, (check.stdout, check.stderr)

    # 报告明确区分静态检查和实际浏览器操作；记录ZIP摘要便于确认下载的是本版。
    report = {
        'device_label': label,
        'checked_at': datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds'),
        'baseline': baseline, 'archive': str(archive), 'bytes': archive.stat().st_size,
        'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
        'relocated_directory': str(relocated), 'files': len(expected),
        'file_hashes_equal': True, 'static_check': check.stdout,
        'browser': 'not_verified',
    }
    (build / 'offline-verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
