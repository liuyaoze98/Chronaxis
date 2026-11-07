# `chronaxis.user_guide`

定位可以直接阅读的AI指南，按显式请求另存独立ZIP。

只处理公开使用说明、配置规范和合成样例，不读取用户业务输入。
默认只检查入口并返回路径，不构建、解压或复制。源码使用Docs/AI，
安装使用包内guide目录；显式导出才读取整套资料并写用户指定的新文件。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)

## 对象导航

|对象|用途|
|---|---|
|[`guide_path`](#api-guide_path)|定位中英文README，不写文件。|
|[`_installed_archive`](#api-_installed_archive)|按发行清单打包，忽略阅读后产生的缓存或结果。|
|[`export_guide`](#api-export_guide)|把当前安装包提供的AI使用指南导出为用户指定的新ZIP文件。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from io import BytesIO
from pathlib import Path
from runpy import run_path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo
```

</details>

<a id="api-guide_path"></a>
## `guide_path`

定位中英文README，不写文件。

```python
guide_path(language='zh')
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`language`|str|否|'zh'|位置或关键字。language为zh或en，默认中文。|

### 返回说明

README的绝对Path。

### 异常说明

未知语言ValueError；指南缺失FileNotFoundError。只支持普通目录安装。

源码：[`src/chronaxis/user_guide.py:14`](../../../src/chronaxis/user_guide.py#L14)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-_installed_archive"></a>
## `_installed_archive`

按发行清单打包，忽略阅读后产生的缓存或结果。

```python
_installed_archive(root)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`root`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|位置或关键字。已安装指南的普通目录，按其中manifest.json列出的文件生成可选压缩副本。|

### 返回说明

确定性ZIP字节。

### 异常说明

清单/资源缺失或越界。

源码：[`src/chronaxis/user_guide.py:37`](../../../src/chronaxis/user_guide.py#L37)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-export_guide"></a>
## `export_guide`

把当前安装包提供的AI使用指南导出为用户指定的新ZIP文件。

```python
export_guide(output)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`output`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path) &#124; str|是|无|位置或关键字。用户指定的新ZIP文件路径；父目录须已存在，不允许覆盖文件或写入RefProjects。|

### 返回说明

导出路径。

### 异常说明

已有目标、缺资料或I/O失败。

源码：[`src/chronaxis/user_guide.py:56`](../../../src/chronaxis/user_guide.py#L56)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
