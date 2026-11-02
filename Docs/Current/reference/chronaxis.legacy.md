# chronaxis.legacy

公开旧CAN记录，以及按需加载的记录仓、逐次模型与贡献累计原语。

输入输出和wire边界由records统一；实际进程由调用方显式创建，worker只在INIT后
加载vendor。包导入无输入/DBC读取、logger配置或子进程副作用；不代表旧reader关闭
缺陷已修复。单BLF公共AnalysisRunner和原始片段已在其任务中验收；独立逐次模型及累计
只接收调用方提供的记录和已求值贡献，不证明表达式、旧ChrgInfo出口或公共
legacy_sum来源已经接通。原语不替输入提供者补缓存、施加TTL或重新解码。
解码记录仓只在显式构造后写入新目录，保存现有合法记录，不扩大原IPC值类型。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[DecodedMessageStore](chronaxis.legacy.message_store.md#api-DecodedMessageStore)、[LegacyCANField](chronaxis.legacy.records.md#api-LegacyCANField)、[LegacyCANRequest](chronaxis.legacy.records.md#api-LegacyCANRequest)、[LegacyDecodedFrame](chronaxis.legacy.records.md#api-LegacyDecodedFrame)、[LegacyDecodedUpdate](chronaxis.legacy.updates.md#api-LegacyDecodedUpdate)、[LegacyRawFrame](chronaxis.legacy.records.md#api-LegacyRawFrame)、[LegacySkipReason](chronaxis.legacy.sum.md#api-LegacySkipReason)、[LegacySumAccumulator](chronaxis.legacy.sum.md#api-LegacySumAccumulator)、[LegacySumContribution](chronaxis.legacy.sum.md#api-LegacySumContribution)、[LegacySumSnapshot](chronaxis.legacy.sum.md#api-LegacySumSnapshot)、[LegacyUpdateOrder](chronaxis.legacy.updates.md#api-LegacyUpdateOrder)、[StoredDecodedMessage](chronaxis.legacy.message_store.md#api-StoredDecodedMessage)、[StoredRawFrame](chronaxis.legacy.records.md#api-StoredRawFrame)

## 对象导航

|对象|用途|
|---|---|
|[`__getattr__`](#api-__getattr__)|按需公开独立模型、记录仓与累计，保持原CAN worker的轻量导入。|

## 导出名称

`LegacyCANField`, `LegacyCANRequest`, `LegacyDecodedFrame`, `LegacyRawFrame`, `StoredRawFrame`, `MAX_WIRE_BYTES`, `PROFILE_ID`, `decoded_from_dict`, `decoded_to_dict`, `decode_packet`, `encode_packet`, `field_from_dict`, `field_to_dict`, `frame_from_dict`, `frame_to_dict`, `LegacyDecodedUpdate`, `LegacyUpdateOrder`, `LegacySkipReason`, `LegacySumContribution`, `LegacySumSnapshot`, `LegacySumAccumulator`, `StoredDecodedMessage`, `DecodedMessageStore`, `MAX_DECODED_MESSAGE_ROW_BYTES`

重导出保持定义位置的签名；按上级[总索引](index.md)查找对象名。

公开重导出按[公开API索引](../api.md)查询定义、用途和调用示例。

<details><summary>导入与重导出来源（展开）</summary>

```python
from .records import LegacyCANField, LegacyCANRequest, LegacyDecodedFrame, LegacyRawFrame, StoredRawFrame, MAX_WIRE_BYTES, PROFILE_ID, decoded_from_dict, decoded_to_dict, decode_packet, encode_packet, field_from_dict, field_to_dict, frame_from_dict, frame_to_dict
```

</details>

<a id="api-__getattr__"></a>
## `__getattr__`

按需公开独立模型、记录仓与累计，保持原CAN worker的轻量导入。

```python
__getattr__(name)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`name`|str|是|无|位置或关键字。Python请求的公开属性名称；按实际导出集合延迟导入，未知名称抛AttributeError。|

### 返回说明

已实现模型类本身，不创建输入或状态。

### 异常说明

AttributeError为未公开名称；模型模块导入错误原样传播。

### 副作用说明

仅访问明确名称时导入其模型或累计模块，不读取日志或DBC；
    NumPy仅在调用者实际选择数组累计后加载。

源码：[`src/chronaxis/legacy/__init__.py:24`](../../../src/chronaxis/legacy/__init__.py#L24)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
