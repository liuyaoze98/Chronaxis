# chronaxis.BatchReport

使用`from chronaxis import BatchReport`导入。本页只列直接公开成员与必要的构造/上下文协议；内部实现见[模块参考](../reference/chronaxis.batch.models.md)。

返回[公开API索引](../api.md)。参数表中的类型可跳转到定义；先核对必填、默认值与返回/异常说明。

## 成员导航

- [`BatchReport`](#api-BatchReport)
- [`BatchReport.status`](#api-BatchReport-status)
- [`BatchReport.to_dict`](#api-BatchReport-to_dict)
- [`BatchReport.close`](#api-BatchReport-close)

<a id="api-BatchReport"></a>
## `BatchReport`

按原任务顺序汇总结果；每个任务数值表仍在各自目录，不跨口径归约。

```python
BatchReport(output_dir: pathlib.Path, jobs: tuple[chronaxis.batch.models.BatchJobResult, ...], process_count: int, fail_fast: bool, cancel_requested: bool, device_label: str, worker_process_count: int = 0, infrastructure_error: str | None = None, report_path: pathlib.Path | None = None, _publication: object = None) -> None
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`output_dir`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|可复用的批量输出根目录。|
|`jobs`|tuple[[BatchJobResult](BatchJobResult.md#api-BatchJobResult), ...]|是|无|最终结果顺序不受工作进程完成先后影响。|
|`process_count`|int|是|无|控制最多启动几个分析工作进程。填正整数，例如4；默认1。任务少于该值时按任务数启动，空批次不启动。此数量不包含调度主进程和CAN读取子进程。|
|`fail_fast`|bool|是|无|是否在观察到失败后停止派发。|
|`cancel_requested`|bool|是|无|用户取消或KeyboardInterrupt是否曾被观察到。|
|`device_label`|str|是|无|标记本次批量报告的来源设备。直接构造BatchReport时必填非空文本；run_batch或BatchRunner.run的device_label参数省略时才采用pending。不会覆盖子分析metadata.device_label。|
|`worker_process_count`|int|否|0|本次实际启动的分析工作进程数量；可能少于process_count，空批次或开始前取消时为0。不包含CAN读取子进程。|
|`infrastructure_error`|str &#124; None|否|None|调度/汇总基础设施异常的说明；None表示未记录这类错误，不代表每个任务成功。任务错误查看jobs中的status、error_type、error_message及error_chain。|
|`report_path`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path) &#124; None|否|None|已发布的实际批量报告路径；BatchRunner.run尚未写报告时为None，run_batch写完报告后提供。|
|`_publication`|object|否|None|持有本批名称，关闭释放。|

源码：[`src/chronaxis/batch/models.py:179`](../../../src/chronaxis/batch/models.py#L179)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-BatchReport-status"></a>
### `BatchReport.status`

汇总失败优先状态。

```python
BatchReport.status: str
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

failed/cancelled/completed。

#### 异常说明

无。

返回类型：str。

源码：[`src/chronaxis/batch/models.py:194`](../../../src/chronaxis/batch/models.py#L194)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-BatchReport-to_dict"></a>
### `BatchReport.to_dict`

输出身份和计数。

```python
BatchReport.to_dict() -> dict
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

JSON对象。

#### 异常说明

无。不合并指标值。

返回类型：dict。

源码：[`src/chronaxis/batch/models.py:200`](../../../src/chronaxis/batch/models.py#L200)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-BatchReport-close"></a>
### `BatchReport.close`

重试所有未完清理。

```python
BatchReport.close() -> None
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

首个关闭错误，其他项仍尝试。

返回类型：None。

源码：[`src/chronaxis/batch/models.py:211`](../../../src/chronaxis/batch/models.py#L211)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
