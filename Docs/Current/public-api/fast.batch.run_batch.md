# chronaxis.fast.batch.run_batch

`from chronaxis.fast.batch import run_batch`

<a id="api-run_batch"></a>
## `run_batch`

并行执行相互独立的高性能积分任务；连续来源paths不能借此拆成独立文件。

```python
run_batch(plan_path, output, *, process_count=None, cancel_event=None, total=False)
```

|名称|类型|必填|默认值|用途|
|---|---|---|---|---|
|`plan_path`|见用途|是|无默认值|str或Path：batch_version为1的jobs或template批量配置路径。每个任务都需满足fast能力范围。|
|`output`|见用途|是|无默认值|str或Path：批量输出目录，可以复用；任务输出与批量报告使用本次独占名称。|
|`process_count`|见用途|否|None|正整数或None。None沿用批量配置；显式正整数覆盖进程上限。布尔值不是合法计数。|
|`cancel_event`|见用途|否|None|`threading.Event`或`None`。调用`set()`请求取消：停止派发尚未启动的任务，并通知在途fast任务停止；协作退出超过5秒时启动进程回收。已完成任务可保留completed状态，其他任务以报告中的status、error_type和error_message为准。只有is_set()方法的其他对象不被接受。|
|`total`|见用途|否|False|布尔值，True请求同模板且定义一致的全批总量；按计算项完整性判定，不把缺失值当0。默认不额外汇总。|

### 返回

pathlib.Path：本次批量报告路径。报告可包含失败或未启动任务；返回路径不代表每个任务成功，须检查报告。

### 异常

配置错误抛PlanValidationError；非法total抛TypeError。基础设施异常继续传播，可能通过异常的batch_report附带已保存报告。任务失败按计划fail_fast政策记录。

### 执行与资源

创建工作进程、读取每个任务输入并写报告；内部关闭批量资源。Windows脚本必须在`if __name__ == "__main__":`保护内调用。

[高性能积分器教程](../fast-energy.md)

源码：[`src/chronaxis/fast/batch.py:49`](../../../src/chronaxis/fast/batch.py#L49)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
