"""集中加载DBC文本，不进入第三方持久缓存入口。

调用方负责导入cantools、复用数据库和校验文件身份；这里使用公开load接口，
保留load_file无缓存分支的格式、编码和解析默认值，不读取缓存环境变量。
"""

import os


def load_dbc_file(path, cantools):
    """按文件后缀打开一次文本并交给调用方持有的cantools解析。

    参数: path为原路径对象或字符串；cantools为调用方已导入的模块。
    返回: 官方load返回的数据库。异常: 原文件打开、解析或关闭错误原样传播。
    本次只拥有文本句柄，不保存数据库，不改环境变量或第三方模块。
    """
    # 与两端load_file保持一致：不把未知后缀改成自动探测，非法字节仍替换。
    database_format = os.path.splitext(path)[1][1:].lower()
    encoding = 'cp1252' if database_format in ('dbc', 'sym') else 'utf-8'
    with open(path, encoding=encoding, errors='replace') as stream:
        return cantools.database.load(
            stream, database_format=database_format,
            frame_id_mask=None, prune_choices=False, strict=True,
        )
