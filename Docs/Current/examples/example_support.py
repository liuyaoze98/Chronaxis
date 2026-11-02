"""验证脚本共用的可移植输出目录设置；不依赖仓库层级或预建work目录。"""
import argparse
import os
from pathlib import Path
import tempfile


def new_output(prefix):
    """读取命令参数并创建唯一输出目录。

    参数: prefix为临时目录前缀；CLI可指定--output-root既有父目录和--device-label备注。
    返回: (Path, str)，新目录及报告标签。异常: 参数错误或目录创建错误原样报告。
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-root', type=Path, help='既有可写父目录；省略使用系统临时目录')
    parser.add_argument('--device-label', default=os.environ.get('CHRONAXIS_DEVICE_LABEL', 'pending'), help='验证报告来源备注，不控制分析算法')
    args = parser.parse_args()
    if args.output_root is not None and not args.output_root.is_dir():
        parser.error('--output-root必须是已存在的目录')
    if not args.device_label.strip():
        parser.error('--device-label不能为空')
    return Path(tempfile.mkdtemp(prefix=prefix, dir=args.output_root)).resolve(), args.device_label
