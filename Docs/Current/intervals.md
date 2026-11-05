# 计算间隔


默认按实际时间差计算，不需要填写intervals。需要改用固定周期或DBC声明周期时，再设置根级`intervals`或单个节点的`interval`。它选择累计和等待使用的时长依据；原记录时间及有效期仍按实际时间判断，但确认、超时、窗口触发和配对delay_ns可能变化；配置路径和逐节点覆盖见下表。

三条功率记录出现在0、0.12、0.30秒，都是4000W。按实际间隔累计，能量为4000×(0.12+0.18)=1200J；按固定100ms累计，能量为4000×(0.1+0.1)=800J。若对应报文的DBC周期为100ms，结果也是800J。三条记录形成两个间隔，第一条只建立起点。

配置时长可以写`"0.1s"`或`"100ms"`。内部及API／交换格式中以`_ns`结尾的时间字段使用整数纳秒，例如100ms等于100000000ns；默认可读结果表使用秒。输入日志是秒，不需要先手工转换成纳秒。

## 完整最小例与单项覆盖扩展

[interval-actual.yaml](examples/interval-actual.yaml)省略intervals，得到1200J。[interval-fixed.yaml](examples/interval-fixed.yaml)省略全局intervals，仅对energy计算增加fixed=100ms，得到800J；power在同一文件中先定义。两者使用相同0、0.12、0.30秒三条记录，可直接运行`chronaxis run 文件名.yaml --output 结果目录`。

## 一个完整的最小例子

以下是合成数据，功率和预期能量均可手算。把它保存为`energy.yaml`：

完整文件：保存为本节指定的文件名，包含根级字段，不需要再套父键；结果目录可以重复使用，每次生成带时间后缀的结果文件。

```yaml
config_version: 4          # 当前分析配置版本
dataset:                   # 设置本次分析名称及可选的对象、会话和时间范围
  name: demo               # 命名本次分析数据集；名称写入结果身份字段
sources:                   # 列出输入来源；每项规定数据位置、格式和时间解释方式
  - source_type: memory    # 选择数据格式；memory内存记录、signal_csv物理量表、can_blf/can_asc/raw_can_csv原始CAN
    rows:                  # 提供内存来源的记录列表；每条记录含时间及该时刻的字段值
      - time: 0s           # 填写本条合成记录的发生时间，按本来源的time声明解释
        values:            # 列出本条记录实际更新的原字段及值；字段名供signals.field选择
          p: 4000          # 本时刻原字段p的合成输入值；其类型和单位由下方信号定义说明
      - time: 0.12s        # 填写本条合成记录的发生时间，按本来源的time声明解释
        values:            # 列出本条记录实际更新的原字段及值；字段名供signals.field选择
          p: 4000          # 本时刻原字段p的合成输入值；其类型和单位由下方信号定义说明
      - time: 0.3s         # 填写本条合成记录的发生时间，按本来源的time声明解释
        values:            # 列出本条记录实际更新的原字段及值；字段名供signals.field选择
          p: 4000          # 本时刻原字段p的合成输入值；其类型和单位由下方信号定义说明
signals:                   # 把输入字段定义为有名称、类型、单位和有效期的分析信号
  - name: power            # 给分析信号取名称；后续表达式和计算通过此名称引用它
    field: p               # 指定来源中的原始字段；CSV填表头，CAN填写通道/报文ID/DBC信号名
    dtype: float64         # 选择分析值类型；float64小数、int64有符号整数、uint64非负整数、bool真假、enum状态名称
    unit: W                # 声明分析值的单位；按物理含义填写，无量纲用字符串"1"；未填scale/offset时按已登记的兼容单位换算
    valid_for: 1s          # 设置一次有效更新最多沿用多久；依据采样周期和允许数据陈旧程度填写
calculations:              # 列出希望获得的统计或积分结果，每项独立选择范围和算法
  - name: energy           # 为这项计算结果取唯一名称；结果表用它区分计算项
    operation: integral    # 选择计算方法；本例将有效数值乘持续时间后累计，例如功率乘秒得到能量
    expr: power            # 指定参与计算的数值或信号表达式；引用前面已定义的信号
intervals:                 # 选择时间计算使用实际间隔还是指定周期；不修改原记录时间
  default:                 # 设置未单独覆盖的计算节点采用的时间间隔依据
    mode: fixed            # 选择actual实际时间差、fixed固定周期或dbc报文周期
    value: 100ms           # 给fixed模式提供固定周期；从采集设置或业务规则取得
```

