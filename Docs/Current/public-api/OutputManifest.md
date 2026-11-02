# chronaxis.OutputManifest

从`chronaxis`导入本对象。本页只列直接公开成员与必要的构造/上下文协议；内部实现见[模块参考](../reference/chronaxis.results.manifest.md)。

返回[公开API索引](../api.md)。参数表中的类型可跳转到定义；先核对必填、默认值与返回/异常说明。

## 成员导航

- [OutputManifest](#api-OutputManifest)

<a id="api-OutputManifest"></a>
## `OutputManifest`

保存成功发布目录、清单和固定白名单表行数；legacy只在启用时出现。

```python
OutputManifest(run_id: str, output_dir: pathlib.Path, manifest_path: pathlib.Path, output_files: tuple[pathlib.Path, ...], row_counts: tuple[tuple[str, int], ...], status: str = 'completed') -> None
```

### 属性与数据字段

|名称|数据类型|必填|省略时的值|用途、取值和效果|
|---|---|---|---|---|
|`run_id`|str|是|无|本次运行唯一标识，与发布清单及资源事实关联。|
|`output_dir`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|已经成功发布的结果目录绝对Path。|
|`manifest_path`|[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path)|是|无|已发布run_manifest.json的绝对Path。|
|`output_files`|tuple[[Path](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path), ...]|是|无|本次实际发布的文件路径元组。|
|`row_counts`|tuple[tuple[str, int], ...]|是|无|各固定结果表的实际行数记录。|
|`status`|str|否|'completed'|本次发布结果状态，成功为completed。|

源码：[`src/chronaxis/results/manifest.py:320`](../../../src/chronaxis/results/manifest.py#L320)（行号属于 `66a66ec751da79d6562f341e646dd7f47c726f68`）。
