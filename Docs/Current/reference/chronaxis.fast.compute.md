# `chronaxis.fast.compute`

把单帧数值公式准备成直接读取解码字典的函数，按原始到达顺序累计。

修复版 base 可传只含原生数值尺度的算式；配置入口另传公共编译器核过的
program，以保留 v4 在表达式内部插入的单位换算。两条路径都不执行用户代码。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 对象导航

|对象|用途|
|---|---|
|[`_float`](#api-_float)|转换有限且可精确转双精度的数值；拒绝 bool 和非有限值。|
|[`_typed`](#api-_typed)|检查定宽整数范围、整数性或双精度可表示性，返回目标原生数值。|
|[`_number_type`](#api-_number_type)|为已检查的数值常量确定低层公式的自然类型。|
|[`_affine`](#api-_affine)|按一个完整仿射变换检查最终类型，允许摄氏到开尔文的合法抵消。|
|[`encode_program`](#api-encode_program)|将公共 ExprNode 的数值子集编码为普通 dict。其他操作准备时即拒绝。|
|[`_syntax`](#api-_syntax)|将受限的原尺度公式转换为节点；不解析属性、容器或任意函数。|
|[`_syntax.literal`](#api-_syntax-literal)||
|[`_syntax.visit`](#api-_syntax-visit)||
|[`_bind`](#api-_bind)|在准备阶段创建标量运算函数，运行时只传当帧的解码字典。|
|[`_Accumulator`](#api-_Accumulator)|按原顺序累加已经求好的贡献，不解析公式或保存解码字段。|
|[`_Accumulator.__init__`](#api-_Accumulator-__init__)|读取结果名称和单位；新累计器没有观测值，不把空输入记为零。|
|[`_Accumulator.add`](#api-_Accumulator-add)|提交一条已核验贡献；溢出时保留此前累计及计数，原异常传播。|
|[`_Accumulator.result`](#api-_Accumulator-result)|返回当前业务行；区分没有目标、空方向桶和贡献相消。|
|[`_Metric`](#api-_Metric)|当前累计器及其已准备公式；FileContributions只调用无状态contribution，会话主进程按原顺序调用add。|
|[`_Metric.__init__`](#api-_Metric-__init__)||
|[`_Metric.consume`](#api-_Metric-consume)|消费一条已匹配记录。除零、溢出或缺值直接使本文件失败。|
|[`_Metric.contribution`](#api-_Metric-contribution)|只求当前帧贡献和方向选择，不修改累计状态。|
|[`prepare_metric`](#api-prepare_metric)|创建一个计算项的求值/累计状态。参数为简单声明字典；拒绝冲突别名和未知指令。|
|[`_prepare_program_metric`](#api-_prepare_program_metric)|绑定内部已检查的指令，不重新解析原公式。|
|[`_check_program_spec`](#api-_check_program_spec)|为低层会话检查一次文本及指令，并返回带指令的新声明。|

<a id="api-_float"></a>
## `_float`

转换有限且可精确转双精度的数值；拒绝 bool 和非有限值。

```python
_float(value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|int &#124; float|是|无|位置或关键字。要检查的数值，按本操作约束核验类型、精度和有限性。|

源码：[`src/chronaxis/fast/compute.py:17`](../../../src/chronaxis/fast/compute.py#L17)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_typed"></a>
## `_typed`

检查定宽整数范围、整数性或双精度可表示性，返回目标原生数值。

```python
_typed(value, dtype)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|int &#124; float|是|无|位置或关键字。要检查的数值，按本操作约束核验类型、精度和有限性。|
|`dtype`|str|是|无|位置或关键字。要得到的 int64、uint64 或 float64，决定合法范围与转换规则。|

源码：[`src/chronaxis/fast/compute.py:27`](../../../src/chronaxis/fast/compute.py#L27)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_number_type"></a>
## `_number_type`

为已检查的数值常量确定低层公式的自然类型。

```python
_number_type(value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|int &#124; float|是|无|位置或关键字。要检查的数值，按本操作约束核验类型、精度和有限性。|

源码：[`src/chronaxis/fast/compute.py:39`](../../../src/chronaxis/fast/compute.py#L39)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_affine"></a>
## `_affine`

按一个完整仿射变换检查最终类型，允许摄氏到开尔文的合法抵消。

```python
_affine(value, scale, offset, dtype)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|int &#124; float|是|无|位置或关键字。要检查的数值，按本操作约束核验类型、精度和有限性。|
|`scale`|int &#124; float|是|无|位置或关键字。输入值的乘数，在加偏移前应用。|
|`offset`|int &#124; float|是|无|位置或关键字。乘倍率后增加的偏移，与输出类型一起核验。|
|`dtype`|str|是|无|位置或关键字。要得到的 int64、uint64 或 float64，决定合法范围与转换规则。|

源码：[`src/chronaxis/fast/compute.py:51`](../../../src/chronaxis/fast/compute.py#L51)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-encode_program"></a>
## `encode_program`

将公共 ExprNode 的数值子集编码为普通 dict。其他操作准备时即拒绝。

```python
encode_program(node)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`node`|ExprNode|是|无|位置或关键字。已通过类型和单位检查的表达式节点，编码后传给文件进程。|

源码：[`src/chronaxis/fast/compute.py:61`](../../../src/chronaxis/fast/compute.py#L61)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_syntax"></a>
## `_syntax`

将受限的原尺度公式转换为节点；不解析属性、容器或任意函数。

```python
_syntax(text, signals, parameters)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`text`|str|是|无|位置或关键字。仅使用已支持算术及绑定名的逐帧公式。|
|`signals`|dict|是|无|位置或关键字。别名到本帧 DBC 信号、数值类型和线性变换的映射。|
|`parameters`|dict|是|无|位置或关键字。公式引用的有限数值常量，名称不能与信号冲突。|

源码：[`src/chronaxis/fast/compute.py:78`](../../../src/chronaxis/fast/compute.py#L78)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_syntax-literal"></a>
### `_syntax.literal`



```python
_syntax.literal(value)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|int &#124; float|是|无|位置或关键字。要检查的数值，按本操作约束核验类型、精度和有限性。|

源码：[`src/chronaxis/fast/compute.py:86`](../../../src/chronaxis/fast/compute.py#L86)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_syntax-visit"></a>
### `_syntax.visit`



```python
_syntax.visit(node)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`node`|ast.AST|是|无|位置或关键字。正在检查的语法树节点，仅接受数值算术和受支持的名称。|

源码：[`src/chronaxis/fast/compute.py:89`](../../../src/chronaxis/fast/compute.py#L89)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_bind"></a>
## `_bind`

在准备阶段创建标量运算函数，运行时只传当帧的解码字典。

```python
_bind(node, signals, depth=0)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`node`|dict|是|无|位置或关键字。已经编码的数值操作、类型、参数和输入子指令。|
|`signals`|dict|是|无|位置或关键字。别名到本帧 DBC 信号、数值类型和线性变换的映射。|
|`depth`|int|否|0|位置或关键字。当前绑定的指令嵌套深度，用来限制递归。|

源码：[`src/chronaxis/fast/compute.py:115`](../../../src/chronaxis/fast/compute.py#L115)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_Accumulator"></a>
## `_Accumulator`

按原顺序累加已经求好的贡献，不解析公式或保存解码字段。

```python
_Accumulator(spec)
```


源码：[`src/chronaxis/fast/compute.py:159`](../../../src/chronaxis/fast/compute.py#L159)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_Accumulator-__init__"></a>
### `_Accumulator.__init__`

读取结果名称和单位；新累计器没有观测值，不把空输入记为零。

```python
_Accumulator.__init__(spec)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|dict[str, object]|是|无|位置或关键字。当前计算项的内部声明，读取 name 和 unit；累计值及观测计数从空状态开始。|

源码：[`src/chronaxis/fast/compute.py:162`](../../../src/chronaxis/fast/compute.py#L162)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_Accumulator-add"></a>
### `_Accumulator.add`

提交一条已核验贡献；溢出时保留此前累计及计数，原异常传播。

```python
_Accumulator.add(contribution, keep)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`contribution`|float|是|无|位置或关键字。已求值、换算和检查的当前帧贡献；入选时按原顺序加入总量。|
|`keep`|bool|是|无|位置或关键字。当前帧是否进入所选方向桶；False 仍增加匹配计数，不增加入选数或总量。|

源码：[`src/chronaxis/fast/compute.py:168`](../../../src/chronaxis/fast/compute.py#L168)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_Accumulator-result"></a>
### `_Accumulator.result`

返回当前业务行；区分没有目标、空方向桶和贡献相消。

```python
_Accumulator.result()
```

参数：无显式参数。


源码：[`src/chronaxis/fast/compute.py:175`](../../../src/chronaxis/fast/compute.py#L175)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_Metric"></a>
## `_Metric`

当前累计器及其已准备公式；FileContributions只调用无状态contribution，会话主进程按原顺序调用add。

```python
_Metric(spec, formula)
```

继承关系：[_Accumulator](chronaxis.fast.compute.md#api-_Accumulator)。下表列本类声明的字段；基类字段及其约束见对应类型链接。


源码：[`src/chronaxis/fast/compute.py:182`](../../../src/chronaxis/fast/compute.py#L182)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_Metric-__init__"></a>
### `_Metric.__init__`



```python
_Metric.__init__(spec, formula)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|dict|是|无|位置或关键字。一个指标的绑定、公式、输出尺度和可选方向桶。|
|`formula`|Callable|是|无|位置或关键字。已绑定的数值函数，输入当前帧的物理解码字典。|

源码：[`src/chronaxis/fast/compute.py:185`](../../../src/chronaxis/fast/compute.py#L185)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_Metric-consume"></a>
### `_Metric.consume`

消费一条已匹配记录。除零、溢出或缺值直接使本文件失败。

```python
_Metric.consume(decoded)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`decoded`|dict|是|无|位置或关键字。当前 DBC 报文的信号名到物理值映射，供求值后按原方向分桶。|

源码：[`src/chronaxis/fast/compute.py:196`](../../../src/chronaxis/fast/compute.py#L196)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_Metric-contribution"></a>
### `_Metric.contribution`

只求当前帧贡献和方向选择，不修改累计状态。

```python
_Metric.contribution(decoded)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`decoded`|dict[str, int &#124; float]|是|无|位置或关键字。当前帧的DBC物理解码值；先计算贡献，再按原解码方向判断是否入选。|

#### 返回说明

(float64贡献, bool入选)。

#### 异常说明

类型、单位换算、公式或方向值错误；未入桶也必须先求值。

源码：[`src/chronaxis/fast/compute.py:201`](../../../src/chronaxis/fast/compute.py#L201)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-prepare_metric"></a>
## `prepare_metric`

创建一个计算项的求值/累计状态。参数为简单声明字典；拒绝冲突别名和未知指令。

```python
prepare_metric(spec)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|dict|是|无|位置或关键字。一个指标的绑定、公式、输出尺度和可选方向桶。|

源码：[`src/chronaxis/fast/compute.py:218`](../../../src/chronaxis/fast/compute.py#L218)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_prepare_program_metric"></a>
## `_prepare_program_metric`

绑定内部已检查的指令，不重新解析原公式。

```python
_prepare_program_metric(spec)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|dict[str, object]|是|无|位置或关键字。来自公共编译器或已检查低层会话的内部计算项，包含 signals、parameters 和 program。|

### 返回说明

每文件独立的求值/累计状态。

### 异常说明

指令、类型或数值声明错误。
仅内部调用；普通字典入口仍通过 prepare_metric 检查文本，即使带有 program。

源码：[`src/chronaxis/fast/compute.py:227`](../../../src/chronaxis/fast/compute.py#L227)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_check_program_spec"></a>
## `_check_program_spec`

为低层会话检查一次文本及指令，并返回带指令的新声明。

```python
_check_program_spec(spec)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`spec`|dict[str, object]|是|无|位置或关键字。低层计算项原声明；即使含 program 也先检查 expr，返回带指令的浅复制，不修改原字典。|

### 返回说明

浅复制的内部声明。

### 异常说明

与 prepare_metric 相同；非法文本不能借合法 program 绕过检查。

源码：[`src/chronaxis/fast/compute.py:240`](../../../src/chronaxis/fast/compute.py#L240)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

## 内部匿名回调


<a id="lambda-124"></a>
### 第124行匿名函数

```python
lambda values: constant
```

|参数|含义|返回/异常|
|---|---|---|
|`values`|当前目标帧的 DBC 物理值字典；常量节点不读取它。|返回准备阶段核验过的有限常量。|

<a id="lambda-136"></a>
### 第136行匿名函数

```python
lambda values: _affine(_typed(values[key], original), scale, offset, dtype)
```

|参数|含义|返回/异常|
|---|---|---|
|`values`|当前目标帧的 DBC 物理值字典；常量节点不读取它。|对已经解码的数值应用本次显式变换，并检查输出可表示性。|

<a id="lambda-143"></a>
### 第143行匿名函数

```python
lambda values: _typed(combine(left(values), right(values)), dtype)
```

|参数|含义|返回/异常|
|---|---|---|
|`values`|当前目标帧的 DBC 物理值字典；常量节点不读取它。|按已知整数类型执行运算，溢出时拒绝。|

<a id="lambda-135"></a>
### 第135行匿名函数

```python
lambda values: _typed(values[key], dtype)
```

|参数|含义|返回/异常|
|---|---|---|
|`values`|当前目标帧的 DBC 物理值字典；常量节点不读取它。|返回该信号在当前 DBC 帧的指定类型数值。|

<a id="lambda-142"></a>
### 第142行匿名函数

```python
lambda values: _float(combine(_float(left(values)), _float(right(values))))
```

|参数|含义|返回/异常|
|---|---|---|
|`values`|当前目标帧的 DBC 物理值字典；常量节点不读取它。|以双精度执行左右操作数的算术，检查精度和有限性。|

<a id="lambda-147"></a>
### 第147行匿名函数

```python
lambda values: _float(child(values))
```

|参数|含义|返回/异常|
|---|---|---|
|`values`|当前目标帧的 DBC 物理值字典；常量节点不读取它。|安全转换子表达式为 float64。|

<a id="lambda-150"></a>
### 第150行匿名函数

```python
lambda values: _typed(unary(child(values)), dtype)
```

|参数|含义|返回/异常|
|---|---|---|
|`values`|当前目标帧的 DBC 物理值字典；常量节点不读取它。|执行一元操作并验证类型及溢出。|

<a id="lambda-155"></a>
### 第155行匿名函数

```python
lambda values: _affine(child(values), scale, offset, dtype)
```

|参数|含义|返回/异常|
|---|---|---|
|`values`|当前目标帧的 DBC 物理值字典；常量节点不读取它。|换算子表达式的单位和偏移，检查输出类型。|
