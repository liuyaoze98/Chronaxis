# chronaxis.legacy.vendor.sclicer_functions_v1.can_processor

冻结的Sclicer解码与旧表达式工具。公共CAN输入在独立进程中借用此模块的既有解码能力；旧表达式语法和缺失值政策仅用于兼容审计，普通分析使用chronaxis.core.expression。不要直接用这里的旧求值器替代新核心。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 对象导航

|对象|用途|
|---|---|
|[`build_writer`](#api-build_writer)|根据指定的输出格式和路径，创建对应的 CAN 数据写入器。|
|[`eval_expr`](#api-eval_expr)|解析并评估一个表达式，该表达式使用信号字典中的信号值。|
|[`parse_frame`](#api-parse_frame)|从单帧CAN报文解析出全部信号值。|
|[`get_signals_for_message_id`](#api-get_signals_for_message_id)|获取指定CAN报文ID包含的所有信号名称。|

<a id="api-build_writer"></a>
## `build_writer`

根据指定的输出格式和路径，创建对应的 CAN 数据写入器。

该函数支持三种输出格式：
- 'blf'：使用 can.BLFWriter 写入 BLF 格式文件
- 'asc'：使用 can.ASCWriter 写入 ASC 格式文件
- 'csv'：使用 can.CSVWriter 写入 CSV 格式文件

```python
build_writer(out_path, out_fmt)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`out_path`|str|是|无|位置或关键字。输出文件的路径|
|`out_fmt`|str|是|无|位置或关键字。输出文件的格式，支持 'blf'、'asc'、'csv'|

### 返回说明

tuple: 一个包含写入器和路径的元组 (writer, out_path)

源码：[`src/chronaxis/legacy/vendor/sclicer_functions_v1/can_processor.py:11`](../../../src/chronaxis/legacy/vendor/sclicer_functions_v1/can_processor.py#L11)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-eval_expr"></a>
## `eval_expr`

解析并评估一个表达式，该表达式使用信号字典中的信号值。

该函数会先对输入的表达式进行语法检查，确保只包含允许的语法节点。
接着检查表达式中引用的信号是否都存在于信号字典中，如果有缺失则返回 False。
最后使用安全的方式评估表达式，若评估过程中出现异常也返回 False。
对于浮点数比较，使用近似比较来解决精度问题。

```python
eval_expr(expr, sig_dict)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`expr`|str|是|无|位置或关键字。需要解析和评估的表达式字符串|
|`sig_dict`|dict|是|无|位置或关键字。信号字典，键为信号名，值为信号值|

### 返回说明

bool: 若表达式评估结果为真则返回 True；若表达式语法非法、引用缺失信号或评估出错，返回 False

源码：[`src/chronaxis/legacy/vendor/sclicer_functions_v1/can_processor.py:38`](../../../src/chronaxis/legacy/vendor/sclicer_functions_v1/can_processor.py#L38)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-parse_frame"></a>
## `parse_frame`

从单帧CAN报文解析出全部信号值。

该函数尝试使用提供的数据库对象解码CAN报文，
解析出报文中包含的所有信号及其对应的值。
如果解析失败，返回空字典。

```python
parse_frame(msg, db)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`msg`|can.Message|是|无|位置或关键字。CAN报文对象，包含报文ID和数据|
|`db`|can.Database|是|无|位置或关键字。CAN数据库对象，用于信号解码|

### 返回说明

dict: 包含信号名和对应值的字典；如果解析失败，返回空字典

### 异常说明

无显式异常抛出，所有异常都会被捕获并返回空字典

源码：[`src/chronaxis/legacy/vendor/sclicer_functions_v1/can_processor.py:91`](../../../src/chronaxis/legacy/vendor/sclicer_functions_v1/can_processor.py#L91)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-get_signals_for_message_id"></a>
## `get_signals_for_message_id`

获取指定CAN报文ID包含的所有信号名称。

该函数从数据库中查找指定ID的CAN报文定义，
并返回该报文中包含的所有信号名称集合。
如果未找到对应报文，返回空集合。

```python
get_signals_for_message_id(db, message_id)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`db`|can.Database|是|无|位置或关键字。CAN数据库对象，包含报文和信号定义|
|`message_id`|int|是|无|位置或关键字。CAN报文ID|

### 返回说明

set: 包含信号名称的集合；如果未找到报文，返回空集合

### 异常说明

无显式异常抛出，所有异常都会被捕获并返回空集合

源码：[`src/chronaxis/legacy/vendor/sclicer_functions_v1/can_processor.py:116`](../../../src/chronaxis/legacy/vendor/sclicer_functions_v1/can_processor.py#L116)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
