# chronaxis.BatchRunner

从`chronaxis`导入本对象。本页只列直接公开成员与必要的构造/上下文协议；内部实现见[模块参考](../reference/chronaxis.batch.runner.md)。

返回[公开API索引](../api.md)。参数表中的类型可跳转到定义；先核对必填、默认值与返回/异常说明。

## 成员导航

- [BatchRunner](#api-BatchRunner)
- [BatchRunner.__init__](#api-BatchRunner-__init__)
- [BatchRunner.run](#api-BatchRunner-run)

<a id="api-BatchRunner"></a>
## `BatchRunner`

通过有限spawn工作进程执行独立任务；同一任务的连续文件保持原顺序。

```python
BatchRunner(process_count=1, *, fail_fast=False, backend=None)
```


源码：[`src/chronaxis/batch/runner.py:123`](../../../src/chronaxis/batch/runner.py#L123)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-BatchRunner-__init__"></a>
### `BatchRunner.__init__`

配置调度。

```python
BatchRunner.__init__(process_count=1, *, fail_fast=False, backend=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`process_count`|int|否|1|位置或关键字。控制最多启动几个分析工作进程。填正整数，例如4；默认1。任务少于该值时按任务数启动，空批次不启动。此数量不包含调度主进程和CAN读取子进程。|
|`fail_fast`|bool|否|False|仅关键字。False时某任务失败仍继续尝试后续任务；True时发现失败后停止启动新任务，但等待已启动任务收尾。|
|`backend`|str &#124; None|否|None|仅关键字。`"reference"`使用独立参考计算；`"numpy"`使用NumPy数组计算。None沿用计划中的选择。|

#### 返回说明

None。初始化调度选项；调用BatchRunner(...)才创建并取得实例。此时不启动工作进程或读取输入。

#### 异常说明

类型、范围或计算后端无效。构造时不读取业务数据，也不启动工作进程。

本函数直接报告的具体错误：

- `ValueError`：process_count需要正原生int。
- `TypeError`：fail_fast需要bool。

源码：[`src/chronaxis/batch/runner.py:126`](../../../src/chronaxis/batch/runner.py#L126)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-BatchRunner-run"></a>
### `BatchRunner.run`

运行独立任务，原声明顺序返回报告。

```python
BatchRunner.run(jobs, output_dir, *, cancel_event=None, device_label='pending') -> BatchReport
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`jobs`|tuple|是|无|位置或关键字。提供BatchJob元组，例如load_batch_plan("batch.yaml").jobs；每项含独立分析的ID与计划，顺序决定报告排列。|
|`output_dir`|str &#124; [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。新批量结果目录，每个任务按id创建子目录；目标已经存在时拒绝覆盖。|
|`cancel_event`|[threading.Event](https://docs.python.org/3.12/library/threading.html#event-objects) &#124; None|否|None|仅关键字。可选取消标记；None表示没有。其他线程调用set()后停止派发新任务，正在执行的任务继续收尾。|
|`device_label`|str|否|'pending'|仅关键字。产出记录的设备标签，例如已核实的"home"或"work"；未确定时用"pending"。这是来源说明，不参与数值计算，也不根据文件路径猜测。|

#### 返回说明

BatchReport，close可重试子进程内失败清理。

#### 异常说明

声明/路径错误在创建工作进程前拒绝；工作进程调度器等基础设施错误收尾后传播。

本函数直接报告的具体错误：

- `TypeError`：批量任务需要BatchJob tuple。
- `ValueError`：批量job_id不能重复，大小写冲突也拒绝。
- `TypeError`：cancel_event需要threading.Event。
- `ValueError`：device_label需要非空文本。

#### 副作用说明

启动最多process_count个工作进程，每任务独立发布；取消只阻止未派发任务。

返回类型：[BatchReport](BatchReport.md#api-BatchReport)。

源码：[`src/chronaxis/batch/runner.py:138`](../../../src/chronaxis/batch/runner.py#L138)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
