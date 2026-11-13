# `chronaxis.__main__`

将python -m chronaxis委托给同一个CLI入口。

输入为进程参数，输出及退出码由cli.main定义。作为模块导入时不运行命令；
实际执行只加载CLI，再由用户命令决定检查配置、运行分析或处理结果。
本文件不另写计算逻辑、加载CAN或注册额外后台动作。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象和嵌套函数供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 对象导航

|对象|用途|
|---|---|

<details><summary>导入与重导出来源（展开）</summary>

```python
from .cli import main
```

</details>
