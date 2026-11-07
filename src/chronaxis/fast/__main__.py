"""直接运行fast单会话配置；输入可包含同一来源的多个分卷。"""

import argparse
import json
from .run import run


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True)
    parser.add_argument('--output',required=True)
    args = parser.parse_args()
    print(json.dumps({'manifest_path':str(run(args.config,args.output))},ensure_ascii=False))
