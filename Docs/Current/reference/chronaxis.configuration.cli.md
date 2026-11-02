# chronaxis.configuration.cli

配置辅助命令；复用同一模板及配置入口，不执行分析。

这是模块参考。日常调用先查[公开API索引](../api.md)；下划线对象、嵌套函数和vendor实现供维护者查阅。签名来自固定源码，公开类构造签名经实际Python接口核对。

## 对象导航

|对象|用途|
|---|---|
|[`run_configuration_cli`](#api-run_configuration_cli)|执行已解析的配置命令。|

<details><summary>导入与重导出来源（展开）</summary>

```python
from .template_catalog import available_templates
from .initialization import initialize_configuration
```

</details>

<a id="api-run_configuration_cli"></a>
## `run_configuration_cli`

执行已解析的配置命令。

```python
run_configuration_cli(arguments)
```

### 参数

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`arguments`|argparse.Namespace|是|无|位置或关键字。主CLI已解析的参数对象；子命令、输出路径及选项由对应命令行参数取得。|

### 返回说明

退出码。

### 异常说明

配置/文件/取消上交CLI。

初始化显示实际入口与合成预期；可运行不代表适合真实设备。

源码：[`src/chronaxis/configuration/cli.py:6`](../../../src/chronaxis/configuration/cli.py#L6)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
