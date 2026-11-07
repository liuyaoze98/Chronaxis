# `chronaxis.fast.run`

准备和执行单会话同帧累计，仅在全部输入、累计和资源关闭成功后发布结果。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)、[PublicationNames](chronaxis.results.publication.md#api-PublicationNames)

## 对象导航

|对象|用途|
|---|---|
|[`run_prepared`](#api-run_prepared)|执行冻结会话并最后发布清单。|
|[`run`](#api-run)|运行一份fast单会话配置，所有分卷成功后发布汇总。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from pathlib import Path
from tempfile import TemporaryDirectory
from ..results.publication import PublicationNames, output_root
```

</details>

<a id="api-run_prepared"></a>
## `run_prepared`

执行冻结会话并最后发布清单。

```python
run_prepared(spec: dict, output: str | Path, *, engine: str, database: object | None=None, cancel_event: object | None=None, _return_rows: bool=False, work_dir: str | Path | None=None) -> Path | tuple[Path, tuple]
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|dict|是|无|位置或关键字。本次已编译会话或单文件声明，包含来源、公式、顺序和执行资源；调用过程不改写它。|
|`output`|str &#124; [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。接收本次结果表和完成清单的目录。|
|`engine`|str|是|无|仅关键字。写入完成清单的执行器标识。|
|`database`|cantools.database.Database &#124; None|否|None|仅关键字。预检时加载的 DBC，可交本次执行复用。|
|`cancel_event`|Event &#124; None|否|None|仅关键字。外部取消事件，支持is_set()；设置后停止本次会话并清理，不返回成功结果。|
|`_return_rows`|bool|否|False|仅关键字。请求跨文件总量时直接返回未舍入指标行。|
|`work_dir`|str &#124; [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path) &#124; None|否|None|仅关键字。本次暂存目录的父路径；None使用系统临时目录，每次调用创建独立子目录。|

### 返回说明

清单Path；_return_rows=True时返回(Path, 行tuple)。

### 异常说明

执行/取消/发布错误。

返回类型：[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path) &#124; tuple[[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path), tuple]。

源码：[`src/chronaxis/fast/run.py:11`](../../../src/chronaxis/fast/run.py#L11)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-run"></a>
## `run`

运行一份fast单会话配置，所有分卷成功后发布汇总。

```python
run(config: str | Path, output: str | Path, *, process_count: int | None=None, work_dir: str | Path | None=None, cancel_event: object | None=None) -> Path
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`config`|str &#124; [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。同一会话的YAML/JSON分析配置路径；一个来源可包含多个ASC/BLF分卷。|
|`output`|str &#124; [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。接收本次结果表和完成清单的目录。|
|`process_count`|int &#124; None|否|None|仅关键字。本次读取、解码、求值工作进程上限覆盖；None沿用声明，正整数且不接受布尔值。|
|`work_dir`|str &#124; [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path) &#124; None|否|None|仅关键字。本次暂存目录的父路径；None使用系统临时目录，每次调用创建独立子目录。|
|`cancel_event`|Event &#124; None|否|None|仅关键字。外部取消事件，支持is_set()；设置后停止本次会话并清理，不返回成功结果。|

### 返回说明

pathlib.Path，本次成功清单。

### 异常说明

配置/文件/资源/数值错误及InterruptedError。

返回类型：[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)。

源码：[`src/chronaxis/fast/run.py:63`](../../../src/chronaxis/fast/run.py#L63)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
