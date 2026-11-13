# `chronaxis.results.platform_files`

按平台原语不覆盖地移动一个文件或目录，不复制内容或重读分析输入。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)

## 对象导航

|对象|用途|
|---|---|
|[`_linux_rename`](#api-_linux_rename)|取得libc的正式renameat2接口。|
|[`require_publication_platform`](#api-require_publication_platform)|确认本机提供不覆盖发布的调用接口，不创建探测文件。|
|[`_DirectoryHandles`](#api-_DirectoryHandles)|短暂持有本次移动的两个父目录fd；遵循Linux关闭后不重试同一编号。|
|[`_DirectoryHandles.__init__`](#api-_DirectoryHandles-__init__)|初始化两个空目录fd槽。|
|[`_DirectoryHandles.closed`](#api-_DirectoryHandles-closed)|查询两个目录fd是否都已交给Linux关闭。|
|[`_DirectoryHandles.open`](#api-_DirectoryHandles-open)|打开并登记本次移动的一侧父目录。|
|[`_DirectoryHandles.close`](#api-_DirectoryHandles-close)|对两个实际目录fd各调用一次Linux close。|
|[`move_no_replace`](#api-move_no_replace)|在同一文件系统中不覆盖地移动一个文件或目录。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from functools import lru_cache
from pathlib import Path
from .budget import _cleanup_owner
```

</details>

<a id="api-_linux_rename"></a>
## `_linux_rename`

取得libc的正式renameat2接口。

```python
_linux_rename()
```

装饰器：`lru_cache(maxsize=1)`。

参数：无显式参数。


### 参数说明

无。

### 返回说明

已声明参数类型的C函数。

### 异常说明

libc缺少该接口时抛NotImplementedError，不退回可覆盖的rename。

源码：[`src/chronaxis/results/platform_files.py:11`](../../../src/chronaxis/results/platform_files.py#L11)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-require_publication_platform"></a>
## `require_publication_platform`

确认本机提供不覆盖发布的调用接口，不创建探测文件。

```python
require_publication_platform()
```

参数：无显式参数。


### 参数说明

无。

### 返回说明

None；只核对当前平台及调用接口，不创建试探文件，也不预先证明目标文件系统可完成移动。

### 异常说明

Windows 直接通过；Linux 需要 libc 提供 renameat2，其余平台或接口缺失抛 NotImplementedError。Linux 内核与目标文件系统的 RENAME_NOREPLACE 支持在实际移动时核验。

源码：[`src/chronaxis/results/platform_files.py:26`](../../../src/chronaxis/results/platform_files.py#L26)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_DirectoryHandles"></a>
## `_DirectoryHandles`

短暂持有本次移动的两个父目录fd；遵循Linux关闭后不重试同一编号。

```python
_DirectoryHandles()
```


源码：[`src/chronaxis/results/platform_files.py:40`](../../../src/chronaxis/results/platform_files.py#L40)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_DirectoryHandles-__init__"></a>
### `_DirectoryHandles.__init__`

初始化两个空目录fd槽。

```python
_DirectoryHandles.__init__()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

新的目录句柄对象。

#### 异常说明

无主动异常。

源码：[`src/chronaxis/results/platform_files.py:43`](../../../src/chronaxis/results/platform_files.py#L43)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_DirectoryHandles-closed"></a>
### `_DirectoryHandles.closed`

查询两个目录fd是否都已交给Linux关闭。

```python
_DirectoryHandles.closed
```

装饰器：`property`。

读取属性，不使用调用括号。


#### 参数说明

无。

#### 返回说明

bool；关闭报错仍由close方法向外报告。

#### 异常说明

无。

源码：[`src/chronaxis/results/platform_files.py:53`](../../../src/chronaxis/results/platform_files.py#L53)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_DirectoryHandles-open"></a>
### `_DirectoryHandles.open`

打开并登记本次移动的一侧父目录。

```python
_DirectoryHandles.open(name, path)
```

#### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`name`|Literal["source", "target"]|是|无|位置或关键字。登记目录句柄所用的内部槽名；source 代表来源父目录，target 代表目标父目录。调用方固定传这两个值。|
|`path`|[pathlib.Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。待打开的实际父目录；使用不跟随符号链接的 stat 与 O_NOFOLLOW 打开，再核对设备号和 inode，拒绝替换后的目录身份。|

#### 返回说明

实际打开的目录fd。

#### 异常说明

链接、父目录身份替换或IO错误；已经打开的fd仍归本对象。

源码：[`src/chronaxis/results/platform_files.py:62`](../../../src/chronaxis/results/platform_files.py#L62)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-_DirectoryHandles-close"></a>
### `_DirectoryHandles.close`

对两个实际目录fd各调用一次Linux close。

```python
_DirectoryHandles.close()
```

参数：无显式参数。


#### 参数说明

无。

#### 返回说明

None；已关闭的槽不重复操作。

#### 异常说明

报告首个关闭错误，其余写入notes；不重试可能已被复用的fd编号。

源码：[`src/chronaxis/results/platform_files.py:77`](../../../src/chronaxis/results/platform_files.py#L77)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

<a id="api-move_no_replace"></a>
## `move_no_replace`

在同一文件系统中不覆盖地移动一个文件或目录。

```python
move_no_replace(source, target)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`source`|str &#124; os.PathLike[str]|是|无|位置或关键字。本次要移动的已有文件或目录路径；来源和目标须在同一文件系统，不复制内容，也不读取分析输入。|
|`target`|str &#124; os.PathLike[str]|是|无|位置或关键字。不得已存在的目标路径；目标出现时由平台原语拒绝覆盖，回滚移动也遵循同一规则。|

### 返回说明

None。单次名称移动使用平台不覆盖原语；不承诺多文件事务或断电后的持久化。

### 异常说明

已有目标、跨文件系统、目录身份变化或 I/O 错误原样失败。未支持的平台、libc 缺少 renameat2，或内核/目标文件系统不支持 RENAME_NOREPLACE 时抛 NotImplementedError；不会改用可覆盖的 rename。Linux 目录 fd 各关闭一次，关闭失败仍报告原错误，不重试可能已被复用的编号。

源码：[`src/chronaxis/results/platform_files.py:100`](../../../src/chronaxis/results/platform_files.py#L100)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
