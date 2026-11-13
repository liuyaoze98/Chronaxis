# 执行设置与资源管理

根级映射 `execution` 控制一次分析怎样运行：使用多少文件工作进程、采用哪种计算实现、分配多少受管理资源，以及怎样返回数据不完整的结果。输入文件由 `sources` 选择，计算内容由 `calculations`、`rules` 等字段定义。

## 基础配置：设置并行进程数

对同一次试验的 ASC／BLF 连续分卷，推荐先设置最多 4 个文件工作进程。普通分析由工作进程读取、解析和 DBC 解码，主进程接续信号状态、检测事件并完成计算。使用[高性能积分器](fast-energy.md)时，工作进程还会计算每条报文的贡献。

下面的片段放在完整分析配置根级；已有 `execution` 时，只增加或修改其中的 `process_count`，保留其他设置。与 `dataset`、`sources` 对齐，不添加第二个同名父键。

```yaml
execution:          # 设置本次分析的运行方式
  process_count: 4  # 最多4个文件工作进程，主进程另计
```

`4` 是示例推荐的上限，不是程序默认值。省略仍为 `1`；有两个文件时最多使用两个文件工作进程，只有一个文件时不会拆成四份并行计算。根据电脑的 CPU、内存和同时运行的其他程序，可以改为 `2`、`4`、`8` 等正整数。先运行完整的[连续分卷示例](examples/continuous-parallel.yaml)：两份 ASC 共同得到 **38 J**，文件边界不切断积分。

|输入或任务|进程数放在哪里|本手册的基础写法|
|---|---|---|
|同一来源的 ASC／BLF 连续分卷|分析配置的 `execution.process_count`|填写 `4`；来源保留默认的按需解码。支持范围见[连续记录](continuous-files.md)。|
|多个相互独立的试验|[批量配置](batch.md)根级 `process_count`|批量填写 `4`，每个子分析填写 `execution.process_count: 1`，避免重复建立进程池。|
|CSV、内存、多个来源或全部信号解码|分析配置的 `execution.process_count`|当前填写 `1`。多个独立分析可通过上一行的批量入口并行。|

`batch_rows` 控制一次交给分析器的样本数，不是进程数。修改并行上限也不会自动排序文件；文件接续和时间归并见[连续记录](continuous-files.md)。

## 完整最小例与执行扩展

[calculation-minimal.yaml](examples/calculation-minimal.yaml)读取随册的一个 ASC 文件，并用 teaching.dbc 解码功率，得到30J。配置保留基础上限 `process_count: 4`；本例是单 ASC 文件且使用默认 `file_merge: concatenate`，读取和分析都在当前进程内完成，不创建文件工作进程。这一说明仅针对本例的输入和文件组织方式。

[execution-diagnostics.yaml](examples/execution-diagnostics.yaml)使用相同 ASC／DBC，改为reference计算、每批1个样本、结果缓冲1行，并开启输入追溯；数值仍为30J，同时可读取input_trace。小批次用于观察分批行为，不是大文件性能推荐值。

[execution-report.yaml](examples/execution-report.yaml)与[execution-strict.yaml](examples/execution-strict.yaml)都请求0～12秒，但4000W输入只观测到8秒。前者得到32000J/partial，后者得到空值/indeterminate；数据和公式完全相同，只有partial_policy不同。

命令：`chronaxis run 文件名.yaml --output 结果目录`。先按上表选择进程数，再按实际需要增加资源或诊断字段。下段列出程序的全部默认值，供查阅；普通 ASC／BLF 配置通常只需上面的 `process_count`。

以下是可放入完整分析配置根级的片段。全部字段可省略，使用表中的默认值。

应用位置：以[analysis.yaml](examples/analysis.yaml)为基础，在文件根级加入或替换`execution`，代码已包含父键。保留未展示的其他根字段，不再添加第二个同名父键。

```yaml
execution:                        # 设置计算实现、资源上限和数据不全时的处理方式
  process_count: 1                # 设置本任务读取/解码工作进程上限；不包含主进程，默认1
  backend: auto                   # 按整个计划选择计算实现；可省略，显式reference/numpy固定使用对应实现
  batch_rows: 65536               # 限制一次交给分析层的记录数；按内存和处理开销选择，不是采样周期
  memory_budget_bytes: 268435456  # 限制新分析层管理的内存字节数；按可用内存留出其他进程开销
  result_buffer_rows: 4096        # 限制结果写入前在内存积累的行数；按结果大小和内存选择
  spool_quota_bytes: null         # 限制本次分析临时数据的磁盘字节数；按可用磁盘空间选择
  partial_policy: report          # 设置默认的数据不全处理；report保留已知部分，strict不给不完整数值
  on_budget_exceeded: error       # 选择资源超限处理；当前填error，中止并报告，不丢数据继续
```

## 全部运行字段

