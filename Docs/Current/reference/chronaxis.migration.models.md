# chronaxis.migration.models

保存旧配置导入的冻结报告，不把静态转换当作数据运行证明。

输入为导入器已经定位的配置事实；输出为固定类型结果和可供CLI写出的原生
JSON字典。原INI字节单独保留，字段和问题保持原顺序。本模块不读写文件、
执行表达式或导入任何旧配置对象，失败结果不能携带部分成功计划。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[AnalysisPlan](chronaxis.planning.plan.md#api-AnalysisPlan)

## 对象导航

|对象|用途|
|---|---|
|[`LegacyImportIssue`](#api-LegacyImportIssue)|定位一个错误或明确迁移差异；行列以1开始，非文本位置可为None。|
|[`LegacyImportIssue.to_dict`](#api-LegacyImportIssue-to_dict)|转换固定问题字段；|
|[`LegacyFieldMapping`](#api-LegacyFieldMapping)|保一项原INI字段、文本定位及处理去向，不因替代I/O丢弃原值。|
|[`LegacyFieldMapping.to_dict`](#api-LegacyFieldMapping-to_dict)|转换固定字段事实；|
|[`LegacyImportReport`](#api-LegacyImportReport)|区分整份成功与失败，SHA只证明配置身份，不证明来源数据已读。|
|[`LegacyImportReport.to_dict`](#api-LegacyImportReport-to_dict)|生成独立JSON报告；|
|[`LegacyImportResult`](#api-LegacyImportResult)|返回完整计划或None，同时保留同一个不可变原INI字节对象。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from typing import TYPE_CHECKING
```

</details>

<a id="api-LegacyImportIssue"></a>
## `LegacyImportIssue`

定位一个错误或明确迁移差异；行列以1开始，非文本位置可为None。

```python
class LegacyImportIssue
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`code`|str|是|无|可机读的问题代码，供报告分类。|
|`origin`|str|是|无|问题/字段来自INI还是mapping的来源标识。|
|`path`|str|是|无|原INI或mapping内的字段定位路径，不是文件内容已验证的证明。|
|`message`|str|是|无|面向使用者的问题或迁移差异说明文本。|
|`line`|int &#124; None|否|None|原文本1起始行号；无法归属实际文本位置时为None。|
|`column`|int &#124; None|否|None|原文本1起始列号；无法确定时为None。|
|`level`|str|否|'error'|问题等级文本，区分error与warning。|

源码：[`src/chronaxis/migration/models.py:16`](../../../src/chronaxis/migration/models.py#L16)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-LegacyImportIssue-to_dict"></a>
### `LegacyImportIssue.to_dict`

转换固定问题字段；

```python
LegacyImportIssue.to_dict() -> dict
```

参数：无显式参数。


#### 参数说明

无；

#### 返回说明

JSON对象；

#### 异常说明

无。

返回类型：dict。

源码：[`src/chronaxis/migration/models.py:27`](../../../src/chronaxis/migration/models.py#L27)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-LegacyFieldMapping"></a>
## `LegacyFieldMapping`

保一项原INI字段、文本定位及处理去向，不因替代I/O丢弃原值。

```python
class LegacyFieldMapping
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`origin`|str|是|无|问题/字段来自INI还是mapping的来源标识。|
|`path`|str|是|无|原INI或mapping内的字段定位路径，不是文件内容已验证的证明。|
|`value`|str|是|无|保留原INI字段的原始文本，不因迁移覆盖它。|
|`line`|int|是|无|原文本1起始行号；无法归属实际文本位置时为None。|
|`column`|int|是|无|原文本1起始列号；无法确定时为None。|
|`target`|str &#124; None|是|无|该原字段对应的新配置路径。|
|`status`|str|是|无|本次迁移状态，区分成功、拒绝或该字段的处理去向；不是分析运行成功证明。|
|`message`|str|是|无|面向使用者的问题或迁移差异说明文本。|

源码：[`src/chronaxis/migration/models.py:34`](../../../src/chronaxis/migration/models.py#L34)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-LegacyFieldMapping-to_dict"></a>
### `LegacyFieldMapping.to_dict`

转换固定字段事实；

```python
LegacyFieldMapping.to_dict() -> dict
```

参数：无显式参数。


#### 参数说明

无；

#### 返回说明

JSON对象；

#### 异常说明

无。

返回类型：dict。

源码：[`src/chronaxis/migration/models.py:46`](../../../src/chronaxis/migration/models.py#L46)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-LegacyImportReport"></a>
## `LegacyImportReport`

区分整份成功与失败，SHA只证明配置身份，不证明来源数据已读。

```python
class LegacyImportReport
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`status`|str|是|无|本次迁移状态，区分成功、拒绝或该字段的处理去向；不是分析运行成功证明。|
|`mode`|str|是|无|五种迁移模式：legacy_sum累计当前消息公式；sclicer_single找持续活动；sclicer_start_only找触发点；sclicer_start_end明确开始和结束；sclicer_slope转换窗口变化条件。各模式的必填映射和差异见[迁移](../migration.md)。|
|`source_name`|str|是|无|报告中的原INI来源文件名称，用于错误定位。|
|`source_sha256`|str|是|无|旧INI原始字节的SHA-256摘要。|
|`mapping_identity`|str &#124; None|是|无|规范迁移mapping的身份摘要；不证明数据文件已读取。|
|`device_label`|str|是|无|实际内容来源设备标签；不能根据文件所在路径猜home/work。|
|`fields`|tuple[[LegacyFieldMapping](chronaxis.migration.models.md#api-LegacyFieldMapping), ...]|是|无|本次局部字段映射记录列表，保留每个原INI键的定位和值与处理去向。|
|`issues`|tuple[[LegacyImportIssue](chronaxis.migration.models.md#api-LegacyImportIssue), ...]|是|无|本次局部问题列表，保留拒绝或明确差异的原因与位置。|
|`plan_identity`|str &#124; None|是|无|转换成功的计划身份；失败无计划时为None。|

源码：[`src/chronaxis/migration/models.py:53`](../../../src/chronaxis/migration/models.py#L53)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-LegacyImportReport-to_dict"></a>
### `LegacyImportReport.to_dict`

生成独立JSON报告；

```python
LegacyImportReport.to_dict() -> dict
```

参数：无显式参数。


#### 参数说明

无；

#### 返回说明

dict；

#### 异常说明

无。

#### 流程说明

仅展开固定报告对象，原INI和AnalysisPlan不会被反射序列化。

返回类型：dict。

源码：[`src/chronaxis/migration/models.py:66`](../../../src/chronaxis/migration/models.py#L66)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-LegacyImportResult"></a>
## `LegacyImportResult`

返回完整计划或None，同时保留同一个不可变原INI字节对象。

```python
class LegacyImportResult
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|'[AnalysisPlan](chronaxis.planning.plan.md#api-AnalysisPlan) &#124; None'|是|无|本次冻结AnalysisPlan，提供来源、规则、范围与执行预算。|
|`report`|[LegacyImportReport](chronaxis.migration.models.md#api-LegacyImportReport)|是|无|本次LegacyImportReport，包含完整字段映射、问题和转换结果。|
|`original_ini`|bytes|是|无|不可变的原INI bytes，保原编码、BOM与换行。|

源码：[`src/chronaxis/migration/models.py:78`](../../../src/chronaxis/migration/models.py#L78)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
