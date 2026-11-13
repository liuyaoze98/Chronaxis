# `chronaxis.fast.baseline`

修复版 base 的测量入口。输入为冻结的文件参数，只测读取、直接累计及发布。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 相关类型

[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)

## 对象导航

|对象|用途|
|---|---|
|[`main`](#api-main)|执行一个低层基准任务并打印实际清单路径。解析或执行错误使进程失败。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from pathlib import Path
from .run import run_prepared
```

</details>

<a id="api-main"></a>
## `main`

执行一个低层基准任务并打印实际清单路径。解析或执行错误使进程失败。

```python
main()
```

参数：无显式参数。


源码：[`src/chronaxis/fast/baseline.py:10`](../../../src/chronaxis/fast/baseline.py#L10)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
