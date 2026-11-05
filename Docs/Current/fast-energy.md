# 高性能积分器（同帧逐报文累计）

本积分器把每条匹配报文的表达式结果相加。用功率计算能量时，应在表达式中乘以该报文代表的持续时间，例如 `power * period`。如果每条报文已经提供能量贡献，则直接累计：两条贡献为 400 J、600 J 的报文合计 1000 J，无需再乘时间。

`period` 是示例自行定义的参数名，不是必填参数。运行器不会自动乘以相邻报文的实际时间间隔；需要由实际经过的时间确定积分量时，使用[时间积分](calculations.md#integrators)。

如果设备每记录一条功率报文就代表 0.1 秒，可以用 fast 把每条的「功率 × 0.1 秒」相加。多个独立文件使用fast batch；需要跨连续分卷保留状态时使用通用分析入口。可直接打开下面的[完整单文件示例](examples/fast/analysis.yaml)。另有[BLF 版本](examples/fast/analysis-blf.yaml)、[批量配置](examples/fast/batch.yaml)、[DBC](examples/fast/data/power.dbc) 和三份输入（[第一份 ASC](examples/fast/data/run2.asc)、[第二份 ASC](examples/fast/data/run10.asc)、[BLF](examples/fast/data/single.blf)）。

## 安装与运行

安装 Chronaxis 0.1.0.dev2。首次安装需要可取得项目依赖；本地 wheel 安装方法见[安装说明](installation.md)。激活后切换到上面下载的分析配置所在目录，保持 data 子目录结构。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install "chronaxis==0.1.0.dev2"
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
config_version: 4            # 声明分析配置结构版本；当前只接受整数4
dataset:                     # 设置本次分析名称及可选的对象、会话和时间范围
  name: energy_demo          # 命名本次分析数据集；名称写入结果身份字段
sources:                     # 列出输入来源；每项规定数据位置、格式和时间解释方式
  - paths: data/run2.asc     # 指定本任务唯一ASC/BLF文件；相对路径基于本配置，展开后须恰好一个文件
    dbc_by_channel:          # 为每个CAN通道指定解码用DBC文件；键是通道编号的字符串
      '1': data/power.dbc    # 为这个通道指定DBC文件；路径相对当前配置文件，通道键须为字符串
signals:                     # 定义公式使用的信号
  - name: power              # 公式中的信号名称
    field:                   # 输入中的原始字段
      frame_id: 0x100        # 信号所属报文 ID
      signal: Power          # DBC 中的信号名
    period: 100ms            # 声明本信号正常更新周期；从设备/采集规范取得，省略valid_for时按其3倍确定有效期
message_calculations:        # 每条目标报文计算一次并累计
  - name: energy             # 结果表中的累计名称
    update_message:          # 触发公式的报文
      frame_id: 0x100        # 每来一条此 ID 的报文就计算
    parameters:              # 每条报文使用的固定参数
      period:                # 每条目标报文计入的时间
        value: 0.1           # 每条报文按 0.1 秒累计
        unit: s              # 该时间参数以秒计
    expr: power * period     # 定义单条目标消息的贡献；使用该报文信号和parameters常量
    unit: J                  # 声明累计结果的单位；须与表达式量纲相符
```

YAML 通过缩进表示父子关系。`frame_id` 指向报文 0x100，`Power` 是 DBC 信号名，`power` 是用于公式的名字。DBC 将这条信号解成 W。通道 1 在配置中写为 DBC 映射的字符串键。这里信号周期填 100 ms，用于信号声明；公式中的 0.1 s 是每条报文计入能量的时间，只乘一次。放到自己的设备上前要核实这个工程口径。若需要按前后两条报文的实际间隔积分，使用通用 `chronaxis run` 的积分配置。

run2.asc 中 0 秒出现两条 4000 W 的目标报文，每条贡献 400 J，输出的 energy 为 **800 J**。这两条报文即使同刻也都参与计算。BLF 示例包含同样的两次有效读数，结果也是 800 J。终端返回本轮 manifest_path。打开该 JSON 的 outputs 所列 CSV，可见一行「计算项 energy，结果 800.0，单位 J，状态 完整」。重复运行时从本轮返回的路径读取结果。

## 将同一份模板用于多个独立文件

```yaml
batch_version: 1           # 声明独立批量任务文件的结构版本；当前填写整数1
template: analysis.yaml    # 指定批量任务重复使用的分析配置路径；每个输入独立执行该配置
inputs: data/*.asc         # 选择批量处理的文件、目录或通配符；每个文件是独立任务
process_count: 2           # 限制分析工作进程数；正整数，1表示一个工作进程依次执行
```

本例按自然序分别处理 run2.asc 和 run10.asc。前者有两条报文，得到 800 J；后者有一条，得到 400 J。终端返回 report_path。批量报告的 jobs 列出逐文件状态，传入 `--total` 时，totals 中的 energy 为 **1200.0 J**，status 为 complete。只处理 BLF 时可以把 inputs 改为 `data/*.blf` 并选择相应模板。本例中不把 BLF 副本再计入同一总量。

单项总量要求该计算项在全部预期文件有有效结果。某个文件没有对应目标帧时，该项为 null；有有效目标帧但没有进入所请求的方向桶时，零可以参加求和。同一文件若发生公式错误（如除零）会失败。fast 在筛选目标帧后先求值，再按原 DBC 解码值分正/负方向。请先核实电流符号；正负不自动解释为充电或放电。普通多文件 paths 描述连续来源；要为每个文件新建累计状态，请使用批量模板。

## 配置被拒绝时

运行 `python -m chronaxis fast validate unsupported.yaml` 检查[拒绝示例](examples/fast/unsupported.yaml)。它要求 `outputs.contributions: full`。程序返回退出码 2，在 errors 中给出 `$.outputs.contributions`。需要逐报文贡献明细、跨 ID 保持电压、条件持续满 60 秒或时间窗口时，按其语义改用通用分析入口。fast 适合当前消息的同帧数值累计。

|任务需要什么|如何选择|
|---|---|
|单通道、同一 ID 的数值公式|用 fast 计算常量、四则运算和 abs。电流方向决定是否累计时使用正负分桶。|
|DBC 枚举标签、复用或容器报文、沿用另一个 ID 的信号，或事件窗口|按通用入口支持范围配置，或调整输入格式。fast 在打开日志前指出不支持的绑定。|
|硬内存上限或完整贡献明细|使用支持相应设置的通用计划。fast 由每个 worker 整文件读取，增加 process_count 时要考虑各文件同时驻留的内存。|
|缺观测或坏数据|没有目标帧时得到 null。相关报文解码或数值计算失败会使该文件失败；批量默认继续处理其他独立文件，各文件状态见批量报告的 jobs。|

## 用 Python 调用

```python
from chronaxis.fast import run

manifest = run("analysis.yaml", "result-asc")
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
| `run(config, output)` | `pathlib.Path`：本轮完成清单；通过其中的 `outputs` 找到结果表。 |
| `run_batch(plan_path, output, *, process_count=None, cancel_event=None, total=False)` | `pathlib.Path`：批量报告，列出每项任务的状态及请求的总量。 |

| 参数 | 类型、默认行为与限制 |
|---|---|
| `config`、`plan_path` | JSON/YAML 文件路径，接受字符串或路径对象；相对调用进程的工作目录。不接受 `AnalysisPlan` 或字典。配置内部路径相对配置文件。 |
| `output` | 输出目录路径，可以已存在；带时间后缀的文件保留先前结果。 |
| `process_count` | 可选正整数，不接受布尔值；省略沿用批量配置。实际工作进程数不超过任务数。 |
| `cancel_event` | 可选 `threading.Event`。调用其 `set()` 请求取消：停止派发新任务，通知正在执行的 fast 工作进程停止并回收。各文件最终状态以报告为准。 |
| `total` | 布尔值，默认 `False`。`True` 只适用于同一模板展开的不同独立文件，要求计算定义和 DBC 绑定一致；不接受任意独立 jobs，也不会仅按列名相同就相加。 |

配置不合法时，在分析开始前抛出异常。单文件读取、解码、公式或发布失败时抛出异常，不发布正常成功总量。批量文件失败记录在对应任务中；除非配置 `fail_fast`，其他任务继续。执行环境故障可能抛出异常，已保存报告时异常可以带 `batch_report` 属性，但并非所有错误都有报告。键盘中断会清理后继续抛出中断。请求取消可以正常返回含取消任务的报告，因此拿到路径不等于全部成功。某计算项所需成员失败、取消或没有数值时，该项完整总量不可用。

完整定义：[run](public-api/fast.run.md)、[run_batch](public-api/fast.batch.run_batch.md)。

维护者 liuyaoze。
