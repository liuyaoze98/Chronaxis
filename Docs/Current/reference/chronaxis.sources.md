# `chronaxis.sources`

按需公开来源适配器和批次模型；读取 BLF 不加载无关的数组后端。

公开名称、类身份与原模块保持一致；只在访问相应名称时导入定义。
导入本包不打开输入、DBC 或工作目录，也不创建进程。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 对象导航

|对象|用途|
|---|---|
|[`__getattr__`](#api-__getattr__)|按公开名称返回原对象；未知名称抛 AttributeError，不导入其他来源。|

## 导出名称

`MemorySourceAdapter`, `SignalCSVSpec`, `CSVSourceRef`, `SignalCSVSourceAdapter`, `FieldDescription`, `FieldLocation`, `ReadRequest`, `SignalBatch`, `SignalSeries`, `SourceCapabilities`, `SourceDescription`, `BatchValidator`, `SourceAdapter`, `SourceClosedError`, `SourceReadError`

重导出保持定义位置的签名；按上级[总索引](index.md)查找对象名。

公开重导出按[公开API索引](../api.md)查询定义、用途和调用示例。

<details><summary>导入与重导出来源（展开）</summary>

```python
from importlib import import_module
```

</details>

<a id="api-__getattr__"></a>
## `__getattr__`

按公开名称返回原对象；未知名称抛 AttributeError，不导入其他来源。

```python
__getattr__(name: str) -> object
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`name`|str|是|无|位置或关键字。调用者请求的来源模块公开名称；按名称延迟导入对应对象，未知名称报告AttributeError。|

返回类型：object。

源码：[`src/chronaxis/sources/__init__.py:22`](../../../src/chronaxis/sources/__init__.py#L22)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
