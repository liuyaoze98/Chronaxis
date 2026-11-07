# `chronaxis.cli`

提供当前配置检查、分析发布、独立批量和高性能积分器入口。

参数为命令行选项；按命令延迟导入实现，帮助只依赖标准库。
检查按需读取配置和DBC元数据，运行命令才扫描业务输入并发布结果。
结果目录可复用；完成清单最后写入，失败不报告正常完成。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)

## 对象导航

|对象|用途|
|---|---|
|[`_parser`](#api-_parser)|定义已交付命令，未知命令和缺参数由argparse定位。|
|[`main`](#api-main)|执行共享CLI并给出固定退出码，完整事实保在报告和原异常中。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from pathlib import Path
```

</details>

<a id="api-_parser"></a>
## `_parser`

定义已交付命令，未知命令和缺参数由argparse定位。

```python
_parser() -> argparse.ArgumentParser
```

参数：无显式参数。


### 参数说明

无。

### 返回说明

ArgumentParser，不读取任何配置或来源。

### 异常说明

原参数构造错误传播；解析时的帮助/坏参数分别SystemExit(0/2)。

返回类型：argparse.ArgumentParser。

源码：[`src/chronaxis/cli.py:14`](../../../src/chronaxis/cli.py#L14)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。

<a id="api-main"></a>
## `main`

执行共享CLI并给出固定退出码，完整事实保在报告和原异常中。

```python
main(argv=None) -> int
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`argv`|str &#124; None|否|None|位置或关键字。argv为参数字符串序列或None（使用进程参数）。|

### 返回说明

0成功、130取消；失败按入口/阶段返回1或2。普通文件失败为1，
    fast单会话准备失败（含文件错误）为2、运行失败为1；批量规则见手册CLI。

### 异常说明

argparse帮助/参数错误按标准抛SystemExit；MemoryError及内部编程错误不伪装配置错误。

### 副作用说明

静态命令只读计划；run分析后发布本次时间文件到可复用目录。

返回类型：int。

源码：[`src/chronaxis/cli.py:85`](../../../src/chronaxis/cli.py#L85)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