运行`python -m chronaxis run energy.yaml --output work/energy-v2-result`，结果目录可以重复使用。`会话结果_<运行时间>.csv`中的energy（J）应为800。删除整个intervals即可改用实际间隔，应为1200J。原始CAN来源才能将mode设为dbc并删除value；上述memory来源不支持DBC周期，选择dbc会在配置校验时报错。

## intervals的全部字段

intervals是可选对象，只包含default，省略时采用actual。单独设置写在规则、配对、窗口、计算项或时序变换自己的interval对象中，不再使用按名称索引的overrides。它选择计算依据，不控制读取批次，也不自动开启导出重采样。

|字段|类型|必填|省略行为|含义|
|---|---|---|---|---|
|default|对象|否|mode为actual|设置全任务的默认时间依据，供下文列出的规则、窗口、配对、积分和时序变换使用。按希望使用真实时间还是记录周期选择。|

表中的mode、value和driver属于一个间隔对象：全局完整路径为`intervals.default.mode/value/driver`；节点则为`rules[].interval`、`windows[].interval`、`sequences[].interval`、`calculations[].interval`或`transforms[].interval`中的同名字段，不能直接写成intervals.mode。

|字段（相对于上述间隔对象）|类型|必填|省略行为|含义|
|---|---|---|---|---|
|mode|字符串|选择对象中必填|无|控制累计和等待的时间来源。actual：取真实时间差；fixed：每个驱动间隔按value计时；dbc：从驱动报文的DBC中读取GenMsgCycleTime。按分析采用的时间标准选择，非格式选择。|
|value|带单位的正时长字符串|fixed必填|无|规定每个驱动间隔计入多少时间；从协议周期或分析规定取得，如100ms。换算后须为int64范围内正纳秒数；0/null不合法。actual/dbc不能填本项。|
|driver|原信号别名字符串|fixed/dbc有零个或多个候选时必填|恰有一个物理更新来源时自动确定|指定由哪条原信号的更新推进周期。填已定义signals[].name；例如电流10ms、电压100ms，选择current便按电流更新推进。常量表达式无候选，须显式选择时钟信号；不接受derived名称、表达式或null。actual不能填本项。|

沿用上方energy.yaml，已有power信号；仅让energy按power更新、每次100ms推进：

以本页energy.yaml为基础，删除原来的根级intervals，再替换calculations。其他节点默认使用实际间隔；energy自己的interval只影响这一项计算。

```yaml
calculations:              # 列出希望获得的统计或积分结果，每项独立选择范围和算法
  - name: energy           # 为这项计算结果取唯一名称；结果表用它区分计算项
    operation: integral    # 选择计算方法；本例将有效数值乘持续时间后累计，例如功率乘秒得到能量
    expr: power            # 指定参与计算的数值或信号表达式；引用前面已定义的信号
    interval:              # 为本节点单独选择计算间隔；覆盖全局默认，不修改原记录时间
      mode: fixed          # 选择actual实际时间差、fixed固定周期或dbc报文周期
      value: 100ms         # 给fixed模式提供固定周期；从采集设置或业务规则取得
```

这里只有power一个候选，所以省略driver；有多个候选时才填写driver明确选用哪一个。这里power就是上方signals中定义的功率信号。它也可以是专门用于推进的独立时钟信号，但与表达式依赖必须有可比较的时间基准。两个别名来自同一条物理报文时只算一个候选。其他被公式使用的信号仍需更新和检查是否有效，不会因为没有选作driver而被丢弃。样本最小值、样本最大值、样本均值、select、纯上升/下降沿不使用间隔；给它们单独设置覆盖会报错。

