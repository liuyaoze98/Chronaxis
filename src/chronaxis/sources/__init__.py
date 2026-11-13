"""按需公开来源适配器和批次模型；读取 BLF 不加载无关的数组后端。

公开名称、类身份与原模块保持一致；只在访问相应名称时导入定义。
导入本包不打开输入、DBC 或工作目录，也不创建进程。
"""
from importlib import import_module

_EXPORTS = {
    'MemorySourceAdapter':'memory',
    'SignalCSVSourceAdapter':'signal_csv',
    'SignalCSVSpec':'csv_spec', 'CSVSourceRef':'csv_spec',
    **dict.fromkeys(('FieldDescription','FieldLocation','ReadRequest','SignalBatch','SignalSeries',
                     'SourceCapabilities','SourceDescription'),'models'),
    **dict.fromkeys(('BatchValidator','SourceAdapter','SourceClosedError','SourceReadError'),'protocol'),
}
__all__ = ['MemorySourceAdapter','SignalCSVSpec','CSVSourceRef','SignalCSVSourceAdapter',
           'FieldDescription','FieldLocation','ReadRequest','SignalBatch','SignalSeries',
           'SourceCapabilities','SourceDescription','BatchValidator','SourceAdapter',
           'SourceClosedError','SourceReadError']


def __getattr__(name: str) -> object:
    """按公开名称返回原对象；未知名称抛 AttributeError，不导入其他来源。"""
    module = _EXPORTS.get(name)
    if module is None:
        raise AttributeError(f'chronaxis.sources没有公开属性{name!r}')
    value = getattr(import_module('.'+module,__name__),name)
    globals()[name] = value
    return value
