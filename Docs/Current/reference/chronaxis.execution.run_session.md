# `chronaxis.execution.run_session`

执行一份分析计划：读取来源并保存历史，再生成事件、窗口片段和指标，最后返回统一的结果对象。它还负责将本次资源交给结果对象管理，避免读取结束后文件仍无人关闭。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[AnalysisError](chronaxis.results.errors.md#api-AnalysisError)、[AnalysisPlan](chronaxis.planning.plan.md#api-AnalysisPlan)、[AnalysisResult](chronaxis.results.result.md#api-AnalysisResult)、[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)、[ResourceBudget](chronaxis.results.budget.md#api-ResourceBudget)、[ResultClosedError](chronaxis.results.errors.md#api-ResultClosedError)、[ResultSpool](chronaxis.results.spool.md#api-ResultSpool)、[RunMetadata](chronaxis.results.manifest.md#api-RunMetadata)

## 对象导航

|对象|用途|
|---|---|
|[`RunSession`](#api-RunSession)|负责一次分析运行的读取器、历史文件、事件检测器和结果暂存。它按计划依次启动这些组件，并在成功或失败后关闭自己创建的资源。计划对象由调用方提供，本类不会重新读取或修改计划。|
|[`RunSession.__init__`](#api-RunSession-__init__)|申请有限固定状态，拒绝已有或受保护目录，不读取来源。|
|[`RunSession._require_static_derived`](#api-RunSession-_require_static_derived)|在需求收集和输入动作前复核全部派生声明，不把派生项变成运行根。|
|[`RunSession.closed`](#api-RunSession-closed)|查看本次执行所管理的资源是否已经关闭。|
|[`RunSession.failed`](#api-RunSession-failed)|读取执行或本owner清理失败事实。|
|[`RunSession.work_dir`](#api-RunSession-work_dir)|读取本次已取得的新根。|
|[`RunSession._construct`](#api-RunSession-_construct)|调用真实工厂并立即登记返回owner，失败只接其明确恢复属性。|
|[`RunSession.execute`](#api-RunSession-execute)|读取一次并返回独立AnalysisResult，重复调用或失败后禁止重新扫描。|
|[`RunSession._run_record_calculations`](#api-RunSession-_run_record_calculations)|在原会话资源树内执行按需周期统计，保持一个公开AnalysisRunner。|
|[`RunSession._adopt_cleanup`](#api-RunSession-_adopt_cleanup)|接管当前工厂明确移交的最高资源所有者，保留失败后可重试关闭的责任。|
|[`RunSession._diagnose`](#api-RunSession-_diagnose)|在本次已取得的最终暂存标失败，诊断清理副错只附note。|
|[`RunSession._require_closed`](#api-RunSession-_require_closed)|检查真实close完成及已知费用槽，不让旧提前closed掩盖尚持有资源。|
|[`RunSession._close_slot`](#api-RunSession-_close_slot)|关闭一个最高owner并在成功后才清槽。|
|[`RunSession._close_inputs`](#api-RunSession-_close_inputs)|关闭记录执行树，失败时保留其最高所有者供调用方重试。|
|[`RunSession._clear_contracts`](#api-RunSession-_clear_contracts)|释放本会话借用的有限声明，随后才退还覆盖它们的预算。|
|[`RunSession._release_costs`](#api-RunSession-_release_costs)|逐笔释放本owner真实槽，覆盖释放前后取消。|
|[`RunSession._assert_owned_balance`](#api-RunSession-_assert_owned_balance)|检查执行树已关闭且账本只含本会话及待移交结果费用。|
|[`RunSession.close`](#api-RunSession-close)|可重试关闭本次最高资源和协调费用，保留文件及已移交结果。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from ..planning.plan import AnalysisPlan
from ..planning.legacy_execution import require_can_decode_scope
from ..planning.input_requirements import collect_input_requirements
from ..results.budget import ResourceBudget
from ..results.errors import AnalysisError, ResultClosedError
from ..results.manifest import RunMetadata
from ..results.result import AnalysisResult
from ..results.spool import ResultSpool, _cleanup_owner, _reserve_owned_ram, _release_owned_ram
from .history import _metadata_bytes
from .static_metadata import static_metadata_bytes
```

</details>

<a id="api-RunSession"></a>
## `RunSession`

负责一次分析运行的读取器、历史文件、事件检测器和结果暂存。它按计划依次启动这些组件，并在成功或失败后关闭自己创建的资源。计划对象由调用方提供，本类不会重新读取或修改计划。

```python
RunSession(plan, work_dir=None)
```


源码：[`src/chronaxis/execution/run_session.py:30`](../../../src/chronaxis/execution/run_session.py#L30)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RunSession-__init__"></a>
### `RunSession.__init__`

申请有限固定状态，拒绝已有或受保护目录，不读取来源。

```python
RunSession.__init__(plan, work_dir=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|[AnalysisPlan](chronaxis.planning.plan.md#api-AnalysisPlan)|是|无|位置或关键字。plan为已选实际backend的AnalysisPlan|
|`work_dir`|str &#124; [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path) &#124; None|否|None|位置或关键字。本次运行独占的工作目录，用来保存中间文件。自行指定时要求尚不存在；不会覆盖旧目录。None让入口自动创建唯一目录。|

#### 返回说明

单次执行owner。

#### 异常说明

类型、路径、预算或取消原错；
    持续构造清理失败附runner_cleanup_owner，已有目录不会被写入诊断。

本函数直接报告的具体错误：

- `TypeError`：RunSession需AnalysisPlan及可选新工作路径。

源码：[`src/chronaxis/execution/run_session.py:38`](../../../src/chronaxis/execution/run_session.py#L38)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RunSession-_require_static_derived"></a>
### `RunSession._require_static_derived`

在需求收集和输入动作前复核全部派生声明，不把派生项变成运行根。

```python
RunSession._require_static_derived()
```

参数：无显式参数。


#### 参数说明

无，借用本会话原计划及声明绑定。

#### 返回说明

None；原静态对象、声明顺序和完整身份均须一致，空任务也不省略校验。

#### 异常说明

TypeError/ValueError为带有明确类型的声明或静态对象被替换；预算和取消错误原样传播。
所有解析表、遍历容器和展开树先付到本owner的_fixed_cost槽，构造失败由
原RunSession清理链回收；本方法不创建目录、不打开来源、不生成普通样本。

源码：[`src/chronaxis/execution/run_session.py:105`](../../../src/chronaxis/execution/run_session.py#L105)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RunSession-closed"></a>
### `RunSession.closed`

查看本次执行所管理的资源是否已经关闭。

```python
RunSession.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象的关闭已完成；False表示尚未关闭完毕。

#### 异常说明

无。

源码：[`src/chronaxis/execution/run_session.py:166`](../../../src/chronaxis/execution/run_session.py#L166)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RunSession-failed"></a>
### `RunSession.failed`

读取执行或本owner清理失败事实。

```python
RunSession.failed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

True表示本对象已记录处理失败；False表示尚未记录失败。

#### 异常说明

无。

源码：[`src/chronaxis/execution/run_session.py:172`](../../../src/chronaxis/execution/run_session.py#L172)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RunSession-work_dir"></a>
### `RunSession.work_dir`

读取本次已取得的新根。

```python
RunSession.work_dir
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

Path或构造未取得时None。

#### 异常说明

无。

源码：[`src/chronaxis/execution/run_session.py:178`](../../../src/chronaxis/execution/run_session.py#L178)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RunSession-_construct"></a>
### `RunSession._construct`

调用真实工厂并立即登记返回owner，失败只接其明确恢复属性。

```python
RunSession._construct(slot, factory, *args, **kwargs)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`slot`|str|是|无|位置或关键字。当前对象中用于保存资源或其费用的属性名，例如"_row_cost"；只能指向本对象实际管理的项。释放成功后才清空对应项。|
|`factory`|Callable|是|无|位置或关键字。固定的内部资源构造器，例如一个读取器类；函数先登记未完成构造的对象，确保失败时仍能关闭。|
|`args`|tuple|否|()|可变位置。按factory的构造签名传入的位置实参，不含self。|
|`kwargs`|dict[str, object]|否|{}|可变关键字。按factory的构造签名传入的关键字实参；名称须由该构造器支持。|

#### 返回说明

实际owner。

#### 异常说明

原工厂错误传播，不对旧半初始化对象调用close。

源码：[`src/chronaxis/execution/run_session.py:183`](../../../src/chronaxis/execution/run_session.py#L183)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RunSession-execute"></a>
### `RunSession.execute`

读取一次并返回独立AnalysisResult，重复调用或失败后禁止重新扫描。

```python
RunSession.execute()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

完成且尚未关闭的AnalysisResult。

#### 异常说明

原执行/预算/取消
    错误保留，普通非AnalysisError由公开AnalysisRunner包装；本方法不反复清理，原错
    附runner_cleanup_owner供公开层统一清理或恢复后close。

源码：[`src/chronaxis/execution/run_session.py:202`](../../../src/chronaxis/execution/run_session.py#L202)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RunSession-_run_record_calculations"></a>
### `RunSession._run_record_calculations`

在原会话资源树内执行按需周期统计，保持一个公开AnalysisRunner。

```python
RunSession._run_record_calculations()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None，完成结果仍由execute统一封存和移交。

#### 异常说明

静态未支持组合在I/O前拒绝，实际子owner统一登记及清理。

源码：[`src/chronaxis/execution/run_session.py:240`](../../../src/chronaxis/execution/run_session.py#L240)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RunSession-_adopt_cleanup"></a>
### `RunSession._adopt_cleanup`

接管当前工厂明确移交的最高资源所有者，保留失败后可重试关闭的责任。

```python
RunSession._adopt_cleanup(exc)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`exc`|BaseException|是|无|位置或关键字。本次操作的原异常，供附加关闭失败信息并保留原因链。不要用错误字符串代替异常对象。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原属性访问错误；不凭字段猜测内层资源。

源码：[`src/chronaxis/execution/run_session.py:290`](../../../src/chronaxis/execution/run_session.py#L290)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RunSession-_diagnose"></a>
### `RunSession._diagnose`

在本次已取得的最终暂存标失败，诊断清理副错只附note。

```python
RunSession._diagnose(exc)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`exc`|BaseException|是|无|位置或关键字。本次操作的原异常，供附加关闭失败信息并保留原因链。不要用错误字符串代替异常对象。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

不替换主异常，不接触未取得或已有根。

源码：[`src/chronaxis/execution/run_session.py:308`](../../../src/chronaxis/execution/run_session.py#L308)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RunSession-_require_closed"></a>
### `RunSession._require_closed`

检查真实close完成及已知费用槽，不让旧提前closed掩盖尚持有资源。

```python
RunSession._require_closed(owner)
```

装饰器：`staticmethod`。

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`owner`|可关闭资源对象|是|无|位置或关键字。刚执行关闭的内部资源，必须报告已关闭状态；仍有资源未释放时阻止会话交付结果。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

AnalysisError为未完成关闭；
    旧深层缺口只据真实槽拒绝，不推测、转移或自行释放未知余额。

本函数直接报告的具体错误：

- `AnalysisError`：内部资源close返回但没有完成关闭。

源码：[`src/chronaxis/execution/run_session.py:323`](../../../src/chronaxis/execution/run_session.py#L323)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RunSession-_close_slot"></a>
### `RunSession._close_slot`

关闭一个最高owner并在成功后才清槽。

```python
RunSession._close_slot(slot)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`slot`|str|是|无|位置或关键字。当前对象中用于保存资源或其费用的属性名，例如"_row_cost"；只能指向本对象实际管理的项。释放成功后才清空对应项。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原关闭错误。

源码：[`src/chronaxis/execution/run_session.py:335`](../../../src/chronaxis/execution/run_session.py#L335)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RunSession-_close_inputs"></a>
### `RunSession._close_inputs`

关闭记录执行树，失败时保留其最高所有者供调用方重试。

```python
RunSession._close_inputs()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原关闭错误；不越过尚未关闭的依赖资源。

源码：[`src/chronaxis/execution/run_session.py:345`](../../../src/chronaxis/execution/run_session.py#L345)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RunSession-_clear_contracts"></a>
### `RunSession._clear_contracts`

释放本会话借用的有限声明，随后才退还覆盖它们的预算。

```python
RunSession._clear_contracts()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

无；不修改调用方计划或已经移交的结果。

源码：[`src/chronaxis/execution/run_session.py:352`](../../../src/chronaxis/execution/run_session.py#L352)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RunSession-_release_costs"></a>
### `RunSession._release_costs`

逐笔释放本owner真实槽，覆盖释放前后取消。

```python
RunSession._release_costs()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原预算错误。

源码：[`src/chronaxis/execution/run_session.py:360`](../../../src/chronaxis/execution/run_session.py#L360)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RunSession-_assert_owned_balance"></a>
### `RunSession._assert_owned_balance`

检查执行树已关闭且账本只含本会话及待移交结果费用。

```python
RunSession._assert_owned_balance()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

AnalysisError为真实内部责任或账本残留。

本函数直接报告的具体错误：

- `AnalysisError`：成功前仍有未关闭内部资源。
- `AnalysisError`：共享RAM账本与实际存活owner费用不一致，拒绝成功移交。

源码：[`src/chronaxis/execution/run_session.py:366`](../../../src/chronaxis/execution/run_session.py#L366)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-RunSession-close"></a>
### `RunSession.close`

可重试关闭本次最高资源和协调费用，保留文件及已移交结果。

```python
RunSession.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None。关闭成功后再次调用不会重复释放同一份资源。

#### 异常说明

原句柄、预算或取消错误附
    runner_cleanup_owner；不会用共享余额抵销旧工厂遗失的费用。

源码：[`src/chronaxis/execution/run_session.py:385`](../../../src/chronaxis/execution/run_session.py#L385)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
