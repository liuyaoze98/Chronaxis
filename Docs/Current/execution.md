# 执行设置与资源管理



根级映射`execution`控制一个分析任务采用哪种计算实现、每批处理多少样本、可使用多少受管理内存和暂存磁盘，以及数据不完整时如何返回结果。它不选择输入文件，也不决定需要计算的业务内容；后两者分别由sources和calculations/rules等字段控制。

需要同时处理多个独立文件时，在单独的[批量配置](batch.md)根级填写`process_count`；该字段不放在`execution`内。`batch_rows`表示处理批次大小，不能用它设置进程数。

## 完整最小例与执行扩展

[calculation-minimal.yaml](examples/calculation-minimal.yaml)省略execution和diagnostics，用默认设置得到30J。[execution-diagnostics.yaml](examples/execution-diagnostics.yaml)使用完全相同输入，仅改为reference计算、每批1个样本、结果缓冲1行，并开启输入追溯；数值仍为30J，同时可读取input_trace。小批次用于观察分批行为，不是大文件性能推荐值。

[execution-report.yaml](examples/execution-report.yaml)与[execution-strict.yaml](examples/execution-strict.yaml)都请求0～12秒，但4000W输入只观测到8秒。前者得到32000J/partial，后者得到空值/indeterminate；数据和公式完全相同，只有partial_policy不同。

命令：`chronaxis run 文件名.yaml --output 结果目录`。先完成最小例，再按资源或诊断需求增加字段。默认运行无需填写execution。下段仅作为全部默认值的参考，不是需要复制的配置：

以下是可放入完整分析配置根级的片段。全部字段可省略，使用表中的默认值。

应用位置：以[analysis.yaml](examples/analysis.yaml)为基础，在文件根级加入或替换`execution`，代码已包含父键。保留未展示的其他根字段，不再添加第二个同名父键。

```yaml
execution:                          # 设置计算实现、资源上限和数据不全时的处理方式
  backend: numpy                    # 选择计算实现；numpy使用数组，reference使用独立参考计算
  batch_rows: 65536                 # 限制一次交给分析层的记录数；按内存和处理开销选择，不是采样周期
  memory_budget_bytes: 268435456    # 限制新分析层管理的内存字节数；按可用内存留出其他进程开销
  result_buffer_rows: 4096          # 限制结果写入前在内存积累的行数；按结果大小和内存选择
  spool_quota_bytes: null           # 限制本次分析临时数据的磁盘字节数；按可用磁盘空间选择
  partial_policy: report            # 设置默认的数据不全处理；report保留已知部分，strict不给不完整数值
  on_budget_exceeded: error         # 选择资源超限处理；当前填error，中止并报告，不丢数据继续
```

## 全部运行字段

本页主字段表相对于`execution`，例如`execution.backend`。子对象另行注明，表中的字段不能直接放到配置根级。

execution本身可以省略。填写时使用根级映射，例如`execution: {batch_rows: 1000}`。以下七个字段均为可选项；数字不加引号，字符串按[YAML语法](configuration-language.md)填写。各项的具体影响在后文解释。除spool_quota_bytes允许null外，其余字段不要用null代替省略；预算/行数必须是正整数，0和布尔true/false均不是合法额度。

|字段|数据类型|必填|默认值|可填写的值及含义|
|---|---|---|---|---|
|backend|字符串|否|`"numpy"`|选择执行数值计算的实现；通常用numpy，需要独立复算时用reference。`"numpy"`使用数组计算；`"reference"`使用独立实现作对照。|
|batch_rows|整数|否|65536|控制一次交付的信号样本数量，按内存与批次切换开销选择。大于0；每批交付的信号样本数上限。|
|memory_budget_bytes|整数|否|268435456|限制引擎可分配的受管理内存，按机器可用资源以字节设置。大于0，单位字节；新分析部分管理的内存额度。|
|result_buffer_rows|整数|否|4096|限制暂存前积累的结果行数，按结果数量和缓冲开销选择。大于0；结果写入暂存前积累的行数上限。|
|spool_quota_bytes|整数或null|否|`null`|限制本任务受管理的暂存磁盘用量，按工作目录可用空间以字节设置。正整数：暂存的磁盘额度，单位字节；null：不另外设置配额。|
|partial_policy|字符串|否|`"report"`|选择数据不完整时是否保留已知部分的数值，按是否允许部分结果选择。`"report"`返回已知部分并标注；`"strict"`在所需数据不全时返回空值。|
|on_budget_exceeded|字符串|否|`"error"`|选择受管理资源不足时的处理方式；目前只能停止并报错。当前填写 `"error"`，表示额度不足时报错并停止；没有丢弃部分数据继续计算的选项。|

## backend：计算实现

“后端”在这里指计算实现，不是服务器，也不需要另开一个服务。

