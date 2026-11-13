# `chronaxis.analysis_cli`

把公共AnalysisRunner的检查、解释和实际分析接到CLI，提供文本和JSON报告。

输入为解析后的命令参数，load_analysis_plan只读取指定JSON/YAML并按配置目录解释来源路径。
validate和explain直接调用同一AnalysisRunner接口，不读取CSV、DBC或旧日志，不建立
运行目录。序列化逐项选择公开报告字段，不遍历任意对象或另做一套配置校验。
报告中的预算和有效期是声明，execution_ready不证明实际输入已核实。
run先检查输出根与独占工作路径，再交给AnalysisRunner运行，在同一结果上write并关闭。
只有真实关闭成功才打印成功摘要；失败保留原原因链和现存产物，不假报回滚。

本模块仅在实际计划命令时加载；CLI帮助与参数错误仍只需要标准库。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[AnalysisError](chronaxis.results.errors.md#api-AnalysisError)、[AnalysisRunner](chronaxis.runner.md#api-AnalysisRunner)、[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)、[PlanValidationError](chronaxis.planning.checks.md#api-PlanValidationError)

## 对象导航

|对象|用途|
|---|---|
|[`validation_json`](#api-validation_json)|保留公共校验报告的全部固定字段和未验证警告。|
|[`explanation_json`](#api-explanation_json)|将依赖、节点后端、历史需求和预算声明完整交给CLI使用者。|
|[`run_static`](#api-run_static)|只加载配置并输出共享AnalysisRunner报告，不触碰来源或创建分析产物。|
|[`_new_output`](#api-_new_output)|在扫描来源前检查可复用输出根和冲突工作路径。|
|[`_cause_chain`](#api-_cause_chain)|取得有限且不重复的真实cause链，供诊断和致命异常判断共用。|
|[`run_analysis`](#api-run_analysis)|复用真实分析和发布，成功关闭所有结果资源后才报告completed。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from pathlib import Path
from . import AnalysisRunner, load_analysis_plan
from .planning.checks import PlanValidationError
from .results.errors import AnalysisError
```

</details>

<a id="api-validation_json"></a>
## `validation_json`

保留公共校验报告的全部固定字段和未验证警告。

```python
validation_json(report) -> dict
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`report`|ValidationReport|是|无|位置或关键字。report为AnalysisRunner.validate返回的ValidationReport。|

### 返回说明

原生JSON字典；元组和只读映射转换为列表和dict，不改变字段含义。

### 异常说明

接口不符的编程错误原样传播，不靠反射补缺失属性。

返回类型：dict。

源码：[`src/chronaxis/analysis_cli.py:23`](../../../src/chronaxis/analysis_cli.py#L23)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-explanation_json"></a>
## `explanation_json`

将依赖、节点后端、历史需求和预算声明完整交给CLI使用者。

```python
explanation_json(report) -> dict
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`report`|ExplainReport|是|无|位置或关键字。report为AnalysisRunner.explain返回的ExplainReport。|

### 返回说明

固定JSON字典，节点保持原顺序，plan_identity保持原配置身份。

### 异常说明

接口不符的编程错误原样传播；不推算实测峰值或来源观测范围。

返回类型：dict。

源码：[`src/chronaxis/analysis_cli.py:35`](../../../src/chronaxis/analysis_cli.py#L35)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-run_static"></a>
## `run_static`

只加载配置并输出共享AnalysisRunner报告，不触碰来源或创建分析产物。

```python
run_static(arguments) -> int
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`arguments`|argparse.Namespace|是|无|位置或关键字。命令行解析后得到的参数对象；属性包括该命令的plan路径，以及output、backend、process_count等适用选项。字段由[CLI](../cli.md)生成，通常直接使用命令行入口。|

### 返回说明

0表示静态有效且当前有执行路径，2表示报告中存在能力错误。

### 异常说明

配置加载、依赖、JSON输出或取消错误向主CLI传播，由统一边界处理。

### 副作用说明

只读取计划JSON、写stdout；来源路径按load_analysis_plan解释，不按CLI另猜。

返回类型：int。

源码：[`src/chronaxis/analysis_cli.py:70`](../../../src/chronaxis/analysis_cli.py#L70)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_new_output"></a>
## `_new_output`

在扫描来源前检查可复用输出根和冲突工作路径。

```python
_new_output(arguments) -> Path
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`arguments`|argparse.Namespace|是|无|位置或关键字。arguments包含output和可选work_dir，由argparse限定为路径文本。|

### 返回说明

绝对输出Path；不创建目录，工作目录实际分配仍归AnalysisRunner。

### 异常说明

FileExistsError或原lstat错误为文件失败；PlanValidationError为工作目录与输出目录冲突。

本函数直接报告的具体错误：

- `PlanValidationError`：$.cli.work_dir。

返回类型：[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)。

源码：[`src/chronaxis/analysis_cli.py:100`](../../../src/chronaxis/analysis_cli.py#L100)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_cause_chain"></a>
## `_cause_chain`

取得有限且不重复的真实cause链，供诊断和致命异常判断共用。

```python
_cause_chain(error) -> tuple
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`error`|BaseException|是|无|位置或关键字。本次操作产生的原异常对象；用于保留原因链、附加清理失败信息或继续抛出，不应换成一段字符串。|

### 返回说明

最多16个原异常对象，保持外层到根因顺序。

### 异常说明

无主动异常；不访问任意业务对象，不解析日志或重建错误。

返回类型：tuple。

源码：[`src/chronaxis/analysis_cli.py:129`](../../../src/chronaxis/analysis_cli.py#L129)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-run_analysis"></a>
## `run_analysis`

复用真实分析和发布，成功关闭所有结果资源后才报告completed。

```python
run_analysis(arguments) -> int
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`arguments`|argparse.Namespace|是|无|位置或关键字。命令行解析后得到的参数对象；属性包括该命令的plan路径，以及output、backend、process_count等适用选项。字段由[CLI](../cli.md)生成，通常直接使用命令行入口。|

### 返回说明

成功0；已知分析/发布/关闭失败1，并说明输出可能已经发布。

### 异常说明

配置/路径错误交主CLI分类；取消原样传播；MemoryError及已知编程错误
    的直接或AnalysisError原因链继续抛出，不伪装成普通业务错误。

### 副作用说明

AnalysisRunner建立专用暂存并读来源，write在输出根新增本次文件；不删除已有产物。

返回类型：int。

源码：[`src/chronaxis/analysis_cli.py:145`](../../../src/chronaxis/analysis_cli.py#L145)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
