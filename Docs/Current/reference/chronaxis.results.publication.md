# `chronaxis.results.publication`

给同次输出分配时间文件名，并在已有结果目录中不覆盖地发布。

只检查本次候选路径，不扫描旧结果。平台不覆盖移动保护竞争期间出现的文件；
临时锁仅协调使用相同时间后缀的发布者，完成清单最后移动。失败回滚本次移动，
身份发生变化的路径保留给调用者处理，不删除其他运行或外部替换的文件。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)

## 对象导航

|对象|用途|
|---|---|
|[`output_root`](#api-output_root)|检查可复用结果根。|
|[`_identity`](#api-_identity)|取得文件身份。|
|[`PublicationNames`](#api-PublicationNames)|独占本次时间后缀，保留有限文件映射及已移动文件身份。|
|[`PublicationNames.__init__`](#api-PublicationNames-__init__)|分配不冲突名称。|
|[`PublicationNames.publish`](#api-PublicationNames-publish)|先移数据再移清单。|
|[`PublicationNames.close`](#api-PublicationNames-close)|释放本次命名锁。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from datetime import datetime
from pathlib import Path
from secrets import randbits
from .platform_files import move_no_replace, require_publication_platform
from .owned_directory import directory_identity
```

</details>

<a id="api-output_root"></a>
## `output_root`

检查可复用结果根。

```python
output_root(value)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`value`|str &#124; [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。请求发布到的目录路径；允许普通已有目录，拒绝只读历史目录及已有文件。|

### 返回说明

绝对Path。

### 异常说明

路径/平台错误。

源码：[`src/chronaxis/results/publication.py:16`](../../../src/chronaxis/results/publication.py#L16)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_identity"></a>
## `_identity`

取得文件身份。

```python
_identity(path)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`path`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。需要登记或核对身份的实际文件或目录路径。|

### 返回说明

设备和inode。

### 异常说明

原stat错误。

源码：[`src/chronaxis/results/publication.py:25`](../../../src/chronaxis/results/publication.py#L25)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-PublicationNames"></a>
## `PublicationNames`

独占本次时间后缀，保留有限文件映射及已移动文件身份。

```python
PublicationNames(root, names)
```


源码：[`src/chronaxis/results/publication.py:31`](../../../src/chronaxis/results/publication.py#L31)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-PublicationNames-__init__"></a>
### `PublicationNames.__init__`

分配不冲突名称。

```python
PublicationNames.__init__(root, names)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`root`|str &#124; [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。本次发布使用的可复用根目录。|
|`names`|Iterable[str]|是|无|位置或关键字。本次有限逻辑文件或目录名集合；每项仅接受单层名称。|

#### 返回说明

实例。

#### 异常说明

IO错。

源码：[`src/chronaxis/results/publication.py:34`](../../../src/chronaxis/results/publication.py#L34)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-PublicationNames-publish"></a>
### `PublicationNames.publish`

先移数据再移清单。

```python
PublicationNames.publish(temporary, last, installer=None, *, only=None)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`temporary`|str &#124; [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。已写好并关闭所有输出的本次临时目录。|
|`last`|str|是|无|位置或关键字。最后移动的完成清单逻辑文件名；必须属于本次选定名称。|
|`installer`|Callable &#124; None|否|None|位置或关键字。可选的不覆盖移动函数，接收来源和目标Path；None使用os.rename。|
|`only`|Iterable[str] &#124; None|否|None|仅关键字。可选的本次发布名称子集，必须包含last；None发布全部登记名称。|

#### 返回说明

None。

#### 异常说明

IO/取消。

源码：[`src/chronaxis/results/publication.py:87`](../../../src/chronaxis/results/publication.py#L87)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-PublicationNames-close"></a>
### `PublicationNames.close`

释放本次命名锁。

```python
PublicationNames.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None。

#### 异常说明

IO错，不删除其他身份的文件。

源码：[`src/chronaxis/results/publication.py:158`](../../../src/chronaxis/results/publication.py#L158)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
