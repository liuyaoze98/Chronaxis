# chronaxis.migration.ini

静态读取受支持INI语法并保字段位置，不实例化旧ConfigManager。

输入为已解码文本和本次局部报告字段列表；输出公开ConfigParser对象及原段序。
Sclicer保持旧option小写规则，ChrgInfo保持大小写及仅分号注释。预扫描拒DEFAULT、插值、重复和多行继承，
随后仍用标准ConfigParser核语法；不读外部INI、DBC、日志或环境变量。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[LegacyFieldMapping](chronaxis.migration.models.md#api-LegacyFieldMapping)、[LegacyImportIssue](chronaxis.migration.models.md#api-LegacyImportIssue)

## 对象导航

|对象|用途|
|---|---|
|[`ImportProblem`](#api-ImportProblem)|仅在本包内部传递一条配置语义问题，不接管I/O或取消异常。|
|[`ImportProblem.__init__`](#api-ImportProblem-__init__)|保原问题；|
|[`problem`](#api-problem)|抛有限语义问题；|
|[`field_path`](#api-field_path)|生成稳定INI位置；|
|[`locate`](#api-locate)|查原字段定位；|
|[`mark`](#api-mark)|更新本次局部字段去向；|
|[`parse_ini`](#api-parse_ini)|预扫有限INI位置并用标准解析器复核，不允许多行或隐式继承。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import replace
from .models import LegacyFieldMapping, LegacyImportIssue
```

</details>

<a id="api-ImportProblem"></a>
## `ImportProblem`

仅在本包内部传递一条配置语义问题，不接管I/O或取消异常。

```python
ImportProblem(issue: LegacyImportIssue)
```

继承关系：Exception。下表列本类声明的字段；基类字段及其约束见对应类型链接。


源码：[`src/chronaxis/migration/ini.py:15`](../../../src/chronaxis/migration/ini.py#L15)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-ImportProblem-__init__"></a>
### `ImportProblem.__init__`

保原问题；

```python
ImportProblem.__init__(issue: LegacyImportIssue)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`issue`|[LegacyImportIssue](chronaxis.migration.models.md#api-LegacyImportIssue)|是|无|位置或关键字。具体MigrationIssue，包含旧配置位置、问题代码和需要修正的说明。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

无。

源码：[`src/chronaxis/migration/ini.py:18`](../../../src/chronaxis/migration/ini.py#L18)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-problem"></a>
## `problem`

抛有限语义问题；

```python
problem(code, origin, path, message, line=None, column=None)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`code`|str|是|无|位置或关键字。报告中的问题代码，便于程序分类处理；对应原因写在message中。|
|`origin`|str|是|无|位置或关键字。原字段所在材料，例如"ini"或"mapping"；与path合起来定位问题来源。|
|`path`|str|是|无|位置或关键字。原INI或mapping内部的字段位置，例如节名和键名，用于回查需要修改的配置。|
|`message`|str|是|无|位置或关键字。面向使用者的问题或迁移差异说明文本。|
|`line`|str &#124; None|否|None|位置或关键字。原文本1起始行号；无法归属实际文本位置时为None。|
|`column`|str &#124; None|否|None|位置或关键字。原文本1起始列号；无法确定时为None。|

### 返回说明

无；

### 异常说明

ImportProblem。

源码：[`src/chronaxis/migration/ini.py:24`](../../../src/chronaxis/migration/ini.py#L24)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-field_path"></a>
## `field_path`

生成稳定INI位置；

```python
field_path(section, key)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`section`|str|是|无|位置或关键字。当前正在转换的旧INI段名，例如TRIGGER_1；必须能在原配置中找到。|
|`key`|str|是|无|位置或关键字。当前段内的旧配置键，例如expr或duration_sec，用于读取值和定位错误。|

### 返回说明

str；

### 异常说明

无。

源码：[`src/chronaxis/migration/ini.py:29`](../../../src/chronaxis/migration/ini.py#L29)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-locate"></a>
## `locate`

查原字段定位；

```python
locate(fields, section, key=None)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`fields`|list[[LegacyFieldMapping](chronaxis.migration.models.md#api-LegacyFieldMapping)]|是|无|位置或关键字。按原INI顺序保存的字段记录，含段名、键、值、行列和转换去向；转换过程会补充处理状态。|
|`section`|str|是|无|位置或关键字。当前正在转换的旧INI段名，例如TRIGGER_1；必须能在原配置中找到。|
|`key`|str &#124; None|否|None|位置或关键字。当前段内的旧配置键，例如expr或duration_sec，用于读取值和定位错误。 None仅定位整个INI节，不定位节内某个键。|

### 返回说明

行列tuple；

### 异常说明

无。

源码：[`src/chronaxis/migration/ini.py:34`](../../../src/chronaxis/migration/ini.py#L34)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-mark"></a>
## `mark`

更新本次局部字段去向；

```python
mark(fields, section, key, target, status='mapped', message='按显式映射转换')
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`fields`|list[[LegacyFieldMapping](chronaxis.migration.models.md#api-LegacyFieldMapping)]|是|无|位置或关键字。按原INI顺序保存的字段记录，含段名、键、值、行列和转换去向；转换过程会补充处理状态。|
|`section`|str|是|无|位置或关键字。当前正在转换的旧INI段名，例如TRIGGER_1；必须能在原配置中找到。|
|`key`|str|是|无|位置或关键字。当前段内的旧配置键，例如expr或duration_sec，用于读取值和定位错误。|
|`target`|str|是|无|位置或关键字。该旧字段转换后对应的新配置路径，例如rules中的某项字段。|
|`status`|str|否|'mapped'|位置或关键字。本次迁移状态，区分成功、拒绝或该字段的处理去向；不是分析运行成功证明。|
|`message`|str|否|'按显式映射转换'|位置或关键字。面向使用者的问题或迁移差异说明文本。|

### 返回说明

返回None，不返回额外的计算值。

### 异常说明

无。

源码：[`src/chronaxis/migration/ini.py:44`](../../../src/chronaxis/migration/ini.py#L44)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。

<a id="api-parse_ini"></a>
## `parse_ini`

预扫有限INI位置并用标准解析器复核，不允许多行或隐式继承。

```python
parse_ini(text, fields, *, preserve_case=False)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`text`|str|是|无|位置或关键字。text原文本|
|`fields`|list[[LegacyFieldMapping](chronaxis.migration.models.md#api-LegacyFieldMapping)]|是|无|位置或关键字。按原INI顺序保存的字段记录，含段名、键、值、行列和转换去向；转换过程会补充处理状态。|
|`preserve_case`|bool|否|False|仅关键字。preserve_case选择ChrgInfo大小写及分号口径。|

### 返回说明

(ConfigParser, 段名到头部行号dict)。

### 异常说明

ImportProblem为配置语法错误；
MemoryError/取消原样传播。Sclicer无inline注释；ChrgInfo的井号不是INI注释。

源码：[`src/chronaxis/migration/ini.py:52`](../../../src/chronaxis/migration/ini.py#L52)（行号属于 `5c95e101972bbdb1228d6fa8f0afadfc34cb050b`）。
