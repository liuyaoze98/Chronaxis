"""在真正使用 CAN 库时给出缺依赖诊断，已安装的库仍按需导入。

输入为固定支持的模块名，输出为原模块；仅包装缺少模块的异常，其他导入错误
继续原样报告。不安装依赖、不读取输入、不修改 reader/decoder 的调用顺序。
"""
from importlib import import_module


CAN_INSTALL_HINT = (
    '请在运行分析的同一个 Python 环境重新安装本地 wheel，默认会安装 CAN 依赖：'
    'python -m pip install "./chronaxis-<版本>-py3-none-any.whl"。'
    '将文件路径替换为实际收到的安装包；离线时需备齐该 wheel 声明版本的依赖。'
    '不要通过修改信号字段解决环境缺依赖，也不要仅安装未核实版本的 cantools。'
)


class CANDependencyError(ImportError):
    """保留缺失模块名与机器码的 CAN 环境错误，不冒充配置值错误。"""

    code = 'dependency_missing'

    def __init__(self, module_name):
        """保存缺项及安装建议。参数: module_name 为缺失模块名。返回: None。异常: 无。"""
        self.module_name = module_name
        self.hint = CAN_INSTALL_HINT
        super().__init__(f'缺少 CAN 读取/解码依赖：{module_name}。{self.hint}')


def import_can_dependency(module_name):
    """按既有调用点导入实际需要的 CAN 库。

    参数: module_name 为 can、cantools 或 natsort。
    返回: 原 Python 模块。异常: CANDependencyError 表示模块或其依赖缺失；
    其他 ImportError 原样传播，避免将损坏或不兼容安装误报成信号错误。
    """
    if module_name not in ('can', 'cantools', 'natsort'):
        raise ValueError('不是已声明的 CAN 依赖')
    try:
        return import_module(module_name)
    except ModuleNotFoundError as error:
        # 间接依赖也可能缺失；保留具体名字供定位完整安装问题。
        raise CANDependencyError(error.name or module_name) from error


def runtime_dependency_versions():
    """取得当前解释器与CAN依赖的实际版本，用于父子环境一致性核对。

    参数: 无。返回: python、python-can、cantools、natsort版本字符串字典。
    异常: 缺少分发元数据时PackageNotFoundError；不导入CAN库或打开业务输入。
    支持版本范围由安装元数据和兼容矩阵定义，不用历史固定补丁号拒绝已验证版本。
    """
    from importlib import metadata
    import platform
    # 元数据只核对实际父子环境，不在模块导入时载入第三方CAN库。
    return {
        'python': platform.python_version(),
        **{name: metadata.version(name) for name in ('python-can', 'cantools', 'natsort')},
    }
