# chronaxis.fast.run

`from chronaxis.fast import run`

<a id="api-run"></a>
## `run`

高性能积分器：读取一个ASC或BLF文件，对同帧公式逐报文累计，成功后发布结果。不是按真实帧间隔积分。

```python
run(config, output)
```

|名称|类型|必填|默认值|用途|
|---|---|---|---|---|
|`config`|见用途|是|无默认值|str或Path：单文件YAML/JSON配置路径。只接受fast支持的同帧逐报文累计配置；DBC与报文路径相对声明它们的配置文件。|
|`output`|见用途|是|无默认值|str或Path：结果目录，可已存在；使用本次时间标记文件，不覆盖既有结果。|

### 返回

pathlib.Path：本次run_manifest完成清单；从outputs取得实际结果文件名。没有目标帧时结果为空且保留原因，不伪造零。

### 异常

无效配置抛PlanValidationError；读取、解码或公式错误传播对应异常，本文件不发布正常累计结果。输出I/O失败传播OSError。此单文件入口没有cancel_event参数。

### 执行与资源

读取配置/DBC/输入，创建并发布结果文件，最后发布完成清单。支持范围与完整配置见高性能积分器教程。

[高性能积分器教程](../fast-energy.md)

源码：[`src/chronaxis/fast/run.py:54`](../../../src/chronaxis/fast/run.py#L54)（行号属于 `e65c920526335247bcc1ed25852bcc967f55f2fd`）。
