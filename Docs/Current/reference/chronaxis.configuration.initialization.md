# `chronaxis.configuration.initialization`

把已校验的随包合成场景写入新目录，不改写已有文件。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)

## 对象导航

|对象|用途|
|---|---|
|[`initialize_configuration`](#api-initialize_configuration)|生成独立场景。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from pathlib import Path
from .template_catalog import available_templates, template_files
```

</details>

<a id="api-initialize_configuration"></a>
## `initialize_configuration`

生成独立场景。

```python
initialize_configuration(scene, output, *, style='annotated')
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`scene`|str|是|无|位置或关键字。模板清单中的场景名，例如signal-csv或can-asc；未知名称报错，不猜相近名称。|
|`output`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path) 或 str|是|无|位置或关键字。尚不存在的目标文件或目录；初始化写完整新目录，转换与展开写新文件，已有目标拒绝。|
|`style`|str|否|'annotated'|仅关键字。minimal只含必要配置，annotated提供完整说明；两者解析后的配置相同，默认annotated。|

### 返回说明

入口绝对路径。

### 异常说明

ValueError/IO/取消。

先读取全部包资源再独占创建目录，入口最后写出。写入失败仅删除本次创建的文件和目录；
清理失败附注原错误并保留残余，不删除其他进程写入的文件，不以成功掩盖部分写入。

源码：[`src/chronaxis/configuration/initialization.py:7`](../../../src/chronaxis/configuration/initialization.py#L7)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。

## 内部匿名回调


<a id="lambda-21"></a>
### 第21行匿名函数

```python
lambda item: item[0] == template.entrypoint
```

|参数|含义|返回/异常|
|---|---|---|
|`item`|模板文件的相对路径与内容二元组。|返回路径是否为入口文件的布尔值，使入口文件排在最后发布。|
