# chronaxis.results.readable_format

将已计算的时间、状态和质量格式化为可读文字，不改变计算结果。

输入为精简结果的标量，输出为CSV单元格或清单说明。整数纳秒用整数运算
转换为十进制秒，不经过浮点，不补造日期。此模块无文件和输入读取副作用。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 对象导航

|对象|用途|
|---|---|
|[`seconds`](#api-seconds)|精确转换纳秒，不产生第二套时间值。|
|[`quality_text`](#api-quality_text)|翻译已设置质量位，0不声称数据绝对正确。|
|[`explanation`](#api-explanation)|合并一项结果的必要原因和质量，不把普通ok当作诊断。|
|[`outcome_messages`](#api-outcome_messages)|解释同次分析的轻量概况，不额外寻找未知区间。|

<a id="api-seconds"></a>
## `seconds`

精确转换纳秒，不产生第二套时间值。

```python
seconds(value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|int &#124; None|是|无|位置或关键字。已记录的整数时间或质量位；具体含义见函数说明，不使用浮点时间。|

### 返回说明

最多9位小数的秒文本；None为空字符串。

### 异常说明

TypeError为非整数输入；不接受bool或浮点纳秒。

源码：[`src/chronaxis/results/readable_format.py:37`](../../../src/chronaxis/results/readable_format.py#L37)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-quality_text"></a>
## `quality_text`

翻译已设置质量位，0不声称数据绝对正确。

```python
quality_text(value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|int &#124; None|是|无|位置或关键字。已记录的整数时间或质量位；具体含义见函数说明，不使用浮点时间。|

### 返回说明

中文原因，以分号分隔；0为空。

### 异常说明

类型错误传播；未知位明确保留提示，不能静默丢失。

源码：[`src/chronaxis/results/readable_format.py:53`](../../../src/chronaxis/results/readable_format.py#L53)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-explanation"></a>
## `explanation`

合并一项结果的必要原因和质量，不把普通ok当作诊断。

```python
explanation(row)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`row`|dict|是|无|位置或关键字。已校验的单条平坦结果，包含完整关联身份。|

### 返回说明

中文说明。

### 异常说明

缺失字段错误传播。

源码：[`src/chronaxis/results/readable_format.py:66`](../../../src/chronaxis/results/readable_format.py#L66)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-outcome_messages"></a>
## `outcome_messages`

解释同次分析的轻量概况，不额外寻找未知区间。

```python
outcome_messages(outcome)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`outcome`|AnalysisOutcome &#124; None|是|无|位置或关键字。同次分析已经得到的有限业务概况；None没有说明。|

### 返回说明

每规则一条说明的列表。

### 异常说明

无；有未知与已有完整事件可以同时出现。

源码：[`src/chronaxis/results/readable_format.py:78`](../../../src/chronaxis/results/readable_format.py#L78)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
