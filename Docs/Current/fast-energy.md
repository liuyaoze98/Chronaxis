# 高性能积分器（同帧逐报文累计）

本积分器把每条匹配报文的表达式结果相加。用功率计算能量时，应在表达式中乘以该报文代表的持续时间，例如 `power * frame_duration`。如果每条报文已经提供能量贡献，则直接累计：两条贡献为 400 J、600 J 的报文合计 1000 J，无需再乘时间。

`frame_duration` 是示例自行定义的参数名，不是必填参数。运行器不会自动乘以相邻报文的实际时间间隔；需要由实际经过的时间确定积分量时，使用[时间积分](calculations.md#integrators)。

如果设备每记录一条功率报文就代表 0.1 秒，可以用 fast 把每条的「功率 × 0.1 秒」相加。同一次记录的多个分卷使用下面的单会话配置；多个独立试验使用fast batch。需要跨帧保持、事件或实际时间积分时使用通用分析入口。基础配置显式填写 `execution.process_count: 4`，最多使用4个文件工作进程读取、解码并计算单条报文贡献，再由主进程按规定顺序累计。进程数是上限：两个文件最多用两个，只有一个文件时在当前进程执行。省略该字段仍默认1。

可直接打开下面的[完整单文件示例](examples/fast/analysis.yaml)。另有[BLF 版本](examples/fast/analysis-blf.yaml)、[批量配置](examples/fast/batch.yaml)、[DBC](examples/fast/data/power.dbc) 和三份输入（[第一份 ASC](examples/fast/data/run2.asc)、[第二份 ASC](examples/fast/data/run10.asc)、[BLF](examples/fast/data/single.blf)）。

## 安装与运行

使用 Chronaxis 0.1.0.dev4 的本地 wheel，填写下方文件的实际路径。首次安装需要可取得项目依赖；同版源码安装方法见[安装说明](installation.md)。激活后切换到上面下载的分析配置所在目录，保持 data 子目录结构。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install ".\chronaxis-0.1.0.dev4-py3-none-any.whl"
.\.venv\Scripts\Activate.ps1
python -m chronaxis fast --help
```

```powershell
python -m chronaxis fast validate analysis.yaml
python -m chronaxis fast explain analysis.yaml
python -m chronaxis fast run analysis.yaml --output result-asc
python -m chronaxis fast run analysis-blf.yaml --output result-blf
python -m chronaxis fast batch batch.yaml --output result-batch --total
```

## 一份配置与实际数值

```yaml
config_version: 4                 # 声明分析配置结构版本；当前只接受整数4
dataset:                          # 命名本次分析并可选限定分析时间范围
  name: energy_demo               # 命名本次分析数据集；名称写入结果身份字段
sources:                          # 列出输入来源；每项规定数据位置、格式和时间解释方式
  - paths: data/run2.asc          # 指定本任务的输入；这里演示一个ASC文件，路径相对本配置
    dbc_by_channel:               # 为每个CAN通道指定解码用DBC文件；键是通道编号的字符串
      '1': data/power.dbc         # 为这个通道指定DBC文件；路径相对当前配置文件，通道键须为字符串
signals:                          # 定义公式使用的信号
  - name: power                   # 公式中的信号名称
    field:                        # 输入中的原始字段
      frame_id: 0x100             # 信号所属报文 ID
      signal: Power               # DBC 中的信号名
message_calculations:             # 每条目标报文计算一次并累计
  - name: energy                  # 结果表中的累计名称
    update_message:               # 触发公式的报文
      frame_id: 0x100             # 每来一条此 ID 的报文就计算
    parameters:                   # 每条报文使用的固定参数
      frame_duration:             # 每条目标报文计入的时间
        value: 0.1                # 每条报文按 0.1 秒累计
        unit: s                   # 该时间参数以秒计
    expr: power * frame_duration  # 定义单条目标消息的贡献；使用该报文信号和parameters常量
    unit: J                       # 声明累计结果的单位；须与表达式量纲相符
execution:                        # 设置本次分析的文件工作进程上限
  process_count: 4                # 最多4个；本例仅一个文件，在当前进程执行
```

YAML 通过缩进表示父子关系。`frame_id` 指向报文 0x100，`Power` 是 DBC 信号名，`power` 是用于公式的名字。DBC 将这条信号解成 W。通道 1 在配置中写为 DBC 映射的字符串键。公式参数 `frame_duration` 的 0.1 s 是每条报文计入能量的时间，只乘一次；它来自采集或业务定义。本例只用当条报文，不沿用前值，因此信号无需填写 `period` 或 `valid_for`。若需要按前后两条报文的实际间隔积分，使用通用 `chronaxis run` 的积分配置。

run2.asc 中 0 秒出现两条 4000 W 的目标报文，每条贡献 400 J，输出的 energy 为 **800 J**。这两条报文即使同刻也都参与计算。BLF 示例包含同样的两次有效读数，结果也是 800 J。终端返回本轮 manifest_path。打开该 JSON 的 outputs 所列 CSV，可见一行「计算项 energy，结果 800.0，单位 J，状态 完整」。重复运行时从本轮返回的路径读取结果。

## 同一次记录的多个分卷

这一功能由 `sources[].paths`、`sources[].file_merge` 和 `execution.process_count` 控制。把同一次充电的所有分卷放在同一个来源中，每个计算项会得到一个跨所有分卷的累计结果；切换文件不会重新累计。ASC、BLF 可以混用，目录和通配符沿用[输入路径规则](inputs.md)。各文件须采用已核实的时间解释；程序不会移动时间或自动删除重复记录。

完整可运行配置：[按文件顺序累计](examples/fast/session.yaml)、[按时间归并累计](examples/fast/session-time-order.yaml)。两个示例复用上文已经定义的 `power` 和 `energy`，下载文件本身包含全部定义、注释及执行设置。run2.asc 的两条和 run10.asc 的一条报文各贡献400J，整个会话得到 **1200J**；某个分卷没有目标报文，不会让其他分卷的有效贡献失效。

在上文完整配置中，替换根级 `sources` 和 `execution` 为下面两段，保留 `dataset`、`signals`、`message_calculations`。它们已经包含父键，不再添加同名父键。下载版还提供可选的资源配额，用于演示资源管理。

```yaml
sources:                   # 一个来源中的连续分卷
  - paths:                 # 按列表顺序处理，最终得到一项会话累计
      - data/run2.asc      # 第一卷含两条能量贡献
      - data/run10.asc     # 第二卷含一条能量贡献
    dbc_by_channel:        # 两卷使用同一通道与DBC
      '1': data/power.dbc  # 通道1的信号定义
execution:                 # 设置本次fast会话的文件工作进程上限
  process_count: 4         # 本例两个文件，实际最多两个工作进程
```

先用默认内存与暂存设置运行，需要限制资源时再填写下面的对应字段。省略 `execution` 与填写 `process_count: 4` 不等价：前者使用默认1，后者明确请求并行。

|字段或选项|控制什么及怎样填写|
|---|---|
|`sources[].paths`|同一来源的输入文件。填写一个路径、目录、通配符或路径列表；明确列表按声明顺序，目录/通配符按项目自然序规则展开。|
|`sources[].file_merge: concatenate`|默认值；先完整处理第一个文件，再处理下一个文件，保持每个文件内的记录顺序。后续文件可以并行求值并暂存。|
|`sources[].file_merge: time_order`|按映射后的时间归并。每文件匹配目标的候选数据报文须有序；检查先于分析范围过滤，不受方向桶或零贡献影响。相同时间按文件顺序、原始记录顺序处理。|
|`execution.process_count`|正整数，默认1；API或CLI显式参数优先于配置。1在当前进程执行；大于1时工作进程上限不超过文件数，不包含主进程。拒绝0、负数、小数、字符串、布尔值和配置中的null。|
|`execution.memory_budget_bytes`|正整数，默认268435456。按可用内存填写受管理空间的估算额度；包括工作缓冲及归并状态，不是整个进程树的物理内存上限。不足时报告资源错误。|
|`execution.spool_quota_bytes`|正整数或null，默认null。正整数限制累计预约的暂存字节数，删除文件不返还额度；null不设额外配额，仍可能磁盘写满。|

fast只接受表中三个 `execution` 字段。普通分析的 `backend`、`batch_rows` 等策略不适用于fast，显式填写会报错。改变进程数不会改变文件组织方式；需要时间归并时仍应明确填写 `file_merge: time_order`。

“暂存”是把已经算出、尚未轮到累计的报文贡献写入本次专用临时文件，之后由主进程读取；它不复制原始日志。内存预算约束程序登记的缓冲和状态估算，Python解释器、第三方库等仍会占用额外内存，因此不能把256MiB预算理解为整个任务最多占256MiB。

`concatenate` 的后续分卷预读空间不足时会暂停，轮到该文件后继续直接消费，可能降低速度。`time_order` 多文件任务需要先完成贡献暂存，配额不足会失败。实际写盘失败、损坏或缺失贡献块会使整个会话失败。各文件仍须满足其格式原有校验；拼接模式不能用来修复错误输入。

```powershell
python -m chronaxis fast validate session.yaml --process-count 4
python -m chronaxis fast explain session.yaml --process-count 4
python -m chronaxis fast run session.yaml --output result-session --process-count 4
python -m chronaxis fast run session-time-order.yaml --output result-time-order
```

`explain` 的 `worker_process_limit` 是静态上限，不是实际启动数；单进程内联时为0。完成清单的 `inputs` 列出全部文件，`execution.worker_pids` 给出实际工作进程，`execution.calculation_counts` 按计算项列出目标、范围内有效和方向入选数，Python 可读 `manifest["execution"]["calculation_counts"]`。默认 CSV 按「计算项、结果、单位、状态、说明」读取；只有显式选择 `outputs.tables: csv` 或 `jsonl` 交换格式时，才使用 `name/value/unit/status/reason` 字段。“完整”表示所选记录处理完成，不证明物理采集从未漏帧。

|某项计算在整个会话中的情况|结果含义|
|---|---|
|所有输入无记录|空值，`empty_file`。|
|有记录但无该项目标报文|空值，`no_target_frames`。|
|该项目标报文全部在分析范围外|空值，`no_target_in_domain`。|
|范围内有有效求值，但方向桶没有入选|0，`no_selected_direction`。|
|有入选贡献，贡献为0或相互抵消|有效的0，无缺失原因；零贡献仍计入入选数量。|
|任一必需分卷读取、解码、求值或关闭失败|整个会话失败，不发布正常成功汇总。|

不同进程数成功完成同一输入、配置、合并模式和运行环境时，未舍入数值一致。两种合并模式的相加顺序可能不同，不保证最后一位相同。fast不自动改成每文件部分和；独立batch仍在各任务进程内累计，不能用其总量替代本会话规则。

## 将同一份模板用于多个独立文件

```yaml
batch_version: 1               # 声明独立批量任务文件的结构版本；当前填写整数1
template: batch-analysis.yaml  # 单进程子模板；每个输入独立执行
inputs: data/*.asc             # 选择批量处理的文件、目录或通配符；每个文件是独立任务
process_count: 4               # 最多4个独立任务并行；两个输入最多用两个进程
```

下载[batch-analysis.yaml](examples/fast/batch-analysis.yaml)作为子模板。它与单独运行的分析使用相同公式，但显式设置 `execution.process_count: 1`；外层批量已并行运行各文件，不在子任务中再次建池。批量CLI可用 `--process-count` 覆盖根级数量。

本例按自然序分别处理 run2.asc 和 run10.asc。前者有两条报文，得到 800 J；后者有一条，得到 400 J。终端返回 report_path。批量报告的 jobs 列出逐文件状态，传入 `--total` 时，totals 中的 energy 为 **1200.0 J**，status 为 complete。只处理 BLF 时可以把 inputs 改为 `data/*.blf` 并选择相应模板。本例中不把 BLF 副本再计入同一总量。

单项总量要求该计算项在全部预期文件有有效结果。某个文件没有对应目标帧时，该项为 null；有有效目标帧但没有进入所请求的方向桶时，零可以参加求和。同一文件若发生公式错误（如除零）会失败。fast 在筛选目标帧后先求值，再按原 DBC 解码值分正/负方向。请先核实电流符号；正负不自动解释为充电或放电。普通多文件 paths 描述连续来源；要为每个文件新建累计状态，请使用批量模板。

## 配置被拒绝时

运行 `python -m chronaxis fast validate unsupported.yaml` 检查[拒绝示例](examples/fast/unsupported.yaml)。它要求 `outputs.contributions: full`。程序返回退出码 2，在 errors 中给出 `$.outputs.contributions`。需要逐报文贡献明细、跨 ID 保持电压、条件持续满 60 秒或时间窗口时，按其语义改用通用分析入口。fast 适合当前消息的同帧数值累计。

|任务需要什么|如何选择|
|---|---|
|单通道、同一 ID 的数值公式|用 fast 计算常量、四则运算和 abs。电流方向决定是否累计时使用正负分桶。|
|DBC 枚举标签、复用或容器报文、沿用另一个 ID 的信号，或事件窗口|按通用入口支持范围配置，或调整输入格式。fast 在打开日志前指出不支持的绑定。|
|受管理资源额度或完整贡献明细|fast流式读取，支持上述内存/暂存额度；完整贡献明细使用通用分析。两者的受管理预算均不等于整个进程树RSS硬上限。|
|缺观测或坏数据|没有目标帧时得到 null。相关报文解码或数值计算失败会使该文件失败；批量默认继续处理其他独立文件，各文件状态见批量报告的 jobs。|

## 用 Python 调用

```python
from chronaxis.fast import run

if __name__ == "__main__":
    manifest = run("session.yaml", "result-session", process_count=4)
    print(manifest)
```

处理多个独立文件时，将下面代码保存为 `run_fast_batch.py`，执行 `python run_fast_batch.py`。配置文件路径在此相对启动目录，配置内部路径相对配置文件。Windows 启动工作进程时会重新导入入口模块，因此将调用放在 `__main__` 保护内。

```python
from chronaxis.fast.batch import run_batch

if __name__ == "__main__":
    report_path = run_batch("batch.yaml", "result-batch", total=True)
    print(report_path)
```

返回值是批量报告路径。使用总量前先检查报告状态；失败或取消成员会使相应总量不可用。

### 函数参数与返回值

`run` 从 `chronaxis.fast` 导入，`run_batch` 从 `chronaxis.fast.batch` 导入；它们与通用 `chronaxis.run_batch` 是不同入口。

| 调用方式 | 返回值 |
|---|---|
| `run(config, output, *, process_count=None, work_dir=None, cancel_event=None)` | `pathlib.Path`：本轮完成清单；通过其中的 `outputs` 找到结果表。 |
| `run_batch(plan_path, output, *, process_count=None, cancel_event=None, total=False)` | `pathlib.Path`：批量报告，列出每项任务的状态及请求的总量。 |

| 参数 | 类型、默认行为与限制 |
|---|---|
| `config`、`plan_path` | JSON/YAML 文件路径，接受字符串或路径对象；相对调用进程的工作目录。不接受 `AnalysisPlan` 或字典。配置内部路径相对配置文件。 |
| `output` | 输出目录路径，可以已存在；带时间后缀的文件保留先前结果。 |
| `process_count` | 可选正整数，不接受布尔值；run省略沿用execution.process_count，run_batch省略沿用批量根级process_count；均默认1。实际数量不超过文件数/任务数。 |
| `cancel_event` | 可选 `threading.Event`。调用其 `set()` 请求取消：停止派发新任务，通知正在执行的 fast 工作进程停止并回收。run取消抛InterruptedError，不发布成功；run_batch各任务最终状态以批量报告为准。 |
| `work_dir` | 仅run支持：可选暂存父目录，省略用系统临时目录；本次调用管理自己的暂存，清理失败按下文重试。 |
| `total` | 布尔值，默认 `False`。`True` 只适用于同一模板展开的不同独立文件，要求计算定义和 DBC 绑定一致；不接受任意独立 jobs，也不会仅按列名相同就相加。 |

配置不合法时，在分析开始前抛出异常。单会话任一文件读取、解码、公式或发布失败时抛出异常，不发布正常成功总量。批量文件失败记录在对应任务中；除非配置 `fail_fast`，其他任务继续。执行环境故障可能抛出异常，已保存报告时异常可以带 `batch_report` 属性，但并非所有错误都有报告。键盘中断会清理后继续抛出中断。请求取消可以正常返回含取消任务的报告，因此拿到路径不等于全部成功。某计算项所需成员失败、取消或没有数值时，该项完整总量不可用。

`run` 的读取、计算或取消异常保留原类型。若会话清理没有完成，可从所捕异常读取 `getattr(exc, "fast_session_cleanup_owner", None)`，排除资源故障后调用该对象的 `close()`；不需要分别关闭它管理的各个子对象。恢复不会重新计算，也不会发布部分成功总量。该属性不保证存在，存在也可能指向后来已关闭的对象。批量恢复及工作进程构造期间的取消处理见[批量任务](batch.md)。

完整定义：[run](public-api/fast.run.md)、[run_batch](public-api/fast.batch.run_batch.md)。

维护者 liuyaoze。