本页主字段表相对于`execution`，例如`execution.backend`。子对象另行注明，表中的字段不能直接放到配置根级。

execution本身可以省略。填写时使用根级映射，例如`execution: {batch_rows: 1000}`。下列字段均可省略；数字不加引号，字符串按[YAML语法](configuration-language.md)填写。各项的具体影响在后文解释。除spool_quota_bytes允许null外，其余字段不要用null代替省略；预算/行数必须是正整数，0和布尔true/false均不是合法额度。

|字段|数据类型|必填|默认值|可填写的值及含义|
|---|---|---|---|---|
|process_count|整数|否|1|控制本任务共用的文件读取/解码进程上限。填写正整数，按可用CPU和内存设置；不包含主进程，不超过可处理文件数。默认1；不能填null或布尔值。当前支持范围见[连续多进程](continuous-files.md)。|
|backend|字符串|否|`"auto"`|选择数值计算实现。`auto`按整份计划选择已验证的实现；`numpy`、`reference`固定使用对应实现。下表说明适用范围。|
|batch_rows|整数|否|65536|控制一次交付的信号样本数量，按内存与批次切换开销选择。大于0；每批交付的信号样本数上限。|
|memory_budget_bytes|整数|否|268435456|限制引擎可分配的受管理内存，按机器可用资源以字节设置。大于0，单位字节；分析状态及文件工作进程受管理缓冲共用的内存额度。|
|result_buffer_rows|整数|否|4096|限制暂存前积累的结果行数，按结果数量和缓冲开销选择。大于0；结果写入暂存前积累的行数上限。|
|spool_quota_bytes|整数或null|否|`null`|限制本任务受管理的暂存磁盘用量，按工作目录可用空间以字节设置。正整数：暂存的磁盘额度，单位字节；null：不另外设置配额。|
|partial_policy|字符串|否|`"report"`|选择数据不完整时是否保留已知部分的数值，按是否允许部分结果选择。`"report"`返回已知部分并标注；`"strict"`在所需数据不全时返回空值。|
|on_budget_exceeded|字符串|否|`"error"`|选择受管理资源不足时的处理方式；目前只能停止并报错。当前填写 `"error"`，表示额度不足时报错并停止；没有丢弃部分数据继续计算的选项。|

## backend：计算实现

“后端”在这里指计算实现，不是服务器，也不需要另开一个服务。

|值|程序做什么|什么时候用|
|---|---|---|
|`auto`（默认）|在读取日志前按计划类别选择reference或numpy，不试跑比较速度|日常分析可省略backend，由程序选择|
|`numpy`|内建流式表达式直接逐点计算；适合整批处理的计算仍用NumPy数组，扩展调用所登记的numpy实现|需要固定使用NumPy实现作对照时使用|
|`reference`|使用另一套独立的数值实现计算，便于与NumPy结果对照|怀疑计算结果有问题时，用相同输入和配置换它复算|

`auto`目前为两类计划选择reference：单个独立信号CSV的一路信号实际时间积分，以及同一CAN来源、同一报文定位、最多两路信号的简单实际时间积分。整份计划只能包含会话范围的ZOH积分和内建简单算术，且每个积分都未设置`condition`；包含事件、窗口、时序变换、其他统计、查表或宿主扩展时使用numpy。选择只看配置，不预读数据；运行错误直接报告，不换实现重跑。

例如[最小积分配置](examples/calculation-minimal.yaml)的`explain.selected_backend`为`reference`。复制该文件，只在原`calculations`的energy列表项中增加`condition: power > 0`，再次运行`python -m chronaxis explain 配置路径 --format json`，`selected_backend`变为`numpy`；无需先声明事件或窗口。两个计划都合法。这里选择的是普通运行器的数值后端，不会自动改用独立fast入口。

选择auto的同帧CAN积分会在绑定明确、且未请求信号导出、原帧导出、追溯或完整性诊断时使用直接积分路径；ASC、BLF、原始报文CSV及连续分卷共用这个规则。绑定不能明确证明适用时，读取首帧前改用通用流程；运行失败仍直接报错。显式reference/numpy使用各自通用流程。

这仍是实际时间积分。例如0秒4000W，0.12秒更新为4800W，采集在0.30秒结束且信号一直有效，结果为4000×0.12＋4800×0.18＝1344J。它不会自动改用DBC周期，也不改变[高性能积分器](fast-energy.md)直接累计逐条表达式贡献的含义。

两种实际计算实现遵守相同的单位、有效期和缺失数据规则。更换backend不应把4000J变成另一种业务含义；但不能因此承诺所有任务的速度相同，或者numpy一定更快。

