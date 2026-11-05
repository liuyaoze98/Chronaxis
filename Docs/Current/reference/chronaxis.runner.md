# `chronaxis.runner`

这是大多数应用只需要调用的执行入口。先用load_analysis_plan读取配置，再用AnalysisRunner.validate检查声明、AnalysisRunner.explain查看将用哪些信号，最后AnalysisRunner.run实际读取数据并计算。run返回的AnalysisResult可逐行读取，也可write到可复用的结果目录；用with语句保证文件和游标及时关闭。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[AnalysisError](chronaxis.results.errors.md#api-AnalysisError)、[AnalysisPlan](chronaxis.planning.plan.md#api-AnalysisPlan)、[ExecutionPlan](chronaxis.planning.models.md#api-ExecutionPlan)、[ExtensionRegistry](chronaxis.extensions.md#api-ExtensionRegistry)

## 对象导航

|对象|用途|
|---|---|
|[`AnalysisRunner`](#api-AnalysisRunner)|配置单次分析的执行器。backend可覆盖计划设置；run创建独立资源，返回需关闭的AnalysisResult。通常复用执行器，分别管理每次结果。|
|[`AnalysisRunner.__init__`](#api-AnalysisRunner-__init__)|选择是否覆盖计划后端，不读取任何来源或配置文件。|
|[`AnalysisRunner.backend`](#api-AnalysisRunner-backend)|读取构造时的覆盖选择，不表示某个尚未运行计划的实际后端。|
|[`AnalysisRunner._effective_plan`](#api-AnalysisRunner-_effective_plan)|保留原声明身份，只为明确覆盖创建内部执行视图。|
|[`AnalysisRunner.validate`](#api-AnalysisRunner-validate)|报告声明是否合法及执行路径是否已接入，不提前读取数据。|
|[`AnalysisRunner.explain`](#api-AnalysisRunner-explain)|列出真实依赖、各节点后端、历史需求及声明预算，不启动分析。|
|[`AnalysisRunner.run`](#api-AnalysisRunner-run)|验证后执行一次真实分析，输入全关才返回独立AnalysisResult。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import replace
from .planning.plan import AnalysisPlan
from .planning.models import ExecutionPlan
from .planning.reports import validate_analysis_plan, explain_analysis_plan
from .results.errors import AnalysisError
from .results.spool import _cleanup_owner
```

</details>

<a id="api-AnalysisRunner"></a>
## `AnalysisRunner`

配置单次分析的执行器。backend可覆盖计划设置；run创建独立资源，返回需关闭的AnalysisResult。通常复用执行器，分别管理每次结果。

```python
AnalysisRunner(backend=None, *, extensions=None)
```


源码：[`src/chronaxis/runner.py:23`](../../../src/chronaxis/runner.py#L23)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-AnalysisRunner-__init__"></a>
### `AnalysisRunner.__init__`

选择是否覆盖计划后端，不读取任何来源或配置文件。

```python
AnalysisRunner.__init__(backend=None, *, extensions=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`backend`|str &#124; None|否|None|位置或关键字。`"reference"`使用独立参考计算；`"numpy"`使用NumPy数组计算。None沿用计划中的选择。|
|`extensions`|[ExtensionRegistry](chronaxis.extensions.md#api-ExtensionRegistry) &#124; None|否|None|仅关键字。实际执行或检查计划时传入的宿主注册，必须与创建计划时使用的对象相同。|

#### 返回说明

None；初始化实例状态。

#### 异常说明

TypeError为非文本覆盖；ValueError为未知后端。

本函数直接报告的具体错误：

- `TypeError`：AnalysisRunner backend需要reference、numpy或None。
- `ValueError`：AnalysisRunner仅支持reference与numpy后端。

源码：[`src/chronaxis/runner.py:30`](../../../src/chronaxis/runner.py#L30)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-AnalysisRunner-backend"></a>
### `AnalysisRunner.backend`

读取构造时的覆盖选择，不表示某个尚未运行计划的实际后端。

```python
AnalysisRunner.backend
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

None/reference/numpy。

#### 异常说明

无。

源码：[`src/chronaxis/runner.py:51`](../../../src/chronaxis/runner.py#L51)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-AnalysisRunner-_effective_plan"></a>
### `AnalysisRunner._effective_plan`

保留原声明身份，只为明确覆盖创建内部执行视图。

```python
AnalysisRunner._effective_plan(plan)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|[AnalysisPlan](chronaxis.planning.plan.md#api-AnalysisPlan)|是|无|位置或关键字。plan为已构建AnalysisPlan。|

#### 返回说明

原plan或仅execution.backend不同的新view。

#### 异常说明

TypeError为非计划/执行声明；不重新解析配置或复制原输入行。

本函数直接报告的具体错误：

- `TypeError`：AnalysisRunner需要load_analysis_plan或AnalysisPlan.from_dict构建的计划。

源码：[`src/chronaxis/runner.py:58`](../../../src/chronaxis/runner.py#L58)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-AnalysisRunner-validate"></a>
### `AnalysisRunner.validate`

报告声明是否合法及执行路径是否已接入，不提前读取数据。

```python
AnalysisRunner.validate(plan)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|[AnalysisPlan](chronaxis.planning.plan.md#api-AnalysisPlan)|是|无|位置或关键字。提供已构建的AnalysisPlan：用load_analysis_plan("analysis.yaml")读取配置，或用AnalysisPlan.from_dict(config)解析Python字典；这里不接收文件名字符串。|

#### 返回说明

同一共享ValidationReport，保留实际字段/范围未验警告。

#### 异常说明

TypeError：plan不是AnalysisPlan或其execution不是合法执行模型。正常计划的静态问题通过ValidationReport.errors返回，执行能力看execution_ready；不读取输入，不能把空errors当作实际日志已验证。

#### 副作用说明

无来源I/O或目录创建。

源码：[`src/chronaxis/runner.py:73`](../../../src/chronaxis/runner.py#L73)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-AnalysisRunner-explain"></a>
### `AnalysisRunner.explain`

列出真实依赖、各节点后端、历史需求及声明预算，不启动分析。

```python
AnalysisRunner.explain(plan)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|[AnalysisPlan](chronaxis.planning.plan.md#api-AnalysisPlan)|是|无|位置或关键字。提供已构建的AnalysisPlan：用load_analysis_plan("analysis.yaml")读取配置，或用AnalysisPlan.from_dict(config)解析Python字典；这里不接收文件名字符串。|

#### 返回说明

ExplainReport，plan_identity保原声明身份。

#### 异常说明

TypeError：plan不是AnalysisPlan或其execution类型不符。手工破坏带有明确类型的引用可能引发AttributeError/KeyError；重新使用from_dict/load_analysis_plan构造合法计划。函数不打开CSV/DBC，不测量实际耗时或内存。

#### 副作用说明

不读取CSV/DBC，也不测量实耗。

源码：[`src/chronaxis/runner.py:83`](../../../src/chronaxis/runner.py#L83)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-AnalysisRunner-run"></a>
### `AnalysisRunner.run`

验证后执行一次真实分析，输入全关才返回独立AnalysisResult。

```python
AnalysisRunner.run(plan, work_dir=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|[AnalysisPlan](chronaxis.planning.plan.md#api-AnalysisPlan)|是|无|位置或关键字。提供已构建的AnalysisPlan：用load_analysis_plan("analysis.yaml")读取配置，或用AnalysisPlan.from_dict(config)解析Python字典；这里不接收文件名字符串。|
|`work_dir`|str &#124; Path &#124; None|否|None|位置或关键字。本次运行独占的工作目录，用来保存中间文件。自行指定时要求尚不存在；不会覆盖旧目录。None让入口自动创建唯一目录。|

#### 返回说明

analysis_complete的AnalysisResult，由调用者close/上下文管理，write另行发布。

#### 异常说明

TypeError为错误plan；验证或运行错误为AnalysisError，保原cause和诊断；
    KeyboardInterrupt/SystemExit原样传播。持续清理失败用runner_cleanup_owner.close恢复。

#### 副作用说明

创建本次新暂存；扫描来源一次、后续仅回读新history，不自动删除或发布文件。

#### 调用示例

```python
"""从YAML配置执行分析并逐行读取结果；输入为配置路径，可选结果输出目录。"""
import argparse
from pathlib import Path

from chronaxis import AnalysisRunner, load_analysis_plan, validate_analysis_plan


def main():
    """检查配置后执行，显式关闭游标和结果。返回None；配置/执行错误保留异常链。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan', nargs='?', type=Path, default=Path(__file__).parent / 'analysis.yaml')
    parser.add_argument('--output', type=Path, help='可复用的正式输出目录；省略则只打印结果')
    args = parser.parse_args()
    plan = load_analysis_plan(args.plan)
    report = validate_analysis_plan(plan)
    if not report.valid or not report.execution_ready:
        raise RuntimeError(report)
    with AnalysisRunner().run(plan) as result:
        rows = result.iter_calculations()
        try:
            for row in rows:
                print(row.calculation_id, row.value, row.unit, row.status, row.reason)
        finally:
            rows.close()
        if args.output is not None:
            manifest = result.write(args.output)
            print(manifest)


if __name__ == '__main__':
    main()

```

源码：[`src/chronaxis/runner.py:94`](../../../src/chronaxis/runner.py#L94)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