逐消息累计（`legacy_sum`）直接相加每条目标消息的 `expr` 结果，不使用 `intervals` 指定的时长。若用功率计算每条消息的能量，应在 `expr` 中乘以时间参数，例如 `power * period`，并在 `parameters` 中定义该参数。`period` 是此例采用的参数名，可以另行命名；若输入已经是每条消息的能量贡献，则直接累计，不再乘时间。见[逐消息累计完整字段参考](message-calculations.md#message-fields)。

## 实际起止时刻不改，累计采用选定的周期

报警在日志10.00秒开始、10.30秒解除，中间有10.12秒一条。固定100ms累计两个间隔，持续时间为0.2秒；事件的实际开始与解除时刻仍为10.00和10.30秒。程序不会额外保存一列改写后的时间来解释差异。

如果要求持续满0.2秒才确认，固定/DBC模式要等第三条所选报文实际到达，确认时刻为10.30秒。没有新报文时不凭空增加周期；actual模式可以按实际时间到期确认。请求响应、超时、进入/退出等待和窗口变化量也采用各自已选定的依据。跨连续文件保留状态，文件边界本身不会结束报警。

事件在10.12秒发生，前后各取0.1秒，固定100ms模式会取到前一条10.00秒和后一条10.30秒，得到实际范围10.00—10.30秒；actual则按日志时刻向前后各取0.1秒。最终报文导出仍按实际选定范围处理，不能把固定周期当作改写原报文时间的要求。

当统计范围截到两条记录中间，按实际重叠比例分配所选周期。两帧在10.00和10.12秒、功率4000W、周期100ms；仅统计10.06—10.12秒时，占实际间隔一半，能量为4000×0.1×0.5=200J。

## 信号是否过期，仍看真实时间

电压只在0秒更新，允许有效150ms；电流在0和180ms到达。即使按每条电流100ms累计，180ms时的旧电压仍已过期，这次不能把它当作有效电压。受影响的计算按partial_policy返回已知部分或空值，并标明缺数据；不会把缺失电压补成0，也不会在后来恢复时回填那段缺口。

输入中的结构损坏仍报错。所需报文结构正确，但DBC解码失败或所需值缺失时，默认把该次信号记为无效并继续，替换上一个有效值。无关报文仅执行当前计算确实需要的读取/检查；只有需要全来源观测的条件才处理全部时间。

## DBC周期的适用来源

BLF、ASC、原始报文CSV可从DBC取得周期；已解码CSV和memory支持actual/fixed，不能选择dbc。周期在初始化时取得，不逐帧重读；缺失、非法或无法唯一定位时明确报错，不自动退回actual。

解码选项见[CAN输入策略](inputs.md#decode-policy)；输入追溯和现场保留见[诊断设置](execution.md#diagnostics)；格式转换、展开和来源定位见[配置工具](configuration-tools.md)。这些功能不由intervals控制。

<a id="timing-basis"></a>
## 同一输入采用三种时间依据

默认actual使用真实时间差；fixed按所选驱动记录每次推进指定周期；dbc按同一驱动报文在DBC中的周期推进。这三种模式的事件时间字段仍使用实际日志坐标，但决定“等够多久”的依据不同，所以不能把“不改时间坐标”理解为“确认时刻和结果永远不变”。

完整输入为[timing.asc](examples/data/timing.asc)和[timing.dbc](examples/data/timing.dbc)，DBC周期1000ms。配置分别是[actual](examples/timing-actual.yaml)、[fixed](examples/timing-fixed.yaml)、[dbc](examples/timing-dbc.yaml)。从examples目录运行：

```powershell
chronaxis run timing-actual.yaml --output timing-actual-result
chronaxis run timing-fixed.yaml --output timing-fixed-result
chronaxis run timing-dbc.yaml --output timing-dbc-result
```

| 原始时刻（秒） | 请求 | 响应 | 温度degC | 电压V |
|---|---|---|---|---|
| 0 | 0 | 0 | 70 | 0 |
| 1 | 1 | 0 | 80 | 1 |
| 3 | 0 | 1 | 80 | 5 |
| 6 | 0 | 0 | 70 | 10 |
| 7 | 0 | 0 | 70 | 10 |

| 核对项 | actual | fixed=1s / dbc=1000ms |
|---|---|---|
| 请求/响应点 | 1秒/3秒 | 同为1秒/3秒 |
| 配对decided_ns | 3000000000 | 3000000000 |
| 配对delay_ns | 2000000000，真实差2秒 | 1000000000，请求到响应仅推进一个驱动周期 |
| 温度>=80累计duration | 5秒 | 两个驱动间隔，2秒 |
| hot要求连续1.5秒，confirmed_ns | 2500000000 | 6000000000：3秒只累计1周期，6秒才累计到2周期 |
| hot活动start/end | 1秒/6秒 | 同为1秒/6秒；确认可以恰好在结束时刻 |
| window_delta最近4秒上升>=5V，emit_initial=true | 4秒初次满足、6秒再次触发 | 7秒才积累4个驱动周期并初次满足 |

actual在4秒完成第一个变化窗口：4秒值沿用3秒的5V，对照0秒0V；5秒左端移到1秒后差值降为4V，6秒再次越过门槛。固定/DBC的窗口长度按驱动周期计数，不是直接从日志时间减4秒。普通windows的pre/post时间扩展与该变化量历史窗口也不是同一配置。

[自动对照脚本](examples/timing_comparison.py)检查同一输入的实际返回。配对结果delay_ns表示该配对所选择的时间依据；只有actual才等于响应事件时间减请求事件时间。导出重采样另由outputs配置，不负责决定上述等待或积分。
