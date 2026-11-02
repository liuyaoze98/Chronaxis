"""公开内存来源、已解码信号表及公共批次协议。

MemorySourceAdapter接收已有内存原行，SignalCSVSourceAdapter接收明确格式
的已解码CSV配置；二者逐批输出SignalSeries和SignalBatch，并共用
SourceDescription、ReadRequest及BatchValidator的身份与进度检查。
导入只加载类型和计算模块，不打开输入文件或DBC，也不创建工作目录。
CAN配置与原报文定位在can_spec，公共AnalysisRunner已接单BLF/单DBC的旧公开链；
本模块的内存/CSV入口不代替CAN运行包装，也不代表其他旧入口已迁移。
"""

# 内存适配器传送已有原行的更新，不构造完整历史保持序列。
from .memory import MemorySourceAdapter
# CSV配置与逐样本定位用于明确的已解码表，不根据后缀猜原始报文。
from .csv_spec import CSVSourceRef, SignalCSVSpec
# 静态导入不会打开CSV，读取由实际迭代器执行。
from .signal_csv import SignalCSVSourceAdapter
# 对外暴露有结构校验的类型，不用object占位。
from .models import FieldDescription, FieldLocation, ReadRequest, SignalBatch, SignalSeries, SourceCapabilities, SourceDescription
# 生命周期协议和跨批校验可由其他已解码来源适配器共用。
from .protocol import BatchValidator, SourceAdapter, SourceClosedError, SourceReadError

# 保留内存/CSV与通用批次的公开名单；CAN通过计划与AnalysisRunner入口执行。
__all__ = ['MemorySourceAdapter', 'SignalCSVSpec', 'CSVSourceRef', 'SignalCSVSourceAdapter', 'FieldDescription', 'FieldLocation', 'ReadRequest', 'SignalBatch', 'SignalSeries', 'SourceCapabilities', 'SourceDescription', 'BatchValidator', 'SourceAdapter', 'SourceClosedError', 'SourceReadError']
