# chronaxis.BatchPlan

从`chronaxis`导入本对象。本页只列直接公开成员与必要的构造/上下文协议；内部实现见[模块参考](../reference/chronaxis.batch.models.md)。

返回[公开API索引](../api.md)。参数表中的类型可跳转到定义；先核对必填、默认值与返回/异常说明。

## 成员导航

- [BatchPlan](#api-BatchPlan)
- [BatchPlan.from_dict](#api-BatchPlan-from_dict)

<a id="api-BatchPlan"></a>
## `BatchPlan`

保存批量配置；只关联独立计划路径，不能把一个会话拆成多个时间任务。

```python
BatchPlan(jobs: tuple[chronaxis.batch.models.BatchJob, ...], process_count: int = 1, fail_fast: bool = False, backend: str | None = None) -> None
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`jobs`|tuple[[BatchJob](BatchJob.md#api-BatchJob), ...]|是|无|提供BatchJob元组，例如(BatchJob("a", Path("a.yaml")),)；也可通过load_batch_plan读取YAML取得。元组顺序就是最终报告顺序。|
|`process_count`|int|否|1|控制最多启动几个分析工作进程。填正整数，例如4；默认1。任务少于该值时按任务数启动，空批次不启动。此数量不包含调度主进程和CAN读取子进程。|
|`fail_fast`|bool|否|False|控制某任务失败后的调度：False继续其他独立任务；True停止提交新任务，已运行任务按批量执行器的取消流程收尾。|
|`backend`|str &#124; None|否|None|`"reference"`使用独立参考计算，`"numpy"`使用NumPy数组计算。None沿用计划的设置。|

源码：[`src/chronaxis/batch/models.py:58`](../../../src/chronaxis/batch/models.py#L58)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-BatchPlan-from_dict"></a>
### `BatchPlan.from_dict`

检查批量配置；jobs只关联路径，template读取模板并展开文件集合。

```python
BatchPlan.from_dict(config, *, base_dir=None)
```

装饰器：`classmethod`。

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`config`|dict[str, object]|是|无|位置或关键字。批量配置：batch_version=1；jobs与template+inputs二选一。jobs每项plan必填，name省略按位置生成job_N；template有多来源时用source明确目标。可选process_count、fail_fast、backend。见[独立批量任务](../batch.md)。|
|`base_dir`|str &#124; [pathlib.Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path) &#124; None|否|None|仅关键字。解析计划中相对路径所用的目录；None表示使用当前工作目录。|

#### 返回说明

冻结BatchPlan。

#### 异常说明

PlanValidationError定位非法字段、重名、缺少模板输入或来源歧义。jobs可为空；jobs只保留计划路径，template会读取模板、展开文件集合并按需读取DBC元数据，不扫描业务报文。

源码：[`src/chronaxis/batch/models.py:80`](../../../src/chronaxis/batch/models.py#L80)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
