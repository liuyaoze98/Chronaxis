# `chronaxis._control_models`

三条内部控制通道的固定模型转换；协议仅接受这里显式列出的构造器。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[ASCSpec](chronaxis.sources.asc.md#api-ASCSpec)、[BLFSpec](chronaxis.sources.blf.md#api-BLFSpec)、[BatchJobResult](chronaxis.batch.models.md#api-BatchJobResult)、[CANCSVLayout](chronaxis.sources.raw_csv_layout.md#api-CANCSVLayout)、[CANCSVSpec](chronaxis.sources.raw_csv.md#api-CANCSVSpec)、[CANTextSpec](chronaxis.sources.text_can_spec.md#api-CANTextSpec)、[CSVTimeSpec](chronaxis.sources.raw_csv.md#api-CSVTimeSpec)、[ColumnMapping](chronaxis.sources.raw_csv_layout.md#api-ColumnMapping)、[FrameRebuildRule](chronaxis.results.frame_patch.md#api-FrameRebuildRule)、[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)、[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition)

## 对象导航

|对象|用途|
|---|---|
|[`native`](#api-native)|复制控制值为有限JSON树。|
|[`keys`](#api-keys)|核对模型的完整字段集合。|
|[`extract`](#api-extract)|摘取固定模型的明确字段。|
|[`_scalar`](#api-_scalar)|编码信号无效值标记。|
|[`_restore_scalar`](#api-_restore_scalar)|恢复信号无效值标记。|
|[`pack_signal`](#api-pack_signal)|展开已冻结信号声明。|
|[`restore_signal`](#api-restore_signal)|恢复明确的信号声明。|
|[`pack_input`](#api-pack_input)|展开一个CAN文件输入。|
|[`restore_input`](#api-restore_input)|恢复一个CAN文件输入。|
|[`pack_source`](#api-pack_source)|展开单次CAN来源。|
|[`restore_source`](#api-restore_source)|恢复单文件CAN来源。|
|[`pack_options`](#api-pack_options)|展开CAN读取关键字。|
|[`restore_options`](#api-restore_options)|恢复CAN读取关键字。|
|[`pack_frame_context`](#api-pack_frame_context)|展开所需帧重建声明。|
|[`restore_frame_context`](#api-restore_frame_context)|恢复固定帧重建上下文。|
|[`pack_result`](#api-pack_result)|展开无活动资源的批量结果。|
|[`restore_result`](#api-restore_result)|恢复批量任务结果事实。|
|[`pack_message`](#api-pack_message)|展开固定控制命令的参数。|
|[`restore_message`](#api-restore_message)|恢复固定命令参数。|
|[`_object`](#api-_object)|核对有限对象字段。|
|[`_program`](#api-_program)|核对已有数值指令形状。|
|[`check_fast_spec`](#api-check_fast_spec)|核对有限fast文件声明。|
|[`_check_fast_rows`](#api-_check_fast_rows)|检查快速批量总量所用的固定五字段结果。|
|[`check_message_fields`](#api-check_message_fields)|核对大消息的固定字段。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from collections.abc import Mapping
from math import isfinite
from pathlib import Path
```

</details>

<a id="api-native"></a>
## `native`

复制控制值为有限JSON树。

```python
native(value, depth=0)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|None &#124; bool &#124; int &#124; float &#124; str &#124; Mapping[str, Any] &#124; list &#124; tuple|是|无|位置或关键字。要复制的原生树；映射键必须是字符串，浮点值必须有限，tuple转换为list，不接受自定义模型。|
|`depth`|int|否|0|位置或关键字。当前递归层数，入口为0，每经过一层容器加1；超过320时拒绝。|

### 返回说明

独立list/dict及原生标量。

### 异常说明

类型、深度或非有限数错误。

源码：[`src/chronaxis/_control_models.py:21`](../../../src/chronaxis/_control_models.py#L21)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-keys"></a>
## `keys`

核对模型的完整字段集合。

```python
keys(data, names)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`data`|dict[str, Any]|是|无|位置或关键字。待检查的模型字段字典；字段集合必须与names完全相等，不允许缺项或多项。|
|`names`|Sequence[str]|是|无|位置或关键字。调用点写定的全部必需字段名，用来比对data的键集合。|

### 返回说明

原字典。

### 异常说明

缺项、多项或非字典时ValueError。

源码：[`src/chronaxis/_control_models.py:45`](../../../src/chronaxis/_control_models.py#L45)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-extract"></a>
## `extract`

摘取固定模型的明确字段。

```python
extract(value, names)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition) &#124; [ASCSpec](chronaxis.sources.asc.md#api-ASCSpec) &#124; [CANCSVLayout](chronaxis.sources.raw_csv_layout.md#api-CANCSVLayout) &#124; [ColumnMapping](chronaxis.sources.raw_csv_layout.md#api-ColumnMapping) &#124; [CSVTimeSpec](chronaxis.sources.raw_csv.md#api-CSVTimeSpec) &#124; [FrameRebuildRule](chronaxis.results.frame_patch.md#api-FrameRebuildRule) &#124; [BatchJobResult](chronaxis.batch.models.md#api-BatchJobResult)|是|无|位置或关键字。由调用点选定的固定模型；只读取names列出的属性，不发现任意对象类型。|
|`names`|Sequence[str]|是|无|位置或关键字。本次需要摘取的属性名序列；返回字典使用同名键，属性缺失时保留AttributeError。|

### 返回说明

字段名到原值的dict。

### 异常说明

缺少已声明属性时AttributeError。

源码：[`src/chronaxis/_control_models.py:57`](../../../src/chronaxis/_control_models.py#L57)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_scalar"></a>
## `_scalar`

编码信号无效值标记。

```python
_scalar(value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|None &#124; str &#124; bool &#124; int &#124; float|是|无|位置或关键字。信号invalid_values中的一个原生标记；浮点以hex文本保留NaN、Inf和原类型，其他原生值使用value标记。|

### 返回说明

二元素列表，分别为固定种类及无损原值。

### 异常说明

未支持类型时ValueError。

源码：[`src/chronaxis/_control_models.py:67`](../../../src/chronaxis/_control_models.py#L67)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_restore_scalar"></a>
## `_restore_scalar`

恢复信号无效值标记。

```python
_restore_scalar(data)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`data`|list[str &#124; bool &#124; int &#124; None]|是|无|位置或关键字。二元素列表：第一项是float或value标记，第二项是浮点hex文本或对应原生标量；不接受额外元素。|

### 返回说明

原生标量，保留float与整数区别。

### 异常说明

种类、数量或浮点文本非法时ValueError。

源码：[`src/chronaxis/_control_models.py:81`](../../../src/chronaxis/_control_models.py#L81)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-pack_signal"></a>
## `pack_signal`

展开已冻结信号声明。

```python
pack_signal(signal)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`signal`|[SignalDefinition](chronaxis.core.binding.md#api-SignalDefinition)|是|无|位置或关键字。已冻结的信号声明；按_SIGNAL写定字段展开，dtype转名称，invalid_values用专用标量标记。|

### 返回说明

JSON原生字段字典。

### 异常说明

模型类型或字段值非法。

源码：[`src/chronaxis/_control_models.py:97`](../../../src/chronaxis/_control_models.py#L97)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-restore_signal"></a>
## `restore_signal`

恢复明确的信号声明。

```python
restore_signal(value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|dict[str, Any]|是|无|位置或关键字。包含_SIGNAL全部且仅这些字段的原生字典；dtype名称、枚举对、无效标记等恢复后由SignalDefinition再次核约束。|

### 返回说明

SignalDefinition，其派生单位状态由构造重新核对。

### 异常说明

字段、dtype或模型约束错误。

源码：[`src/chronaxis/_control_models.py:114`](../../../src/chronaxis/_control_models.py#L114)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-pack_input"></a>
## `pack_input`

展开一个CAN文件输入。

```python
pack_input(item)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`item`|[ASCSpec](chronaxis.sources.asc.md#api-ASCSpec) &#124; [BLFSpec](chronaxis.sources.blf.md#api-BLFSpec) &#124; [CANCSVSpec](chronaxis.sources.raw_csv.md#api-CANCSVSpec)|是|无|位置或关键字。一个已确定格式的输入声明；只展开相应固定字段和路径文本，不打开文件。|

### 返回说明

固定种类及字段字典的二元素列表。

### 异常说明

未知输入类型时TypeError。

源码：[`src/chronaxis/_control_models.py:132`](../../../src/chronaxis/_control_models.py#L132)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-restore_input"></a>
## `restore_input`

恢复一个CAN文件输入。

```python
restore_input(data)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`data`|list[Any]|是|无|位置或关键字。恰好两项：asc/blf/csv种类标记和该种类的完整字段字典；路径恢复为Path。|

### 返回说明

ASCSpec、BLFSpec或CANCSVSpec，不读取输入。

### 异常说明

种类、字段或原模型约束错误。

源码：[`src/chronaxis/_control_models.py:157`](../../../src/chronaxis/_control_models.py#L157)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-pack_source"></a>
## `pack_source`

展开单次CAN来源。

```python
pack_source(source)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`source`|[CANTextSpec](chronaxis.sources.text_can_spec.md#api-CANTextSpec)|是|无|位置或关键字。当前文件任务的CAN来源声明，包含格式输入、DBC路径、通道、时钟和读取政策；不扫描报文。|

### 返回说明

原生字段字典，路径按现有文本保留。

### 异常说明

类型或嵌套模型错误。

源码：[`src/chronaxis/_control_models.py:190`](../../../src/chronaxis/_control_models.py#L190)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-restore_source"></a>
## `restore_source`

恢复单文件CAN来源。

```python
restore_source(value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|dict[str, Any]|是|无|位置或关键字。固定来源字段字典，inputs必须是恰好一份输入的list；恢复CANTextSpec和TimebaseSpec，不读取文件。|

### 返回说明

CANTextSpec，不打开DBC或日志。

### 异常说明

字段、时间类型或输入数量错误。

源码：[`src/chronaxis/_control_models.py:207`](../../../src/chronaxis/_control_models.py#L207)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-pack_options"></a>
## `pack_options`

展开CAN读取关键字。

```python
pack_options(options)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`options`|dict[str, Any]|是|无|位置或关键字。键仅接受_OPTIONS登记的CAN读取选项；周期/元数据定位显式展开，ID集合转列表，回调不可传输。|

### 返回说明

原生字典，周期定位显式展开，ID集合变列表。

### 异常说明

回调、未知关键字或未支持值类型错误。

源码：[`src/chronaxis/_control_models.py:227`](../../../src/chronaxis/_control_models.py#L227)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-restore_options"></a>
## `restore_options`

恢复CAN读取关键字。

```python
restore_options(options)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`options`|dict[str, Any]|是|无|位置或关键字。来自控制消息的白名单选项；定位字典恢复为LegacyCANField，ID列表恢复为tuple。|

### 返回说明

含固定LegacyCANField元组及ID元组的dict。

### 异常说明

未知选项或非法定位模型错误。

源码：[`src/chronaxis/_control_models.py:247`](../../../src/chronaxis/_control_models.py#L247)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-pack_frame_context"></a>
## `pack_frame_context`

展开所需帧重建声明。

```python
pack_frame_context(value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|tuple[tuple[[FrameRebuildRule](chronaxis.results.frame_patch.md#api-FrameRebuildRule), ...], bool, bool] &#124; None|是|无|位置或关键字。None表示无需帧重建；否则依次为重建规则、是否读取周期、是否做完整性记录。|

### 返回说明

None或固定三元素列表。

### 异常说明

非原生字段错误。

源码：[`src/chronaxis/_control_models.py:267`](../../../src/chronaxis/_control_models.py#L267)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-restore_frame_context"></a>
## `restore_frame_context`

恢复固定帧重建上下文。

```python
restore_frame_context(value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|list[Any] &#124; None|是|无|位置或关键字。None或恰好三项的原生列表：规则字典列表、周期开关、完整性开关；后两项必须为bool。|

### 返回说明

None或FrameRebuildRule元组与两个bool。

### 异常说明

字段、开关或规则校验错误。

源码：[`src/chronaxis/_control_models.py:280`](../../../src/chronaxis/_control_models.py#L280)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-pack_result"></a>
## `pack_result`

展开无活动资源的批量结果。

```python
pack_result(result)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`result`|[BatchJobResult](chronaxis.batch.models.md#api-BatchJobResult)|是|无|位置或关键字。没有活动recovery句柄的任务结果；仅展开_RESULT事实字段，输出及清单Path改为文本。|

### 返回说明

固定原生结果字典。

### 异常说明

未知类型或仍持恢复句柄时TypeError。

源码：[`src/chronaxis/_control_models.py:300`](../../../src/chronaxis/_control_models.py#L300)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-restore_result"></a>
## `restore_result`

恢复批量任务结果事实。

```python
restore_result(value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|dict[str, Any]|是|无|位置或关键字。完整_RESULT结果字段字典；指定路径恢复为Path，错误链恢复tuple，recovery保持为空。|

### 返回说明

BatchJobResult，指定路径字段恢复为Path，恢复对象仍为空。

### 异常说明

字段或结果模型约束错误。

源码：[`src/chronaxis/_control_models.py:316`](../../../src/chronaxis/_control_models.py#L316)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-pack_message"></a>
## `pack_message`

展开固定控制命令的参数。

```python
pack_message(family, message)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`family`|str|是|无|位置或关键字。已选控制通道族，只使用can、fast或batch；决定哪些参数按固定模型展开。|
|`message`|tuple[Any, ...] &#124; list[Any]|是|无|位置或关键字。首项为已登记命令，其余为该命令参数；此函数返回展开后的参数列表，不含命令名。|

### 返回说明

JSON原生参数列表。

### 异常说明

未支持对象或固定模型错误。

源码：[`src/chronaxis/_control_models.py:331`](../../../src/chronaxis/_control_models.py#L331)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-restore_message"></a>
## `restore_message`

恢复固定命令参数。

```python
restore_message(family, operation, arguments)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`family`|str|是|无|位置或关键字。can、fast或batch之一，与已校验控制消息头相同，用于选择固定恢复规则。|
|`operation`|str|是|无|位置或关键字。该通道登记的命令名；只恢复此命令写定的模型，不按输入类名构造对象。|
|`arguments`|list[Any]|是|无|位置或关键字。解码后的原生参数列表；按命令核数量及字段，返回时在前面加上operation。|

### 返回说明

现有消费者使用的tuple，仅恢复写定模型。

### 异常说明

数量、类型或模型校验错误。

源码：[`src/chronaxis/_control_models.py:356`](../../../src/chronaxis/_control_models.py#L356)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_object"></a>
## `_object`

核对有限对象字段。

```python
_object(value, required, allowed)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|dict[str, Any]|是|无|位置或关键字。待检查的有限字段对象；函数只核字典类型和键集合，不复制或修改内容。|
|`required`|Collection[str]|是|无|位置或关键字。该对象不可省略的键集合；必须全部出现在value中。|
|`allowed`|Collection[str]|是|无|位置或关键字。该对象全部允许的键集合；value不得包含集合外的键。|

### 返回说明

None，不改输入。

### 异常说明

缺项、未知字段或类型错误。

源码：[`src/chronaxis/_control_models.py:400`](../../../src/chronaxis/_control_models.py#L400)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_program"></a>
## `_program`

核对已有数值指令形状。

```python
_program(value, depth=0)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|dict[str, Any]|是|无|位置或关键字。fast已编译的固定数值指令，包含op、dtype及该操作允许的字段；只检查形状，不重编译表达式。|
|`depth`|int|否|0|位置或关键字。当前指令树递归深度，入口为0；超过128拒绝。|

### 返回说明

None，不重新编译文本表达式。

### 异常说明

未知操作、dtype、参数或深度错误。

源码：[`src/chronaxis/_control_models.py:411`](../../../src/chronaxis/_control_models.py#L411)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-check_fast_spec"></a>
## `check_fast_spec`

核对有限fast文件声明。

```python
check_fast_spec(value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|dict[str, Any]|是|无|位置或关键字。fast单文件原生声明；需path、dbc、channel及非空metrics，其他键和指令按固定白名单核对。|

### 返回说明

None，不加载数据库或运行公式。

### 异常说明

未知字段、缺项或固定指令错误。

源码：[`src/chronaxis/_control_models.py:443`](../../../src/chronaxis/_control_models.py#L443)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_check_fast_rows"></a>
## `_check_fast_rows`

检查快速批量总量所用的固定五字段结果。

```python
_check_fast_rows(rows)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`rows`|list[dict[str, str &#124; int &#124; float &#124; None]] &#124; None|是|无|位置或关键字。None表示未请求或任务失败；否则每行仅含name、unit、value、status、reason五字段，值需有限或None。|

### 返回说明

None；不改数值、名称和顺序，也不限制合法任务的计算项数量。

### 异常说明

未知字段、类型或结果状态错误。

源码：[`src/chronaxis/_control_models.py:480`](../../../src/chronaxis/_control_models.py#L480)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-check_message_fields"></a>
## `check_message_fields`

核对大消息的固定字段。

```python
check_message_fields(family, operation, arguments)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`family`|str|是|无|位置或关键字。can、fast或batch控制族，选择要核的固定大消息规则。|
|`operation`|str|是|无|位置或关键字。本族登记命令；fast文件/EOF及batch任务/结果有各自字段约束。|
|`arguments`|list[Any] &#124; tuple[Any, ...]|是|无|位置或关键字。已通过基础数量检查的命令参数；此处补核计数、固定结果及数值指令，用户分析配置仍交原计划验证。|

### 返回说明

None，用户config仍交原AnalysisPlan验证。

### 异常说明

固定字段、计数、结果状态或指令错误。

源码：[`src/chronaxis/_control_models.py:503`](../../../src/chronaxis/_control_models.py#L503)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
