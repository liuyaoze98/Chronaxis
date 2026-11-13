"""统一AI资料锁与构建器的文件字节规则，并校核教学结果的内层摘要。

说明文本允许统一换行；教学数据和已有字节摘要的结果目录必须原样保存。
输入为仓库相对路径及字节、或最终指南文件映射；返回规范化字节及检查数量。
函数只操作内存，不读写文件，不在普通分析运行中调用。
"""
from hashlib import sha256
import json
from pathlib import PurePosixPath


def resource_bytes(relative, data):
    """按资源用途决定是否规范换行，保留带摘要的结果文件原始字节。

    参数: relative为仓库相对路径，data为原始bytes。
    返回: bytes；教学数据、结果目录及二进制不变，其余已登记文本转换CRLF为LF。
    异常: 无主动异常；错误参数类型由基础操作拒绝。
    """
    path = PurePosixPath(str(relative).replace('\\', '/'))
    suffix = path.suffix.lower()
    if path.as_posix().startswith(('Docs/Current/examples/results/', 'Docs/Current/examples/data/')):
        return data
    # fast、temporal等专题的输入也按格式保留，不能只覆盖主data目录。
    if path.as_posix().startswith('Docs/Current/examples/') and suffix in {'.csv', '.asc', '.dbc', '.blf', '.txt'}:
        return data
    if suffix in {'.json', '.yaml', '.md', '.csv', '.asc', '.dbc', '.ini', '.py'}:
        return data.replace(b'\r\n', b'\n')
    return data


def validate_result_summaries(files):
    """逐份核对指南内结果摘要引用的实际文件，避免外层清单掩盖内层失配。

    参数: files为指南相对路径到原始bytes的映射。
    返回: dict，包含检查的摘要数和结果文件数。
    异常: ValueError，摘要结构、相对路径、文件大小或SHA256不一致。
    """
    summaries = checked = 0
    for name, data in files.items():
        if not name.startswith('examples/results/') or not name.endswith('/result-summary.json'):
            continue
        summary = json.loads(data)
        records = summary.get('files')
        if not isinstance(records, list):
            raise ValueError('结果摘要缺少files数组：' + name)
        summaries += 1
        seen = set()
        for record in records:
            relative = record.get('path') if isinstance(record, dict) else None
            if not isinstance(relative, str) or not relative or '\\' in relative:
                raise ValueError('结果摘要文件路径无效：' + name)
            path = PurePosixPath(relative)
            if path.is_absolute() or '..' in path.parts or ':' in relative:
                raise ValueError('结果摘要路径必须位于本案例目录内：' + name)
            target = str(PurePosixPath(name).parent / path)
            if target in seen or target not in files:
                raise ValueError('结果摘要引用重复或缺失文件：' + target)
            seen.add(target)
            actual = files[target]
            if type(record.get('bytes')) is not int or record['bytes'] != len(actual):
                raise ValueError('结果摘要bytes不一致：' + target)
            if record.get('sha256') != sha256(actual).hexdigest():
                raise ValueError('结果摘要sha256不一致：' + target)
            checked += 1
    return {'result_summaries': summaries, 'result_files': checked}
