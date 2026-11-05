# `chronaxis.sources`

公开内存来源、已解码信号表及公共批次协议。

MemorySourceAdapter接收已有内存原行，SignalCSVSourceAdapter接收明确格式
的已解码CSV配置；二者逐批输出SignalSeries和SignalBatch，并共用
SourceDescription、ReadRequest及BatchValidator的身份与进度检查。
导入只加载类型和计算模块，不打开输入文件或DBC，也不创建工作目录。
CAN配置与原报文定位在can_spec，公共AnalysisRunner已接单BLF/单DBC的旧公开链；
本模块的内存/CSV入口不代替CAN运行包装，也不代表其他旧入口已迁移。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[BatchValidator](chronaxis.sources.protocol.md#api-BatchValidator)、[CSVSourceRef](chronaxis.sources.csv_spec.md#api-CSVSourceRef)、[FieldDescription](chronaxis.sources.models.md#api-FieldDescription)、[FieldLocation](chronaxis.sources.models.md#api-FieldLocation)、[MemorySourceAdapter](chronaxis.sources.memory.md#api-MemorySourceAdapter)、[ReadRequest](chronaxis.sources.models.md#api-ReadRequest)、[SignalBatch](chronaxis.sources.models.md#api-SignalBatch)、[SignalCSVSourceAdapter](chronaxis.sources.signal_csv.md#api-SignalCSVSourceAdapter)、[SignalCSVSpec](chronaxis.sources.csv_spec.md#api-SignalCSVSpec)、[SignalSeries](chronaxis.sources.models.md#api-SignalSeries)、[SourceAdapter](chronaxis.sources.protocol.md#api-SourceAdapter)、[SourceCapabilities](chronaxis.sources.models.md#api-SourceCapabilities)、[SourceClosedError](chronaxis.sources.protocol.md#api-SourceClosedError)、[SourceDescription](chronaxis.sources.models.md#api-SourceDescription)、[SourceReadError](chronaxis.sources.protocol.md#api-SourceReadError)

## 对象导航

|对象|用途|
|---|---|

## 导出名称

`MemorySourceAdapter`, `SignalCSVSpec`, `CSVSourceRef`, `SignalCSVSourceAdapter`, `FieldDescription`, `FieldLocation`, `ReadRequest`, `SignalBatch`, `SignalSeries`, `SourceCapabilities`, `SourceDescription`, `BatchValidator`, `SourceAdapter`, `SourceClosedError`, `SourceReadError`

重导出保持定义位置的签名；按上级[总索引](index.md)查找对象名。

公开重导出按[公开API索引](../api.md)查询定义、用途和调用示例。

<details><summary>导入与重导出来源（展开）</summary>

```python
from .memory import MemorySourceAdapter
from .csv_spec import CSVSourceRef, SignalCSVSpec
from .signal_csv import SignalCSVSourceAdapter
from .models import FieldDescription, FieldLocation, ReadRequest, SignalBatch, SignalSeries, SourceCapabilities, SourceDescription
from .protocol import BatchValidator, SourceAdapter, SourceClosedError, SourceReadError
```

</details>
