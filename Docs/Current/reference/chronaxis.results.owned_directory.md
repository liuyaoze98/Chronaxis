# `chronaxis.results.owned_directory`

只删除本次明确新建的私有目录，拒绝路径被重定向或目录被替换。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)

## 对象导航

|对象|用途|
|---|---|
|[`directory_identity`](#api-directory_identity)|登记刚创建目录的实际位置和文件系统身份，不枚举内容。|
|[`remove_owned_directory`](#api-remove_owned_directory)|核对原实际路径和身份后删除自有目录；不存在时幂等，失败可重试。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from pathlib import Path
```

</details>

<a id="api-directory_identity"></a>
## `directory_identity`

登记刚创建目录的实际位置和文件系统身份，不枚举内容。

```python
directory_identity(path)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`path`|str &#124; [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。本次任务专用路径；只操作本次登记的资源，不能指向原始输入或历史项目目录。|

### 返回说明

(resolved_path, device, inode)。

### 异常说明

IO或链接根拒绝。

源码：[`src/chronaxis/results/owned_directory.py:7`](../../../src/chronaxis/results/owned_directory.py#L7)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-remove_owned_directory"></a>
## `remove_owned_directory`

核对原实际路径和身份后删除自有目录；不存在时幂等，失败可重试。

```python
remove_owned_directory(path, identity)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`path`|str &#124; [Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。本次任务专用路径；只操作本次登记的资源，不能指向原始输入或历史项目目录。|
|`identity`|tuple[int, int, int, int] &#124; None|是|无|位置或关键字。本次登记的设备号、文件号、大小和mtime_ns；未请求摘要时据此拒绝文件替换或修改。|

### 返回说明

None。

### 异常说明

重定向/替换或IO错误。
shutil只删除目录内链接自身，不沿子目录链接删除外部内容；不接收未登记目录。

源码：[`src/chronaxis/results/owned_directory.py:19`](../../../src/chronaxis/results/owned_directory.py#L19)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
