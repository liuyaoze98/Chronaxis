# `chronaxis.fast.blocks`

贡献块的有界二进制编码。浮点使用binary64，时间和记录序号保持整数。

同一帧多个贡献共享时间和记录位置；CRC检查暂存意外损坏。只处理本次会话
内部数据，不加载任意对象，不保存完整CAN帧或解码字典。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 对象导航

|对象|用途|
|---|---|
|[`encode`](#api-encode)|编码一个有界块。|
|[`decode`](#api-decode)|核验并逐帧解码。|
|[`batches`](#api-batches)|按记录数及字节双上限切块。|

<a id="api-encode"></a>
## `encode`

编码一个有界块。

```python
encode(file_index, number, records)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`file_index`|int|是|无|位置或关键字。文件在已展开输入列表中的从0开始位置，用于校验交付身份及稳定排序。|
|`number`|int|是|无|位置或关键字。本文件从0递增的贡献块序号；消费者要求连续且只消费一次。|
|`records`|Iterable[tuple]|是|无|位置或关键字。同一文件的有序贡献记录，每条为整数时间、原始记录序号、计算项贡献元组；不得传部分和。|

### 返回说明

bytes。

### 异常说明

超大块或非法数值；不会改成低精度或丢弃尾部。

源码：[`src/chronaxis/fast/blocks.py:19`](../../../src/chronaxis/fast/blocks.py#L19)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-decode"></a>
## `decode`

核验并逐帧解码。

```python
decode(payload, file_index, number, metric_count)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`payload`|bytes|是|无|位置或关键字。包含版本、文件/块身份、binary64贡献和CRC的有界二进制数据；不得提前舍入。|
|`file_index`|int|是|无|位置或关键字。文件在已展开输入列表中的从0开始位置，用于校验交付身份及稳定排序。|
|`number`|int|是|无|位置或关键字。本文件从0递增的贡献块序号；消费者要求连续且只消费一次。|
|`metric_count`|int|是|无|位置或关键字。本会话计算项数量，用于拒绝未知、重复或超出范围的计算项编号。|

### 返回说明

记录生成器。

### 异常说明

身份、长度、CRC、序号、计算项或数值非法；不接受重复项。

源码：[`src/chronaxis/fast/blocks.py:38`](../../../src/chronaxis/fast/blocks.py#L38)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-batches"></a>
## `batches`

按记录数及字节双上限切块。

```python
batches(stream)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`stream`|Iterator[tuple]|是|无|位置或关键字。按原始文件顺序产生单帧贡献的迭代器，只有成功读完并关闭才结束。|

### 返回说明

有限列表生成器。

### 异常说明

单帧超限；不会拆散同帧元数据或整文件载入。

源码：[`src/chronaxis/fast/blocks.py:74`](../../../src/chronaxis/fast/blocks.py#L74)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
