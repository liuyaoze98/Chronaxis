# chronaxis.fast.run

`from chronaxis.fast import run`

<a id="api-run"></a>
## `run`

高性能积分器：一个会话管理一个或多个ASC/BLF分卷，按确定顺序累计同帧贡献并发布一次汇总。

```python
run(config: str | pathlib.Path, output: str | pathlib.Path, *, process_count: int | None = None, work_dir: str | pathlib.Path | None = None, cancel_event: object | None = None) -> pathlib.Path
```

|名称|类型|必填|默认值|用途|
|---|---|---|---|---|
|`config`|str &#124; pathlib.Path|是|无默认值|YAML/JSON分析配置路径；一个来源的paths列出同一会话分卷，内部路径相对配置文件。仅支持fast当前帧数值子集。|
|`output`|str &#124; pathlib.Path|是|无默认值|结果目录，可已存在；使用本次时间标记文件，不覆盖既有结果。|
|`process_count`|int &#124; None|否|None|可选正整数工作进程上限，不含主进程；None沿用execution.process_count，默认1内联。超过文件数时按文件数限制，拒绝bool，不修改原配置。|
|`work_dir`|str &#124; pathlib.Path &#124; None|否|None|可选暂存父目录，None使用系统临时目录；本次创建的私有暂存完成或失败后清理。|
|`cancel_event`|object &#124; None|否|None|可选带is_set()的取消事件，例如threading.Event；set()请求停止调度并清理，run抛InterruptedError，不发布成功汇总。|

### 返回

pathlib.Path：本次完成清单。inputs列出全部文件，outputs列出结果表；每项独立判断空值/有效零，某分卷无目标不使其他有效贡献失效。

### 异常

PlanValidationError为配置不合法；ValueError为非法覆盖或数值/协议问题；资源超额、worker故障可抛RuntimeError；取消抛InterruptedError；文件和发布错误可抛OSError。任一必需文件失败均不发布正常会话结果。会话异常保留原类型；清理未完成时，原异常可能带fast_session_cleanup_owner，排除资源故障后调用该对象close，不必分别关闭子对象。该属性不保证存在，也可能在后续重试后指向已关闭对象。

### 执行与资源

读取配置/DBC及分卷；工作进程求单帧贡献，主进程逐条累计。单进程内联；time_order多文件需暂存。Windows多进程调用须置于`if __name__ == "__main__":`保护中，清单最后发布。

[高性能积分器教程](../fast-energy.md)

源码：[`src/chronaxis/fast/run.py:65`](../../../src/chronaxis/fast/run.py#L65)（行号属于 `8904c2f744951857659abd40aaa3535d57faf53c`）。
