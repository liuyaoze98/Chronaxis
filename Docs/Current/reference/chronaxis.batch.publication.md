# `chronaxis.batch.publication`

把批量报告写入独占命名的新 JSON 文件。先完成写入和关闭，再用平台不覆盖原语发布：Windows 使用重命名，Linux 使用 renameat2 的 RENAME_NOREPLACE。目标已存在或平台能力不足时失败；不会因此删除已完成任务的结果。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[BatchReport](chronaxis.batch.models.md#api-BatchReport)、[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)

## 对象导航

|对象|用途|
|---|---|
|[`write_batch_report`](#api-write_batch_report)|发布带本批时间的汇总文件。|
|[`_write_batch_report`](#api-_write_batch_report)|先完成可选的 fast 总量计算，再一次发布同一批报告。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from pathlib import Path
from .models import BatchReport
```

</details>

<a id="api-write_batch_report"></a>
## `write_batch_report`

发布带本批时间的汇总文件。

```python
write_batch_report(report: BatchReport) -> Path
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`report`|[BatchReport](chronaxis.batch.models.md#api-BatchReport)|是|无|位置或关键字。report实际结果。|

### 返回说明

实际报告路径。

### 异常说明

report 类型错误抛 TypeError；平台接口缺失或实际文件系统不支持不覆盖发布时抛 NotImplementedError。已有目标、写入、关闭或移动错误原样传播；关闭失败不安装报告。报告已发布后另有收尾失败时，异常的 published_report_path 指向实际报告；不删除已完成任务的结果。

### 副作用说明

只写本批目录的唯一暂存文件，失败不删除任务结果或覆盖已有报告。

返回类型：[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)。

源码：[`src/chronaxis/batch/publication.py:14`](../../../src/chronaxis/batch/publication.py#L14)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_write_batch_report"></a>
## `_write_batch_report`

先完成可选的 fast 总量计算，再一次发布同一批报告。

```python
_write_batch_report(report, extra)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`report`|[BatchReport](chronaxis.batch.models.md#api-BatchReport)|是|无|位置或关键字。本批各任务的成功、取消、失败以及发布路径。|
|`extra`|dict &#124; None|是|无|位置或关键字。在报告根写入的 fast 执行标志和可选总量。|

源码：[`src/chronaxis/batch/publication.py:23`](../../../src/chronaxis/batch/publication.py#L23)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
