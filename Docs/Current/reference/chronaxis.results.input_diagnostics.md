# `chronaxis.results.input_diagnostics`

保存明确请求的输入检查范围；摘要只覆盖实际交给分析层的记录。

一份来源说明关联必要路径、所需别名、检查范围及可选摘要，不复制输入文件。
本模型不读取数据；EOF和摘要由同次运行提供，不能当成全文件内容证明。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 对象导航

|对象|用途|
|---|---|
|[`InputDiagnostic`](#api-InputDiagnostic)|一个实际来源的有限诊断；记录数与摘要均指同一所需记录流。|
|[`InputDiagnostic.__post_init__`](#api-InputDiagnostic-__post_init__)|核有限范围声明。|
|[`InputDiagnostic.to_dict`](#api-InputDiagnostic-to_dict)|输出一份来源/绑定范围，未请求摘要时不写空摘要栏。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from ..core.validation import require_identifier, require_text
```

</details>

<a id="api-InputDiagnostic"></a>
## `InputDiagnostic`

一个实际来源的有限诊断；记录数与摘要均指同一所需记录流。

```python
class InputDiagnostic
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`source`|str|是|无|当前结果或记录所属的来源名称，必须对应计划中已经定义的source。|
|`source_type`|str|是|无|来源类型：memory为内存记录，signal_csv为解析信号表，can_blf/can_asc/raw_can_csv为三种原始报文。|
|`paths`|tuple[str, ...]|是|无|实际使用的有序来源路径；内存来源可以为空，不重复复制原文件内容。|
|`aliases`|tuple[str, ...]|是|无|实际需要的信号别名；序列用于内部范围校验，发布时通过bindings统一说明。|
|`bindings`|tuple[tuple[str, str], ...]|是|无|每个所需别名及其实际原字段的对应关系，公共来源说明只保存一次。|
|`input_check`|str|是|无|auto按本次依赖选择必要检查；full要求完整来源检查，不等于自动开启所有诊断输出。|
|`time_scope`|str|是|无|none不采集时间；selected处理所需记录时间；source处理完整来源时间，不能混称全日志证明。|
|`record_count`|int|是|无|实际进入该输入诊断范围的记录数，非负；不是无条件等于原文件全部报文数。|
|`source_eof`|bool|是|无|本来源是否确实读到结束；完成的输入诊断要求True。|
|`sha256`|str &#124; None|否|None|明确请求时对所需记录流计算的SHA256文本；未请求时为None且发布时省略该键。|
|`digest_scope`|str|否|'required-decoded-records-v1'|固定required-decoded-records-v1，限定摘要只覆盖交给分析层的所需解码记录，不是原文件字节证明。|

源码：[`src/chronaxis/results/input_diagnostics.py:11`](../../../src/chronaxis/results/input_diagnostics.py#L11)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-InputDiagnostic-__post_init__"></a>
### `InputDiagnostic.__post_init__`

核有限范围声明。

```python
InputDiagnostic.__post_init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

类型/值错误。

源码：[`src/chronaxis/results/input_diagnostics.py:25`](../../../src/chronaxis/results/input_diagnostics.py#L25)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。

<a id="api-InputDiagnostic-to_dict"></a>
### `InputDiagnostic.to_dict`

输出一份来源/绑定范围，未请求摘要时不写空摘要栏。

```python
InputDiagnostic.to_dict()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

dict。

#### 异常说明

无。

源码：[`src/chronaxis/results/input_diagnostics.py:46`](../../../src/chronaxis/results/input_diagnostics.py#L46)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