YAML写法见上例的`execution.backend`。Python中`AnalysisRunner(backend="reference")`和CLI的`--backend reference`可覆盖该次运行的选择，`explain`的`requested_backend`、`selected_backend`和`backend_reason`分别说明请求、静态选择和原因。运行清单的`backend`记录实际使用的reference或numpy；auto本身不是第三套数值算法。批量配置指定auto时，每个子任务独立选择。两种方式都使用本项目既有依赖，不表示reference版可以忽略安装要求。

## batch_rows：输入批次大小

批次就是“分批处理”。例如有十万条样本，可以先处理第一批，再处理第二批，而不是同时把所有记录放入内存。

`execution.batch_rows`默认65536，控制来源交给分析器的一批样本数量上限。它不是时间长度，也不是最多读取65536条后就停止；按全部信号列的样本数相加计数，不按CSV宽表行数计数。例如一行CSV同时更新功率和状态，这一行就产生两条信号样本。

独立信号CSV（`signal_csv`）会按实际读入的内容和当前剩余预算组批，不为65536条样本预先分配整批空间。接近容量时先交付已读到的样本，再继续读取；每批可能少于这个上限。同一行的多个信号也可以分到相邻批次，更新顺序、数值、有效期和事件状态保持不变。这是信号CSV读取器的处理方式，不代表所有来源都会按预算自动缩小批次。

如果连一条所需记录及必要的解析、交接状态都放不下，仍会报告`BudgetExceededError`，不会截断或丢弃数据。正常CSV任务可先使用默认批次设置；出现错误时按报错资源定位，再决定是否调整配置。受管理预算是引擎的资源估算，不保证整个进程的实际内存（RSS）低于该值。

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

应用位置：以[analysis.yaml](examples/analysis.yaml)为基础，在已有 `execution` 内增加或修改 `partial_policy`。下面同时保留基础并行设置；其他执行字段如已填写，继续保留，不再添加第二个同名父键。

```yaml
execution:                # 设置计算实现、资源上限和数据不全时的处理方式
  process_count: 4        # 保留本次分析的文件工作进程上限
  partial_policy: strict  # 设置默认的数据不全处理；report保留已知部分，strict不给不完整数值
```

如果已把execution.partial_policy设为strict，也可以让某一项仍返回已知部分：

应用位置：以[analysis.yaml](examples/analysis.yaml)为基础，在文件根级加入或替换`calculations`，代码已包含父键。保留未展示的其他根字段，不再添加第二个同名父键。

```yaml
calculations:               # 本例的统计结果
  - name: session_energy    # 结果表中的计算名称
    expr: power             # 使用已定义的信号或公式
    partial_policy: report  # 决定数据不全时是否保留可核实数值；report保留并标记，strict返回空值
    operation: integral     # 按有效持续时间积分
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
diagnostics:   # 选择是否额外记录定位信息、校验摘要以及保留临时数据
  trace: true  # 控制是否记录详细定位信息；true增加追溯记录，false使用默认简要信息
```

逐消息贡献另由`outputs.contributions: full`开启。运行环境备注放在根级`metadata`映射中；metadata默认{}，不会替代execution或diagnostics。分析和导出使用相同的[可选设备标签](exports.md)。

## 计算项的覆盖门槛

`minimum_coverage`属于计算项或支持它的预设参数，不属于execution；字段与例子见[统计与积分](calculations.md)。

## 一份可直接运行的对照

[readability_examples.py](examples/readability_examples.py)使用同一份5行输入，比较两个backend、不同batch_rows及report/strict，并断言事件数和能量。该脚本还运行表达式说明中的每项例子，失败时直接报错。

在离线手册解压根目录运行（该目录直接包含`examples`）：

```powershell
python -B examples/readability_examples.py
```

如使用源码仓库，则在含`pyproject.toml`的仓库根目录运行：

```powershell
python -B Docs/Current/examples/readability_examples.py
```

脚本默认把输出放在系统临时目录中新建的独立目录；可用--output-root指定既有父目录，合成数据的阈值不代表真实设备应采用这些阈值。

## 根级metadata与运行来源标签

metadata保存运行附加信息，缺省为空对象。其中metadata.device_label被程序读取，用于运行清单的设备来源标签；其他备注不会改变计算。

|入口|填写位置、默认及限制|
|---|---|
|普通分析|根级metadata.device_label；非空文本，如lab_pc；省略为pending，空白文本无效。CLI普通run不以CHRONAXIS_DEVICE_LABEL自动覆盖它。|
|含信号或CAN文件导出的分析|同一字段可省略，默认pending；填写时接受任意非空文本，如lab-pc或试验台一号。|
|批量总报告|CLI从CHRONAXIS_DEVICE_LABEL取得；Python使用run_batch的device_label参数，缺省pending。不会覆盖每个子分析的metadata.device_label。|

普通分析可在根级填写：

```yaml
metadata:               # 保存说明性信息；字段不会自动校准数据或更改计算公式
  device_label: lab_pc  # 可选设备标签；任意非空文本，省略为pending，不影响计算或导出
```
