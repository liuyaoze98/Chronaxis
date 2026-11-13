# `chronaxis.configuration.diagnostics`

为配置错误附上原文位置与有限的上下文；成功计划不保存此处的文档对象。

这里只消费已解析的原生值，不重新读取配置或来源。字段路径采用带引号键的
JSON路径；不存在字段回指最近所属对象，不能给缺少的值捏造行列。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 对象导航

|对象|用途|
|---|---|
|[`field_path_parts`](#api-field_path_parts)|读取内部字段路径。|
|[`child_path`](#api-child_path)|追加一层真实键。|
|[`value_preview`](#api-value_preview)|只显示有限值摘要。|
|[`locate_error`](#api-locate_error)|给计划异常补充有限诊断字段。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from .models import field_path_text
```

</details>

<a id="api-field_path_parts"></a>
## `field_path_parts`

读取内部字段路径。

```python
field_path_parts(text)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`text`|str|是|无|位置或关键字。形如$.sources[0].path的字段路径文本；带引号的键按原文字识别，不任意拆分点号。|

### 返回说明

tuple或无法定位时None。

### 异常说明

无。

引号键用标准JSON解码，不执行表达式；组合诊断如$.signals/derived不能冒充字段。

源码：[`src/chronaxis/configuration/diagnostics.py:12`](../../../src/chronaxis/configuration/diagnostics.py#L12)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-child_path"></a>
## `child_path`

追加一层真实键。

```python
child_path(path, key)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`path`|tuple[str 或 int, ...]|是|无|位置或关键字。从配置根开始的字段键/数组下标序列；只表示当前值的位置，不是操作系统文件路径。|
|`key`|str 或 int|是|无|位置或关键字。映射中的文本键或数组中的整数下标；拼接时保留层级，带标点的键不会当成路径分隔符。|

### 返回说明

无歧义路径。

### 异常说明

内部路径不合法。

源码：[`src/chronaxis/configuration/diagnostics.py:46`](../../../src/chronaxis/configuration/diagnostics.py#L46)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-value_preview"></a>
## `value_preview`

只显示有限值摘要。

```python
value_preview(value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|JSON原生值|是|无|位置或关键字。当前待检查或显示的单个值；诊断不会展开打印整个大容器。|

### 返回说明

最多180字符。

### 异常说明

无。

容器仅报类型/大小，防止错误输出整份配置、内存行或自由元数据。

源码：[`src/chronaxis/configuration/diagnostics.py:52`](../../../src/chronaxis/configuration/diagnostics.py#L52)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-locate_error"></a>
## `locate_error`

给计划异常补充有限诊断字段。

```python
locate_error(error, document)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`error`|配置异常实例|是|无|位置或关键字。需要补充来源位置的原异常，保留错误码及其原因链，不用新成功结果替代。|
|`document`|ConfigurationDocument|是|无|位置或关键字。共享解析器返回的原生配置及字段位置；不包含业务输入记录。|

### 返回说明

同一异常。

### 异常说明

无。

不保存document、原字典或位置表；只复制源码名、单一位置、对象名和短值。

源码：[`src/chronaxis/configuration/diagnostics.py:65`](../../../src/chronaxis/configuration/diagnostics.py#L65)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
