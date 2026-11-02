# chronaxis.batch.publication

把批量报告写入新的JSON文件。先写临时文件并关闭，再改名为正式报告；目标已经存在时不会覆盖。当前发布方式使用Windows的不覆盖重命名，其他平台会报错。任务各自已经生成的结果不会因此被删除。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[BatchReport](chronaxis.batch.models.md#api-BatchReport)、[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)

## 对象导航

|对象|用途|
|---|---|
|[`write_batch_report`](#api-write_batch_report)|发布固定汇总文件。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from pathlib import Path
from uuid import uuid4
from .models import BatchReport
```

</details>

<a id="api-write_batch_report"></a>
## `write_batch_report`

发布固定汇总文件。

```python
write_batch_report(report: BatchReport) -> Path
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`report`|[BatchReport](chronaxis.batch.models.md#api-BatchReport)|是|无|位置或关键字。report实际结果。|

### 返回说明

batch_report.json路径。

### 异常说明

类型、只读路径、未支持平台、已有目标或原文件错误；关闭失败不安装正式文件。

本函数直接报告的具体错误：

- `TypeError`：需要BatchReport。
- `ValueError`：批量报告不能位于RefProjects。
- `NotImplementedError`：批量报告原子发布目前只验收Windows。

### 副作用说明

只写本批目录的唯一暂存文件，失败不删除任务结果或覆盖已有报告。

返回类型：[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)。

源码：[`src/chronaxis/batch/publication.py:14`](../../../src/chronaxis/batch/publication.py#L14)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
