# chronaxis.cli

提供计划检查、运行发布、独立批量与旧INI导入，复用各自公共接口。

输入为命令行路径、模式及显式mapping；输出为新计划、原INI、迁移报告和简短
JSON摘要。转换失败仍可保存原文与失败报告，绝不返回部分可运行计划。
validate/explain只读取计划，输出共享AnalysisRunner报告，不打开数据/DBC或运行分析。
run才调用同一AnalysisRunner执行、write发布并关闭结果；完整完成后才打印成功摘要。
batch run调用同一批量API，打印状态计数，逐任务错误保存在batch_report.json。
配置和参数错误退出2，文件/平台错误退出1，取消退出130，成功退出0。
--help及参数错误只需标准库；实际命令执行时才加载对应计划或发布模块。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)

## 对象导航

|对象|用途|
|---|---|
|[`_parser`](#api-_parser)|定义已交付命令，未知命令和缺参数由argparse定位。|
|[`_brief`](#api-_brief)|生成固定摘要，不将全部原字段或warnings输出到控制台。|
|[`_issue_text`](#api-_issue_text)|将首个错误压缩为可跳转位置，完整事实留在迁移报告。|
|[`_run_import`](#api-_run_import)|调用真实两配置加载与计划最后发布，静态成功不代表数据运行通过。|
|[`main`](#api-main)|执行共享CLI并给出固定退出码，完整事实保在报告和原异常中。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from pathlib import Path
```

</details>

<a id="api-_parser"></a>
## `_parser`

定义已交付命令，未知命令和缺参数由argparse定位。

```python
_parser() -> argparse.ArgumentParser
```

参数：无显式参数。


### 参数说明

无。

### 返回说明

ArgumentParser，不读取任何配置或来源。

### 异常说明

原参数构造错误传播；解析时的帮助/坏参数分别SystemExit(0/2)。

返回类型：argparse.ArgumentParser。

源码：[`src/chronaxis/cli.py:19`](../../../src/chronaxis/cli.py#L19)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_brief"></a>
## `_brief`

生成固定摘要，不将全部原字段或warnings输出到控制台。

```python
_brief(result, files) -> dict
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`result`|LegacyImportResult|是|无|位置或关键字。INI迁移的完整结果，包含问题清单、转换计划和原始配置记录。|
|`files`|LegacyImportFiles|是|无|位置或关键字。已经发布的原文、报告和计划文件路径；用于命令行输出实际文件位置。|

### 返回说明

原生JSON对象，三路径为绝对str，转换失败plan为None。

### 异常说明

内部带有明确类型的接口不符直接传播，不以自由反射吞掉错误。

返回类型：dict。

源码：[`src/chronaxis/cli.py:83`](../../../src/chronaxis/cli.py#L83)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_issue_text"></a>
## `_issue_text`

将首个错误压缩为可跳转位置，完整事实留在迁移报告。

```python
_issue_text(issue) -> str
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`issue`|LegacyImportIssue|是|无|位置或关键字。迁移发现的一条问题，包含级别、位置、代码和说明；转换为便于阅读的一行文字。|

### 返回说明

一行文本，含来源/路径及存在的行列。

### 异常说明

内部字段类型错误传播，不截掉报告中的原始消息。

返回类型：str。

源码：[`src/chronaxis/cli.py:97`](../../../src/chronaxis/cli.py#L97)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_run_import"></a>
## `_run_import`

调用真实两配置加载与计划最后发布，静态成功不代表数据运行通过。

```python
_run_import(arguments) -> int
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`arguments`|argparse.Namespace|是|无|位置或关键字。命令行解析后得到的参数对象；属性包括该命令的plan或ini路径，以及output、backend、process_count等适用选项。字段由[CLI](../cli.md)生成，通常直接使用命令行入口。|

### 返回说明

0为完整转换/发布成功，2为原配置整体拒绝且原文/报告已保存。

### 异常说明

文件/平台/取消/资源错误原样向main传播，保发布器恢复owner。

返回类型：int。

源码：[`src/chronaxis/cli.py:111`](../../../src/chronaxis/cli.py#L111)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-main"></a>
## `main`

执行共享CLI并给出固定退出码，完整事实保在报告和原异常中。

```python
main(argv=None) -> int
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`argv`|str &#124; None|否|None|位置或关键字。argv为参数字符串序列或None（使用进程参数）。|

### 返回说明

0成功、2配置错误、1文件/平台错误、130取消。

### 异常说明

argparse帮助/参数错误按标准抛SystemExit；MemoryError及内部编程错误不伪装配置错误。

### 副作用说明

导入读取两配置并发布；静态命令只读计划；run分析后发布到新目录。

返回类型：int。

源码：[`src/chronaxis/cli.py:133`](../../../src/chronaxis/cli.py#L133)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
