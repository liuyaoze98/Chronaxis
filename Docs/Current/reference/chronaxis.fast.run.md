# `chronaxis.fast.run`

准备和执行单文件同帧累计，仅在文件全部计算成功后发布结果。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)、[PublicationNames](chronaxis.results.publication.md#api-PublicationNames)

## 对象导航

|对象|用途|
|---|---|
|[`run_prepared`](#api-run_prepared)|执行单文件，返回完成清单。批量请求跨文件总量时另返回未舍入指标行。|
|[`run`](#api-run)|读取单文件 Chronaxis 配置并执行，返回该次发布的 manifest 路径。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from pathlib import Path
from tempfile import TemporaryDirectory
from ..results.publication import PublicationNames, output_root
from .can_io import run_one
```

</details>

<a id="api-run_prepared"></a>
## `run_prepared`

执行单文件，返回完成清单。批量请求跨文件总量时另返回未舍入指标行。

```python
run_prepared(spec, output, *, engine, database=None, cancel_event=None, _return_rows=False)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|dict|是|无|位置或关键字。一个文件的已绑定参数，包括 DBC、通道、数值公式和输出单位。|
|`output`|str &#124; [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。接收本次结果表和完成清单的目录。|
|`engine`|str|是|无|仅关键字。写入完成清单的执行器标识。|
|`database`|cantools.database.Database &#124; None|否|None|仅关键字。预检时加载的 DBC，可交本次执行复用。|
|`cancel_event`|Event &#124; None|否|None|仅关键字。已设置时取消本次操作，省略时按调用方的正常生命周期运行。|
|`_return_rows`|bool|否|False|仅关键字。请求跨文件总量时直接返回未舍入指标行。|

源码：[`src/chronaxis/fast/run.py:12`](../../../src/chronaxis/fast/run.py#L12)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-run"></a>
## `run`

读取单文件 Chronaxis 配置并执行，返回该次发布的 manifest 路径。

```python
run(config, output)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`config`|str &#124; [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。当前独立文件的分析计划路径。|
|`output`|str &#124; [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。接收本次结果表和完成清单的目录。|

源码：[`src/chronaxis/fast/run.py:54`](../../../src/chronaxis/fast/run.py#L54)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
