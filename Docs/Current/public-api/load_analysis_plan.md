# chronaxis.load_analysis_plan

使用`from chronaxis import load_analysis_plan`导入。本页只列直接公开成员与必要的构造/上下文协议；内部实现见[模块参考](../reference/chronaxis.planning.plan.md)。

返回[公开API索引](../api.md)。参数表中的类型可跳转到定义；先核对必填、默认值与返回/异常说明。

## 成员导航

- [`load_analysis_plan`](#api-load_analysis_plan)

<a id="api-load_analysis_plan"></a>
## `load_analysis_plan`

加载JSON/YAML及显式公共定义，应用受限覆盖并编译分析计划。目录输入会展开文件名；信号缺省类型、单位或枚举映射时按需读取DBC，不扫描业务报文。

```python
load_analysis_plan(path: Path | str, *, extensions=None) -> AnalysisPlan
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`path`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path) &#124; str|是|无|位置或关键字。配置文件路径；不接受目录扫描或任意路径对象。 配置按UTF-8读取，允许文件开头带BOM。|
|`extensions`|ExtensionRegistry &#124; None|否|None|仅关键字。宿主为版本4分析显式创建的注册表；省略时没有可额外调用的宿主操作。|

### 返回说明

AnalysisPlan：已检查并编译的计划。加载主配置与显式公共定义，按声明展开文件集合，必要时读取DBC元数据；不读取业务报文或CSV记录。

### 异常说明

PlanValidationError: 路径类型错误、文件读取或编码错误、JSON/YAML语法错误、
        重复键、非有限常量或配置声明错误。加载错误带配置文件定位，
        通过原异常链保留更详细的原因。

### 副作用说明

打开指定配置及公共定义文件，按需求读取DBC或枚举目录；句柄在正常或异常返回前关闭，不创建结果文件。

返回类型：[AnalysisPlan](AnalysisPlan.md#api-AnalysisPlan)。

### 调用示例

```python
from chronaxis import load_analysis_plan
plan = load_analysis_plan("Docs/Current/examples/analysis.yaml")
```

源码：[`src/chronaxis/planning/plan.py:368`](../../../src/chronaxis/planning/plan.py#L368)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
