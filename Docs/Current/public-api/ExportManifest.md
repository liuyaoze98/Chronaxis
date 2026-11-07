# chronaxis.ExportManifest

使用`from chronaxis import ExportManifest`导入。本页只列直接公开成员与必要的构造/上下文协议；内部实现见[模块参考](../reference/chronaxis.results.manifest.md)。

返回[公开API索引](../api.md)。参数表中的类型可跳转到定义；先核对必填、默认值与返回/异常说明。

## 成员导航

- [`ExportManifest`](#api-ExportManifest)

<a id="api-ExportManifest"></a>
## `ExportManifest`

独立信号或原帧导出的实际输出路径；调用者无需猜测时间文件名。

```python
ExportManifest(output_dir: pathlib.Path, manifest_path: pathlib.Path, output_files: tuple[pathlib.Path, ...]) -> None
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`output_dir`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|本次导出所在目录，可以含有旧结果。|
|`manifest_path`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|本次带时间后缀的完成清单Path，直接使用实际返回路径。|
|`output_files`|tuple[[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path), ...]|是|无|本次导出的数据文件Path元组，不含由manifest_path单独提供的完成清单。|

源码：[`src/chronaxis/results/manifest.py:360`](../../../src/chronaxis/results/manifest.py#L360)（行号属于 `afc8d5eb1dc95c26176b20ebedaeda6a0a643540`）。
