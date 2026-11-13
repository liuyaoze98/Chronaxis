# `chronaxis.core.types`

定义信号类型、时间坐标、三值条件和质量原因，供模型及计算层共用。

模型接收明确的枚举成员；质量原因以固定的整数位保存，允许组合已知位，
拒绝未知位。Truth区分条件成立、不成立和无法确定三种结果，禁止直接转为
Python布尔值。SignalDType声明值类型，TimeType区分相对坐标与UTC绝对坐标。
本模块只依赖标准库，不读取数据或文件，不持有会话状态；SourceType当前
只描述内存输入。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 对象导航

|对象|用途|
|---|---|
|[`Truth`](#api-Truth)|保存条件成立、不成立或无法确定的三种结果。|
|[`Truth.__bool__`](#api-Truth-__bool__)|阻止三个枚举成员被Python统一当作True。|
|[`QualityFlag`](#api-QualityFlag)|用固定整数位保存样本无效或质量受限的原因。|
|[`QualityFlag._missing_`](#api-QualityFlag-_missing_)|检查候选质量位值，再由标准库构造合法的位组合。|
|[`SignalDType`](#api-SignalDType)|声明信号值的逻辑类型，供模型和数值运算检查使用。|
|[`TimeType`](#api-TimeType)|区分相对来源坐标和UTC绝对坐标，保留显式起点依据。|
|[`SourceType`](#api-SourceType)|标明当前内存模型接受的数据来源种类。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from enum import Enum, FlagBoundary, IntFlag
```

</details>

<a id="api-Truth"></a>
## `Truth`

保存条件成立、不成立或无法确定的三种结果。

TRUE和FALSE表示已有充分证据；UNKNOWN表示缺失、过期或无法有效求值。
成员不可变，任何成员都禁止隐式转为Python布尔值，调用者须明确处理三种结果。

```python
class Truth(Enum)
```

继承关系：Enum。下表列本类声明的字段；基类字段及其约束见对应类型链接。

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`TRUE`|枚举成员|类成员，不作为构造参数填写|'true'|已知且条件成立。|
|`FALSE`|枚举成员|类成员，不作为构造参数填写|'false'|已知且条件不成立。|
|`UNKNOWN`|枚举成员|类成员，不作为构造参数填写|'unknown'|缺失、过期或无法有效求值。|

源码：[`src/chronaxis/core/types.py:14`](../../../src/chronaxis/core/types.py#L14)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-Truth-__bool__"></a>
### `Truth.__bool__`

阻止三个枚举成员被Python统一当作True。

```python
Truth.__bool__() -> bool
```

参数：无显式参数。


#### 参数说明

无额外参数；当前三值结果。

#### 返回说明

无正常返回；须显式比较Truth成员。

#### 异常说明

TypeError；三值逻辑尚未由普通Python bool表达。

本函数直接报告的具体错误：

- `TypeError`：Truth不能隐式转bool，请显式处理TRUE/FALSE/UNKNOWN。

返回类型：bool。

源码：[`src/chronaxis/core/types.py:25`](../../../src/chronaxis/core/types.py#L25)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-QualityFlag"></a>
## `QualityFlag`

用固定整数位保存样本无效或质量受限的原因。

多个原因可以组合；基础策略拒绝所有非零位。NONE表示没有记录原因，
仍需结合valid判断有效性。最高位为256，数组至少需要16位保存全部标志；
构造时拒绝负值和未知位。

```python
class QualityFlag(IntFlag)
```

继承关系：IntFlag。下表列本类声明的字段；基类字段及其约束见对应类型链接。

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`NONE`|枚举成员|类成员，不作为构造参数填写|0|没有已记录原因，不证明来源能力完整。|
|`MISSING`|枚举成员|类成员，不作为构造参数填写|1|缺少所需观测。|
|`STALE`|枚举成员|类成员，不作为构造参数填写|2|观测超过有效期。|
|`DECODE_ERROR`|枚举成员|类成员，不作为构造参数填写|4|来源解析或解码失败。|
|`NONFINITE`|枚举成员|类成员，不作为构造参数填写|8|数值NaN或无穷。|
|`OUT_OF_RANGE`|枚举成员|类成员，不作为构造参数填写|16|超过明确业务范围。|
|`ESTIMATED`|枚举成员|类成员，不作为构造参数填写|32|显式估计值，首版基础策略也禁止。|
|`OVERFLOW`|枚举成员|类成员，不作为构造参数填写|64|定宽运算上溢或下溢，回绕结果不能作为有效值。|
|`PRECISION_LOSS`|枚举成员|类成员，不作为构造参数填写|128|不能精确表示的数值转换。|
|`DOMAIN_ERROR`|枚举成员|类成员，不作为构造参数填写|256|除零等值域错误。|

源码：[`src/chronaxis/core/types.py:36`](../../../src/chronaxis/core/types.py#L36)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-QualityFlag-_missing_"></a>
### `QualityFlag._missing_`

检查候选质量位值，再由标准库构造合法的位组合。

```python
QualityFlag._missing_(value)
```

装饰器：`classmethod`。

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|int|是|无|位置或关键字。候选质量位组合，必须是非负整数并且不含未定义位；例如MISSING与NONFINITE可以按位或组合。|

#### 返回说明

QualityFlag或None: 合法组合由IntFlag构造；其他输入遵循标准库协议。

#### 异常说明

ValueError: 候选值为负数、包含未知位或不能构造为合法质量值。

本函数直接报告的具体错误：

- `ValueError`：quality mask必须非负。

源码：[`src/chronaxis/core/types.py:56`](../../../src/chronaxis/core/types.py#L56)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-SignalDType"></a>
## `SignalDType`

声明信号值的逻辑类型，供模型和数值运算检查使用。

整数明确分为int64和uint64，浮点使用float64。bool独立于整数，enum使用
显式标签域；类型不会根据Python继承关系或NumPy自动类型提升推断。

```python
class SignalDType(Enum)
```

继承关系：Enum。下表列本类声明的字段；基类字段及其约束见对应类型链接。

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`INT64`|枚举成员|类成员，不作为构造参数填写|'int64'|有符号64位整数。|
|`UINT64`|枚举成员|类成员，不作为构造参数填写|'uint64'|无符号64位整数。|
|`FLOAT64`|枚举成员|类成员，不作为构造参数填写|'float64'|有限双精度浮点，不隐式转大整数。|
|`BOOL`|枚举成员|类成员，不作为构造参数填写|'bool'|明确布尔值，不按任意数值的Python真值判断。|
|`ENUM`|枚举成员|类成员，不作为构造参数填写|'enum'|显式枚举标签，不参与一般数值运算。|

源码：[`src/chronaxis/core/types.py:82`](../../../src/chronaxis/core/types.py#L82)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-TimeType"></a>
## `TimeType`

区分相对来源坐标和UTC绝对坐标，保留显式起点依据。

不读取机器时区，不自动把相对0当作UTC epoch。

```python
class TimeType(Enum)
```

继承关系：Enum。下表列本类声明的字段；基类字段及其约束见对应类型链接。

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`RELATIVE`|枚举成员|类成员，不作为构造参数填写|'relative'|需要来源声明origin。|
|`ABSOLUTE`|枚举成员|类成员，不作为构造参数填写|'absolute'|已规范化UTC epoch纳秒。|

源码：[`src/chronaxis/core/types.py:96`](../../../src/chronaxis/core/types.py#L96)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-SourceType"></a>
## `SourceType`

标明当前内存模型接受的数据来源种类。

MEMORY表示调用者直接提供已转换为纳秒的内存行。本枚举没有可变注册表，
不会因为声明一个外部来源名称就自动读取或解码该来源。

```python
class SourceType(Enum)
```

继承关系：Enum。下表列本类声明的字段；基类字段及其约束见对应类型链接。

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`MEMORY`|枚举成员|类成员，不作为构造参数填写|'memory'|已声明纳秒的内存行，不执行旧读写或解码。|

源码：[`src/chronaxis/core/types.py:106`](../../../src/chronaxis/core/types.py#L106)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
