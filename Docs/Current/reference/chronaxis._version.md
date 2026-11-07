# `chronaxis._version`

取得当前这份软件的发行版本，不查询其他安装副本或业务输入。

源码检出从自身项目的pyproject.toml读取；构建包使用构建时自动生成的版本模块。
只依赖标准库且不写文件，缺失或损坏的版本资料明确报错，不回退为另一版本。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)

## 对象导航

|对象|用途|
|---|---|
|[`software_version`](#api-software_version)|返回当前源码或安装包版本；版本资料缺失、项目不符或版本为空时抛RuntimeError。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from pathlib import Path
```

</details>

<a id="api-software_version"></a>
## `software_version`

返回当前源码或安装包版本；版本资料缺失、项目不符或版本为空时抛RuntimeError。

```python
software_version() -> str
```

参数：无显式参数。


### 参数说明

无。

### 返回说明

非空版本字符串。读取最多一份本地项目文件或本包生成模块；
不读取全局distribution元数据，不依赖调用者工作目录，不修改任何文件。

返回类型：str。

源码：[`src/chronaxis/_version.py:11`](../../../src/chronaxis/_version.py#L11)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
