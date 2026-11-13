# `chronaxis.results.errors`

定义分析、暂存、资源限额和结果发布过程中使用的异常类型。调用方可据此区分“超过内存限额”“结果已经关闭”“文件格式损坏”等失败原因；异常出现不代表此前生成的文件已经回滚。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 对象导航

|对象|用途|
|---|---|
|[`AnalysisError`](#api-AnalysisError)|表示分析或结果交付失败；异常本身不承诺旧输出已回滚。|
|[`BudgetExceededError`](#api-BudgetExceededError)|表示新分析层估算RAM或累计磁盘暂存超过显式限额。|
|[`ResultClosedError`](#api-ResultClosedError)|表示结果已经关闭，不能再创建迭代器、读取或发布。|
|[`ResultFormatError`](#api-ResultFormatError)|表示暂存行版本、结构或带有明确类型的事实非法；禁止静默补值。|
|[`ContributionsUnavailableError`](#api-ContributionsUnavailableError)|表示本次选择不生成贡献明细；应改为full重新运行，不能把缺失明细当作零条计算。|

<a id="api-AnalysisError"></a>
## `AnalysisError`

表示分析或结果交付失败；异常本身不承诺旧输出已回滚。

```python
class AnalysisError(RuntimeError)
```

继承关系：RuntimeError。下表列本类声明的字段；基类字段及其约束见对应类型链接。


源码：[`src/chronaxis/results/errors.py:8`](../../../src/chronaxis/results/errors.py#L8)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-BudgetExceededError"></a>
## `BudgetExceededError`

表示新分析层估算RAM或累计磁盘暂存超过显式限额。

```python
class BudgetExceededError(AnalysisError)
```

继承关系：[AnalysisError](chronaxis.results.errors.md#api-AnalysisError)。下表列本类声明的字段；基类字段及其约束见对应类型链接。


源码：[`src/chronaxis/results/errors.py:12`](../../../src/chronaxis/results/errors.py#L12)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ResultClosedError"></a>
## `ResultClosedError`

表示结果已经关闭，不能再创建迭代器、读取或发布。

```python
class ResultClosedError(AnalysisError)
```

继承关系：[AnalysisError](chronaxis.results.errors.md#api-AnalysisError)。下表列本类声明的字段；基类字段及其约束见对应类型链接。


源码：[`src/chronaxis/results/errors.py:16`](../../../src/chronaxis/results/errors.py#L16)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ResultFormatError"></a>
## `ResultFormatError`

表示暂存行版本、结构或带有明确类型的事实非法；禁止静默补值。

```python
class ResultFormatError(AnalysisError)
```

继承关系：[AnalysisError](chronaxis.results.errors.md#api-AnalysisError)。下表列本类声明的字段；基类字段及其约束见对应类型链接。


源码：[`src/chronaxis/results/errors.py:20`](../../../src/chronaxis/results/errors.py#L20)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-ContributionsUnavailableError"></a>
## `ContributionsUnavailableError`

表示本次选择不生成贡献明细；应改为full重新运行，不能把缺失明细当作零条计算。

```python
class ContributionsUnavailableError(AnalysisError)
```

继承关系：[AnalysisError](chronaxis.results.errors.md#api-AnalysisError)。下表列本类声明的字段；基类字段及其约束见对应类型链接。


源码：[`src/chronaxis/results/errors.py:24`](../../../src/chronaxis/results/errors.py#L24)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