|值|程序做什么|什么时候用|
|---|---|---|
|`numpy`（默认）|使用NumPy数组完成支持的数值运算；读文件和事件状态管理仍由Python代码处理|日常分析先用这个选项|
|`reference`|使用另一套独立的数值实现计算，便于与NumPy结果对照|怀疑计算结果有问题时，用相同输入和配置换它复算|

两种实现遵守相同的单位、有效期和缺失数据规则。更换backend不应把4000J变成另一种业务含义；但不能因此承诺所有任务的速度相同，或者numpy一定更快。

YAML写法见上例的`execution.backend`。Python中`AnalysisRunner(backend="reference")`和CLI的`--backend reference`可覆盖该次运行的选择，运行清单记录实际选择。两种方式都使用本项目既有依赖，不表示reference版可以忽略安装要求。

## batch_rows：输入批次大小

批次就是“分批处理”。例如有十万条样本，可以先处理第一批，再处理第二批，而不是同时把所有记录放入内存。

`execution.batch_rows`默认65536，控制来源交给分析器的一批样本数量上限。它不是时间长度，也不是最多读取65536条后就停止；按全部信号列的样本数相加计数，不按CSV宽表行数计数。例如一行CSV同时更新功率和状态，这一行就产生两条信号样本。

假设设备从1秒一直工作到4秒，某批数据恰好在2秒结束，下一批从3秒接着读。程序会保留“设备还在工作”的状态，最终仍应得到1—4秒的一次活动，不会在每个批次交界处人为切断。

- 降低批次数量上限通常减少一次交付的数据量，但会增加批次切换次数。
- 提高上限可能减少切换，但一次保留的数据更多。
- 批次大小不是整个程序的内存上限：事件状态、历史数据、结果缓冲和旧解码库还会使用资源。

教程使用`batch_rows=1`是为了让只有5行的数据也经过多次分批，检查批次交界处理；不是推荐真实日志都逐条运行。

## memory_budget_bytes：受管理内存额度

这里的“预算”是资源上限，与金额或模型用量无关。默认268435456字节，即256MiB；1MiB等于1024×1024字节。

程序给自己管理的缓冲、状态等申请额度，额度不够就报错。它不会丢弃部分数据来继续输出一个看似完整的结果。这个数**不是整个Python进程的硬性内存限制**：旧解码库、Python本身以及未计入该额度的开销还会占内存。

若出现`BudgetExceededError`，先看异常指出的是哪项资源。内存缓冲不足时，可尝试降低`batch_rows`或`result_buffer_rows`；如果维持业务状态本身就需要更多空间，单纯减小批次未必解决。确有足够机器内存时，再提高`memory_budget_bytes`。

`on_budget_exceeded`目前只支持`"error"`。不能填`"skip"`让程序丢数据继续。

样本最小值、最大值和均值在汇总样本时会根据共享预算的剩余空间自动拆成较小计算块；同一任务的读取队列和其他计算项也计入这份预算。拆块不丢样本，不改变结果、有效期或条件范围，也不降低资源检查要求。普通任务无需为此新增配置。

如果连最小计算块都放不下，错误会指出计算项名称、样本统计工作区以及当前可用字节数。先检查是否请求了无用统计，再考虑减少读取批量；只有确认机器和任务所需空间后才提高内存额度。预算数是保守的管理估算，不是任务管理器中的实际进程内存。

## 结果缓冲与暂存配额

结果很多时，程序把完成的结果逐步写入工作目录，再从那里生成最终输出。这个过程称为“暂存”。

|参数|默认值|控制什么|
|---|---|---|
|`result_buffer_rows`|4096|结果写入暂存前，一批在内存中积累的行数上限；不是只保留前4096个结果|
|`spool_quota_bytes`|`null`|受管理的暂存所允许使用的磁盘额度；null表示没有设置这一额外上限，磁盘本身仍可能写满|

例如`spool_quota_bytes=1073741824`表示1GiB。超过指定额度会失败，并保留已有诊断。`close()`默认关闭资源并清理程序为本次运行创建的临时数据；明确设置diagnostics.retain_work=true时才保留现场。原始输入和已发布结果不因此删除。

## partial_policy：部分结果处理

另用一组恒功率数据作为对照：请求计算0—12秒，功率一直为4000W，但日志只记录到8秒。

已经知道的8秒能量为`4000 × 8 = 32000J`。剩余4秒没有观测记录，程序不知道功率是多少，因此不能声称12秒总能量为48000J。

|设置|value|status|怎么理解|
|---|---|---|---|
|`report`（默认）|32000J|`partial`|给出已知部分的能量，并明确它不是12秒完整结果|
|`strict`|`null`，Python里为None|`indeterminate`|所需范围不完整，不给该指标的数值；仍给原因和覆盖信息|

report不会猜缺失部分，也不会把缺失值改成0。若从头到尾都没有可计算的数据，即使选report也不能得到正常的0。

