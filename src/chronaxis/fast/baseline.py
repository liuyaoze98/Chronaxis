"""修复版 base 的测量入口。输入为冻结的文件参数，只测读取、直接累计及发布。"""

import argparse
import json
from pathlib import Path

from .run import run_prepared


def main():
    """执行一个低层基准任务并打印实际清单路径。解析或执行错误使进程失败。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    spec = json.loads(args.config.read_text(encoding='utf-8-sig'))
    path = run_prepared(spec,args.output,engine='chrginfo_corrected')
    print(json.dumps({'manifest_path':str(path)},ensure_ascii=False))


if __name__ == '__main__':
    main()
