# chronaxis.migration.publication

在新目标旁发布导入原文与报告，成功转换的计划最后才安装。

输入是LegacyImportResult和.json目标，可显式附INI/mapping源路径；输出固定
LegacyImportFiles。三个文件先写入同父UUID临时文件，flush及实际close成功后，
按原文、报告、计划顺序用Windows不覆盖rename安装。转换失败只安装前两件，
报告status仍表示转换结果，不能据此宣称分析已运行或数据已经验证。

目标、解析后的RefProjects边界和源路径冲突在创建目录前检查；安装仍以真实
no-replace操作防竞态，不依赖预先exists检查或os.replace。只声明已验证的
Windows文件安装语义，其他平台在写入前明确拒绝。目录本身不作跨文件原子
事务，已安装sidecar在后续失败时保留；计划是最后的提交点。

小owner仅持本次真实FD和已独占创建的三个UUID临时文件。失败不吞原取消、
MemoryError或I/O异常；清理副错附note，异常上的
legacy_import_publication_cleanup_owner.close()可重试关闭并移除自有临时文件。
不递归删除，不删除已发布sidecar、用户目标或原配置，也不配置日志或运行旧链。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[AnalysisPlan](chronaxis.planning.plan.md#api-AnalysisPlan)、[LegacyImportReport](chronaxis.migration.models.md#api-LegacyImportReport)、[LegacyImportResult](chronaxis.migration.models.md#api-LegacyImportResult)、[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)

## 对象导航

|对象|用途|
|---|---|
|[`LegacyImportFiles`](#api-LegacyImportFiles)|保存词法绝对发布路径；plan为None时只有原文和失败转换报告。|
|[`_mapping_json`](#api-_mapping_json)|仅展开计划固定MappingProxy，不反射任意对象或调用其序列化方法。|
|[`_require_result`](#api-_require_result)|核公开转换结果与原bytes/计划身份一致，拒绝失败结果携带部分计划。|
|[`_targets`](#api-_targets)|先核词法目标、实际保护边界及源冲突，不创建任何输出。|
|[`_PublicationOwner`](#api-_PublicationOwner)|仅持本次独占临时文件及一个真实FD，不接管源文件或已安装目标。|
|[`_PublicationOwner.__init__`](#api-_PublicationOwner-__init__)|先安装全部实际责任槽，尚不创建临时文件。|
|[`_PublicationOwner._close_handle`](#api-_PublicationOwner-_close_handle)|关闭当前真实FD，失败时保持同一对象及临时路径可恢复。|
|[`_PublicationOwner.write`](#api-_PublicationOwner-write)|独占创建一个临时文件，写完flush且真实close后才允许安装。|
|[`_PublicationOwner.install`](#api-_PublicationOwner-install)|用Windows真实不覆盖rename安装，成功后只撤本临时槽。|
|[`_PublicationOwner.close`](#api-_PublicationOwner-close)|可重试关闭FD并逐个删除自有UUID临时文件，保留全部已安装sidecar。|
|[`write_legacy_import`](#api-write_legacy_import)|发布原配置及转换报告，只有完整成功转换才在最后安装计划。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from uuid import uuid4
from ..planning import AnalysisPlan
from .models import LegacyImportReport, LegacyImportResult
```

</details>

<a id="api-LegacyImportFiles"></a>
## `LegacyImportFiles`

保存词法绝对发布路径；plan为None时只有原文和失败转换报告。

```python
class LegacyImportFiles
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`plan`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path) &#124; None|是|无|读取成功发布的计划文件绝对Path；转换失败时为None，此时只有original和report两个辅助文件。|
|`original`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|已发布原INI副本的绝对Path。|
|`report`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|迁移报告的已发布绝对Path。|

源码：[`src/chronaxis/migration/publication.py:32`](../../../src/chronaxis/migration/publication.py#L32)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_mapping_json"></a>
## `_mapping_json`

仅展开计划固定MappingProxy，不反射任意对象或调用其序列化方法。

```python
_mapping_json(value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|object|是|无|位置或关键字。JSON编码器遇到的不可直接序列化对象；本函数处理冻结映射等迁移模型使用的结构，其他类型报错。|

### 返回说明

原生dict副本。

### 异常说明

TypeError为非MappingProxyType；MemoryError保持原生异常。

本函数直接报告的具体错误：

- `TypeError`：导入计划JSON仅允许固定MappingProxyType扩展。

源码：[`src/chronaxis/migration/publication.py:40`](../../../src/chronaxis/migration/publication.py#L40)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_require_result"></a>
## `_require_result`

核公开转换结果与原bytes/计划身份一致，拒绝失败结果携带部分计划。

```python
_require_result(result)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`result`|[LegacyImportResult](chronaxis.migration.models.md#api-LegacyImportResult)|是|无|位置或关键字。result为LegacyImportResult。|

### 返回说明

返回None，不返回额外的计算值。

### 异常说明

TypeError为非固定模型；ValueError为状态、原SHA或计划身份不一致。

本函数直接报告的具体错误：

- `TypeError`：发布需要LegacyImportResult、LegacyImportReport及原生INI bytes。
- `ValueError`：发布原INI bytes与转换报告SHA不一致。
- `ValueError`：无计划时仅接受失败转换报告，plan_identity必须为None。
- `ValueError`：成功转换报告必须关联同一完整AnalysisPlan。

源码：[`src/chronaxis/migration/publication.py:51`](../../../src/chronaxis/migration/publication.py#L51)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_targets"></a>
## `_targets`

先核词法目标、实际保护边界及源冲突，不创建任何输出。

```python
_targets(output_path, source_paths)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`output_path`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path) &#124; str|是|无|位置或关键字。output_path为.json文件Path/str|
|`source_paths`|tuple|是|无|位置或关键字。source_paths为INI及mapping的Path/str tuple。|

### 返回说明

(计划、原文、报告)三个绝对Path，按计划路径派生固定后缀。

### 异常说明

TypeError为路径容器；ValueError为后缀/Ref/源冲突；FileExistsError为任一已有目标。

本函数直接报告的具体错误：

- `TypeError`：output_path需要Path/str，source_paths需要tuple。
- `TypeError`：source_paths每项需要Path/str。
- `ValueError`：导入计划输出必须使用.json后缀。
- `ValueError`：导入输出禁止位于RefProjects。
- `ValueError`：导入输出不能与原INI或mapping配置同路径。

源码：[`src/chronaxis/migration/publication.py:71`](../../../src/chronaxis/migration/publication.py#L71)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_PublicationOwner"></a>
## `_PublicationOwner`

仅持本次独占临时文件及一个真实FD，不接管源文件或已安装目标。

```python
_PublicationOwner(targets)
```


源码：[`src/chronaxis/migration/publication.py:105`](../../../src/chronaxis/migration/publication.py#L105)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_PublicationOwner-__init__"></a>
### `_PublicationOwner.__init__`

先安装全部实际责任槽，尚不创建临时文件。

```python
_PublicationOwner.__init__(targets)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`targets`|tuple[[pathlib.Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path), [pathlib.Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path), [pathlib.Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)]|是|无|位置或关键字。原文、迁移报告、转换计划的三个绝对目标路径，必须事先检查且彼此不同。|

#### 返回说明

新owner。

#### 异常说明

原内存/UUID错误传播。

源码：[`src/chronaxis/migration/publication.py:108`](../../../src/chronaxis/migration/publication.py#L108)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_PublicationOwner-_close_handle"></a>
### `_PublicationOwner._close_handle`

关闭当前真实FD，失败时保持同一对象及临时路径可恢复。

```python
_PublicationOwner._close_handle()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原close错误；未真实关闭则OSError。

本函数直接报告的具体错误：

- `OSError`：导入临时文件FD尚未关闭。

源码：[`src/chronaxis/migration/publication.py:119`](../../../src/chronaxis/migration/publication.py#L119)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_PublicationOwner-write"></a>
### `_PublicationOwner.write`

独占创建一个临时文件，写完flush且真实close后才允许安装。

```python
_PublicationOwner.write(index, value, *, original=False)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`index`|int|是|无|位置或关键字。当前记录或文件槽的序号，从0开始，按原有顺序定位。|
|`value`|bytes &#124; JSON值|是|无|位置或关键字。原文槽写入原始bytes；报告和计划槽写入JSON结构，编码为UTF-8后写入临时文件。|
|`original`|bool|否|False|仅关键字。original选择二进制原文。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原open/write/flush/close/JSON/内存或取消错误，不隐式重试写入。

本函数直接报告的具体错误：

- `OSError`：原INI临时文件写入不完整。

源码：[`src/chronaxis/migration/publication.py:134`](../../../src/chronaxis/migration/publication.py#L134)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_PublicationOwner-install"></a>
### `_PublicationOwner.install`

用Windows真实不覆盖rename安装，成功后只撤本临时槽。

```python
_PublicationOwner.install(index)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`index`|int|是|无|位置或关键字。当前记录或文件槽的序号，从0开始，按原有顺序定位。|

#### 返回说明

返回None，不返回额外的计算值。

#### 异常说明

原rename错误；不能用exists预检查取代最终no-replace。

源码：[`src/chronaxis/migration/publication.py:161`](../../../src/chronaxis/migration/publication.py#L161)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-_PublicationOwner-close"></a>
### `_PublicationOwner.close`

可重试关闭FD并逐个删除自有UUID临时文件，保留全部已安装sidecar。

```python
_PublicationOwner.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

返回None。关闭成功后再次调用不会重复释放同一份资源。

#### 异常说明

原close/unlink错误附同一最高owner。

源码：[`src/chronaxis/migration/publication.py:171`](../../../src/chronaxis/migration/publication.py#L171)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。

<a id="api-write_legacy_import"></a>
## `write_legacy_import`

发布原配置及转换报告，只有完整成功转换才在最后安装计划。

```python
write_legacy_import(result: LegacyImportResult, output_path, *, source_paths=()) -> LegacyImportFiles
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`result`|[LegacyImportResult](chronaxis.migration.models.md#api-LegacyImportResult)|是|无|位置或关键字。result为固定转换结果|
|`output_path`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path) &#124; str|是|无|位置或关键字。output_path为新.json目标|
|`source_paths`|tuple[str &#124; [pathlib.Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path), ...]|否|()|仅关键字。原INI和mapping路径，用于检查输出不能覆盖输入；省略时沿用函数默认空元组。|

### 返回说明

LegacyImportFiles，均为绝对Path，转换失败时plan=None。

### 异常说明

类型/配置错误、已有目标、Ref边界及系统I/O错误保持原异常；非Windows为
    NotImplementedError。KI/MemoryError原样；清理副错仅附note，最高恢复owner留在原错上。

### 副作用说明

只创建目标父目录和三个自有临时文件；失败可保已装sidecar，绝不覆盖或删用户文件。

返回类型：[LegacyImportFiles](chronaxis.migration.publication.md#api-LegacyImportFiles)。

源码：[`src/chronaxis/migration/publication.py:193`](../../../src/chronaxis/migration/publication.py#L193)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