可以给全部计算项设置默认值：

应用位置：以[analysis.yaml](examples/analysis.yaml)为基础，在文件根级加入或替换`execution`，代码已包含父键。保留未展示的其他根字段，不再添加第二个同名父键。

```yaml
execution:                  # 设置计算实现、资源上限和数据不全时的处理方式
  partial_policy: strict    # 设置默认的数据不全处理；report保留已知部分，strict不给不完整数值
```

如果已把execution.partial_policy设为strict，也可以让某一项仍返回已知部分：

应用位置：以[analysis.yaml](examples/analysis.yaml)为基础，在文件根级加入或替换`calculations`，代码已包含父键。保留未展示的其他根字段，不再添加第二个同名父键。

```yaml
calculations:                 # 本例的统计结果
  - name: session_energy      # 结果表中的计算名称
    expr: power               # 使用已定义的信号或公式
    partial_policy: report    # 决定数据不全时是否保留可核实数值；report保留并标记，strict返回空值
    operation: integral       # 按有效持续时间积分
```

单个计算项里的设置优先于execution默认值。上面都是放进完整配置的片段；完整例子在[快速上手](quickstart.md)。

<a id="diagnostics"></a>
## 诊断与现场保留

根级`diagnostics`决定额外保留哪些追溯资料。三个开关相互独立，默认均为false；省略整个映射或填写{}使用默认值，null不合法。它们不改变计算公式。默认不保留输入追溯与额外内容摘要；逐消息贡献独立选择。关闭时清理程序为本次运行创建的临时数据，原始输入与已经发布的输出不删除。

| 完整路径 | 控制作用及取值依据 | true的效果 | false（默认）的效果 |
|---|---|---|---|
| diagnostics.trace | 控制是否记录所用输入的详细追溯；需要逐条定位来源时开启 | 保存任务实际需要的输入记录，提供input_trace表及iter_input_trace() | 不保存该详细表，调用迭代器会报AnalysisError；不是自动保留全日志 |
| diagnostics.integrity | 控制是否增加内容摘要和完整性诊断；需要核对输入输出内容时开启 | 增加相关输入/输出内容摘要和完整性诊断 | 仍执行必要文件身份、大小和结构检查，不承诺额外内容哈希 |
| diagnostics.retain_work | 控制结果关闭或运行失败后是否保留临时现场；需要进一步排错时开启 | close或失败后保留本次工作现场供排错 | 清理本次运行的临时数据；不删除原始输入或正式输出 |

应用位置：以[analysis.yaml](examples/analysis.yaml)为基础，在文件根级加入或替换`diagnostics`，代码已包含父键。保留未展示的其他根字段，不再添加第二个同名父键。

```yaml
diagnostics:     # 选择是否额外记录定位信息、校验摘要以及保留临时数据
  trace: true    # 控制是否记录详细定位信息；true增加追溯记录，false使用默认简要信息
```

逐消息贡献另由`outputs.contributions: full`开启。运行环境备注放在根级`metadata`映射中；metadata默认{}，不会替代execution或diagnostics。独立信号/CAN导出另有[当前设备标签限制](exports.md)。

## 计算项的覆盖门槛

`minimum_coverage`属于计算项或支持它的预设参数，不属于execution；字段与例子见[统计与积分](calculations.md)。

## 一份可直接运行的对照

[readability_examples.py](examples/readability_examples.py)使用同一份5行输入，比较两个backend、不同batch_rows及report/strict，并断言事件数和能量。该脚本还运行表达式说明中的每项例子，失败时直接报错。

```powershell
python -B Docs/Current/examples/readability_examples.py
```

脚本默认把输出放在系统临时目录中新建的独立目录；可用--output-root指定既有父目录，合成数据的阈值不代表真实设备应采用这些阈值。

## 根级metadata与运行来源标签

metadata保存运行附加信息，缺省为空对象。其中metadata.device_label被程序读取，用于运行清单的设备来源标签；其他备注不会改变计算。

|入口|填写位置、默认及限制|
|---|---|
|普通分析|根级metadata.device_label；非空文本，如lab_pc；省略为pending，空白文本无效。CLI普通run不以CHRONAXIS_DEVICE_LABEL自动覆盖它。|
|含独立信号或CAN文件导出的分析|同一字段必须为home或work，表示已经确认的产出设备；不能使用pending或自定义文本。|
|批量总报告|CLI从CHRONAXIS_DEVICE_LABEL取得；Python使用run_batch的device_label参数，缺省pending。不会覆盖每个子分析的metadata.device_label。|

普通分析可在根级填写：

```yaml
metadata:                 # 保存说明性信息；字段不会自动校准数据或更改计算公式
  device_label: lab_pc    # 记录产出设备标签；当前独立导出仅接受home/work，普通分析与批量报告规则见对应说明
```
