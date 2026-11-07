# chronaxis.run_batch

使用`from chronaxis import run_batch`导入。本页只列直接公开成员与必要的构造/上下文协议；内部实现见[模块参考](../reference/chronaxis.batch.api.md)。

返回[公开API索引](../api.md)。参数表中的类型可跳转到定义；先核对必填、默认值与返回/异常说明。

## 成员导航

- [`run_batch`](#api-run_batch)

<a id="api-run_batch"></a>
## `run_batch`

执行一批独立分析并写出批量报告。使用spawn工作进程，各任务单独加载、分析、发布和清理；在Python脚本的main保护内调用。

```python
run_batch(plan: BatchPlan, output_dir, *, process_count: int | None=None, cancel_event=None, device_label='pending')
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|[BatchPlan](BatchPlan.md#api-BatchPlan)|是|无|位置或关键字。指定要执行的批量任务及调度设置。传入load_batch_plan("batch.yaml")取得的BatchPlan，不能直接传文件名或普通分析计划。|
|`output_dir`|str &#124; Path|是|无|位置或关键字。可重复使用的批量结果目录；任务子目录带本批时间后缀，已有结果保持。实际路径从报告读取。|
|`process_count`|int &#124; None|否|None|仅关键字。覆盖本次分析工作进程数。填正整数，例如4；None沿用BatchPlan.process_count，不修改原计划。|
|`cancel_event`|[threading.Event](https://docs.python.org/3.12/library/threading.html#event-objects) &#124; None|否|None|仅关键字。可选取消标记；None表示没有。其他线程调用set()后停止派发新任务，正在执行的任务继续收尾。|
|`device_label`|str|否|'pending'|仅关键字。产出记录的设备标签，例如已核实的"home"或"work"；未确定时用"pending"。这是来源说明，不参与数值计算，也不根据文件路径猜测。|

### 返回说明

BatchReport；report_path为本次实际报告，jobs各项的manifest_path为实际完成清单。failed/cancelled保留在报告，不伪装全部成功。

### 异常说明

TypeError：plan不是BatchPlan或取消对象类型不合法。ValueError：并发/后端/任务声明不合法。目录创建、调度或报告发布失败按具体异常类型抛出；若已产生报告，异常batch_report保存实际进度，调用者仍须close处理cleanup_pending。单任务失败通常保存在报告jobs中，不作为整个函数抛错。见[按阶段处理错误](../troubleshooting.md#api-errors)。

### 调用示例

```python
from chronaxis import load_batch_plan, run_batch

def main():
    # 先准备batch.yaml；batch-output可以已有结果。
    report = run_batch(load_batch_plan("batch.yaml"), "batch-output")
    try:
        print(report.report_path)
    finally:
        report.close()

if __name__ == "__main__":
    main()
```

源码：[`src/chronaxis/batch/api.py:13`](../../../src/chronaxis/batch/api.py#L13)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
