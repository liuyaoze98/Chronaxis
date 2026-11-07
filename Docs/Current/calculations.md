# 统计与积分

根级`calculations`声明要取得的统计值或选择记录。`operation`选择计算方式，`scope`默认使用全部分析范围，逐事件或窗口计算时再填写，`expr`选择参与的信号或表达式。数值与单位、完整性状态一起返回，读取方法见[结果](results.md)。

<a id="integrators"></a>
## 积分器的选择

**通用时间积分器**把每段仍有效的数值乘以该段按所选时间依据计算的时长，再累加。配置`calculations[].operation: integral`与`expr`；默认按实际时间差，其他依据见[计算间隔](intervals.md)。前一次值只保持到下一次更新或valid_for到期，缺值不补0，结果同时说明完整性。功率积分得到能量，电流积分得到电荷量，其他物理量也可积分。

ASC／BLF来源（可包含同次记录的多个分卷）、同一报文内可取得全部输入、每条报文贡献已经明确时，可选择[高性能积分器（同帧逐报文累计）](fast-energy.md)。其每条贡献由`expr`给出，需要时间因子时须显式写入公式；它不自动采用相邻报文实际间隔，通用integral配置不能只换运行入口。需要跨报文保持、持续条件或事件窗口时使用通用路径。


## 完整最小例与计算方法对照

[calculation-minimal.yaml](examples/calculation-minimal.yaml)只计算一次积分。它引用随附的合成CAN功率记录：0秒0W、1秒10W、4秒0W、5秒0W，分析[0,5)，有效期4秒。结果为0×1+10×3+0×1=30J。

[calculation-operations.yaml](examples/calculation-operations.yaml)使用同一数据，演示下表的基础计算、显式结果单位及覆盖策略。执行`chronaxis run 文件名.yaml --output 结果目录`。范围右端5秒只限定观测终点，不作为被选中的样本。

| 计算项 | 输出 | 根据 |
|---|---|---|
| integral | 30J | 10W持续3秒 |
| sample_minimum / sample_maximum / sample_mean | 0W / 10W / 10÷3W | [0,5)内三次真实更新，分别为0、10、0 |
| min_time / max_time | 0W / 10W | 取有正持续时间的有效区间中的最小/最大值；返回数值，不是值发生的时刻 |
| time_weighted_mean | 6W | 30J÷5秒 |
| duration，condition为power > 0 | 3s | 条件在[1,4)为真 |
| select | 三行，时刻0、1、4秒 | 保留原值和质量，读取selections而非标量calculations |
| energy_Wh | 30÷3600Wh | 积分后将J换成Wh；覆盖率完整，0.9门槛达标 |

<a id="v4-power-statistics"></a>
## 同一次功率试验，按报文、时长或加载次数统计

台架在 0、1、4、5、7 秒分别上报 **0、10、0、20、0 W**。第 9 秒有一条其他报文，确定了观测终点。分析范围是 [0,9) 秒，功率有效期是 4 秒，足以覆盖相邻更新。下载配置、ASC 和 DBC，保留配置文件中的相对目录。在下载配置所在目录运行下列命令，输出目录可重复使用，每次运行会生成带时间后缀的新文件。[完整 v4 配置](examples/power-statistics.yaml) · [原始 ASC](examples/data/can/power-statistics.asc) · [解码 DBC](examples/data/can/teaching.dbc)

```console
python -m chronaxis validate power-statistics.yaml --format json
python -m chronaxis run power-statistics.yaml --output power-results
```

| 想知道什么 | v4 的 `calculations[].operation` | 本例实测结果 |
|---|---|---|
| 收到几条有效功率读数 | `sample_count`，`expr: power` | 5，最后的其他报文只限定观测时间 |
| 功率升到正值几次，正值持续了几段 | `point_event_count` 引用点规则，`activity_count` 引用活动规则，均填写 `rule` | 上升沿 2 次，活动 2 段，分别是 [1,4) 和 [5,7) 秒 |
| 窗口合并后要检查几段试验 | `segment_count`，填写 `window` | 1，1 秒间隙短于 1.5 秒退出延迟，最终片段是 [1,8.5) 秒 |
| 每条读数等权时，波动多大 | `sample_variance`、`sample_stddev` | 方差指定 `ddof: 1` 得 80 W²；标准差沿用 `ddof: 0` 得 8 W |
| 按每个值有效保持的时间算，波动多大 | `time_variance`、`time_stddev` | 5000/81 ≈ 61.7284 W²；其平方根约为 7.85674 W |
| 功率的均方根是多少 | `sample_rms`、`time_rms` | 按读数是 10 W；按有效时长是 √(1100/9) ≈ 11.05542 W |
| 读数的 P95 和中位数是多少 | `sample_quantile`（`q: 0.95`）、`sample_median` | 18 W 和 0 W |

**选择权重。** 样本方法对选择范围内每个有效真实更新计一次，同值的再次上报也可贡献一样本。条件必须已知为真。有效值保持、报文观测终点和仅用于判断条件或到期的时刻都不会多添一个功率样本。`scope` 可取会话、规则事件或窗口。三个对象计数使用会话范围，单位是 `1`，直接引用产生对象的规则或窗口。观测完整且没有符合条件的对象时返回 0。对象发现有缺口时，`report` 可保留已知计数并标记 `partial`，`strict` 隐去部分值。没有观测证据时查看 `status`、`reason`，数值为空。

**方差、标准差与均方根示例。** 五个读数的均值为 6 W，离均差平方和为 320 W²。样本方差除以 `N-ddof`，标准差取方差平方根。`ddof` 默认 0，样本方差与标准差也接受 1。只有一个有效样本且 `ddof: 1` 时数值为空，原因为 `insufficient_samples`。本例按实际时长计算时，0、10、20 W 共保持了 4、3、2 秒，时间均值为 70/9 W，均方为 1100/9 W²。时间统计按所选计时间隔内有效、满足条件的正时长计权，时间方差和标准差仅支持 `ddof: 0`；两种 RMS 均省略 `ddof`。统计使用原物理尺度，允许指定兼容的输出 `unit`。本例方差默认表头 `V^2*A^2` 等价于 W²。绝对温度的标准差为温差，方差为温差平方，摄氏绝对温度求 RMS 要先显式转成 K。

**分位数示例。** 将有效读数升序排列为 [0,0,0,10,20]。从 0 起算位置 `(N-1)×q`，P95 落在位置 3.8，从 10 W 向 20 W 插值 80%，得到 18 W。分位数须提供 0 到 1 的有限数值 `q`，中位数固定取 0.5 并省略 `q`。端点 0 和 1 只保留极值，内部概率要保留所选样本，并为排序另留空间。它们共用 `execution.memory_budget_bytes`，额度不足会报告资源错误。减小读取批次不会缩小同一统计范围，只有业务总体允许时才缩小范围。

打开带运行时间后缀的“会话结果”CSV 核对以上数值。“事件结果”里每段加载另有一行时间均值，分别为 10 和 20 W。对这两行求 P95 得 **19.5 W**。聚合结果列出候选 2、参与 2；此时每次加载各贡献一个值。[聚合总体和排除原因](aggregations.md)

## 配置片段

在已声明功率信号power（W）的完整计划根级加入下段。每项产生独立结果，name用于从结果表中找到它。

应用位置：以[analysis.yaml](examples/analysis.yaml)为基础，在文件根级加入或替换`calculations`，代码已包含父键。存在同名列表时按本例替换该列表，不把父键再嵌入列表项。

先运行最小配置；下方扩展配置增加可选控制。两段是替换关系，不同时重复写入同一个父键。

```yaml
calculations:            # 本例的统计结果
  - name: energy         # 结果表中的计算名称
    operation: integral  # 按有效持续时间积分
    expr: power          # 使用已定义的信号或公式
```

### 扩展设置

下面只增加90%的覆盖要求；积分单位J、前值保持法zoh和部分结果策略report均使用默认值。若需要Wh等其他结果单位或strict策略，再单独填写。

```yaml
calculations:              # 本例的统计结果
  - name: energy           # 结果表中的计算名称
    operation: integral    # 按有效持续时间积分
    expr: power            # 使用已定义的信号或公式
    minimum_coverage: 0.9  # 设置要求的最低有效数据比例；0到1，按可信性要求选择
```

## 字段参考

字段路径均为`calculations[].<字段>`。

| 字段 | 类型、必填与默认 | 用途与组合条件 |
|---|---|---|
|name| 字符串，必填 | 命名计算项，供结果表定位；由配置作者自行取名。唯一计算项标识，不能与规则、窗口或其他节点重名。 |
| operation | 字符串，必填 | 选择返回哪一种统计量或积分量；按下表的权重和输出类型选择。从下表选择计算方法；不同方法对输入类型、单位和时间有不同要求。 |
| rule / window | 字符串，v4 对象计数必填其一 | 点事件和活动使用 `rule`，合并后的片段使用 `window`。这些操作只接受会话范围，无需信号表达式。 |
| ddof | 整数，仅 v4 方差与标准差适用 | 样本可用 0（默认）或 1，时间版本仅允许 0。 |
| q | 有限数，仅 v4 `sample_quantile` 必填 | 指定 0～1 分位概率，如 P95 填 0.95。中位数省略此字段。 |
| scope | 字符串或对象，可省略，默认session | 选择每项结果统计的范围：session计算整个会话；`{rule: hot}`逐个计算hot事件的选择范围；`{window: context}`逐个计算context窗口。引用名称必须已定义。 |
| expr | 表达式字符串，通常必填 | 指定要统计或筛选的值。可填信号名、派生信号名或白名单表达式，例如power或voltage * current。数值计算要求数值表达式；select也接受bool/enum；duration要求bool，且与condition二选一。 |
| condition | 表达式字符串，可省略 | 控制哪些时间或样本参与计算；用已有信号按业务筛选要求写真假表达式，如power > 0。仅在条件已知为真时选取数据；省略表示不增加筛选。duration可直接使用它，不再填写expr。未知条件不是False。 |
| unit | 字符串，可省略 | 选择输出数值采用的单位；按下方允许单位表填写。通常从输入与运算推导；duration固定s；select 可换算兼容单位；积分可指定支持的等价结果单位，例如W积分为J或Wh。不是任意标签。 |
| method | 字符串，仅integral可填，默认zoh | 控制积分怎样处理相邻更新之间的数值；目前只允许zoh。有效区间内保持左侧值积分；其他操作填写此字段会报错。 |
| partial_policy | 字符串，可省略 | 控制缺失时是否提供可计算的部分结果；按是否允许部分结果选择。继承execution.partial_policy，通常report；report返回已知部分，strict在所需数据不全时不给数值。 |
| minimum_coverage | 有限数，默认0 | 规定数据至少覆盖多大比例才算达标；按数据完整性要求填写。0～1；普通标量计算的数据覆盖门槛。0表示不额外要求最低比例，不等于将缺失当0。样本统计的值仍按真实样本计算；覆盖判定不改变其权重。select返回明细，不生成标量覆盖状态。 |

省略calculations或填写`[]`表示不配置普通计算；null不合法。已填写的expr、condition、unit不能使用空字符串代替省略。name、operation缺失、引用不存在、单位冲突或duration同时填写expr与condition时，计划检查以`PlanValidationError`指出具体字段。

可在单个计算项中用interval选择时间依据，省略时继承intervals.default。仅时间积分、持续时间和按时长统计使用它；样本统计与select不接受。详见[计算间隔](intervals.md)。

## 计算方法

| 类别 | operation | 输入与权重 | 输出及专属参数 |
|---|---|---|---|
|时间积分|integral|数值expr，按有效保持时长累计|单个积分值；method仅zoh，省略即采用；可选interval|
|持续时间|duration|布尔expr或condition二选一；累计已知True时长|秒；可选interval|
|样本统计|sample_count|选中的有效真实更新，每条一次|无量纲整数计数，不把保持刷新算新样本|
|样本统计|sample_minimum、sample_maximum、sample_mean|有效真实更新等权|最小值、最大值、均值；无有效样本时无值|
|样本统计|sample_variance、sample_stddev|有效真实更新等权，分母N-ddof|方差、标准差；ddof为0（默认）或1|
|样本统计|sample_rms|有效真实更新等权|平方均值的平方根；不填ddof|
|样本统计|sample_quantile、sample_median|有效真实更新排序，线性分位数|quantile必填q∈[0,1]；median固定0.5并禁止q|
|时间加权统计|min_time、max_time、time_weighted_mean|只计算具有正有效时长的值|保持值的最小／最大／时间均值；前两者不是发生时间；可选interval|
|时间加权统计|time_variance、time_stddev|以有效持续时间加权|方差／标准差；ddof只能0，可选interval|
|时间加权统计|time_rms|以有效持续时间加权平方值|均方根；不填ddof，可选interval|
|对象计数|point_event_count|会话范围，rule引用点事件规则|点事件个数；不填expr、condition、interval|
|对象计数|activity_count|会话范围，rule引用活动规则|活动个数；不填expr、condition、interval|
|对象计数|segment_count|会话范围，window引用窗口|最终片段个数；不填expr、condition、interval|
|样本选择|select|选择范围内的更新和值；可含bool/enum|多条选择记录，含时刻、值、质量；不是一个标量统计；不填interval|

样本统计与select不使用持续时长权重，也不接受interval。非上述适用操作不能填写q或ddof；object计数只允许会话范围。其他标量计算可按会话、事件或窗口各产生一行。对这些结果行再统计请使用[结果聚合](aggregations.md)。

### 方差、标准差与均方根

样本方差按`Σ(x-均值)²/(N-ddof)`计算，标准差取平方根；N≤ddof时没有数值。时间方法按有效时长计权，仅用总体口径。RMS为平方均值开方，不是标准差。绝对温度的方差／标准差使用温差单位；摄氏绝对温度RMS须先换到K。上方功率试验提供手算过程。

### 分位数

q是0～1的概率，不是0～100的百分数。位置`(N-1)×q`决定两个相邻有序样本间的线性插值；median等价于q=0.5。内部概率需保存参与样本并预留排序空间，内存预算不足会报资源错误；不会自动改用近似值。


## 结果单位如何选择

当前配置使用 `config_version: 4`，会换算已登记的兼容单位。单位区分大小写。

| 类别 | 版本 4 支持的单位 |
|---|---|
| 无量纲、比例 | `"1"`、`%`，1%=0.01 |
| 电压、电流、功率 | V、mV；A、mA；W、kW |
| 能量、电荷量 | J、Wh、kWh；Ah、A*s（也可写 A·s） |
| 时间 | s、ms、us、ns；us 也可写 µs 或 μs |
| 温度、温差 | K、degC（°C、℃）；delta_K、delta_degC（ΔK、Δ°C、Δ℃） |
| 电阻 | Ohm、mOhm、kOhm、MOhm；Ohm 可写 Ω 或 Ω；带前缀的符号为 mΩ、kΩ、MΩ |
| 长度、速度、加速度 | m、m/s、m/s^2 |
| 频率、角速度、角度 | Hz、rpm、rad/s；rad、deg（°） |
| 力、力矩、压强 | N、N*m（N·m）；Pa、kPa、bar |

版本 4 也接受登记单位的乘除、整数次幂和括号，如 `V*s`、`A^2`。程序不自动猜测任意前缀或未知单位。数量含义也要匹配：N*m 不自动当成 J，Hz 不自动当成 rad/s；rpm 与 rad/s 有已登记的换算关系。

积分先按所选间隔累加，再换算到目标 `unit`：1000 W 持续 2 秒，默认得到 2000 J；填写 `unit: Wh` 得到约 0.555556 Wh。V 的积分为 V*s，不是能量。摄氏温度参与积分前须在表达式中明确换到 K，不能在积分结果上补一次温度偏移。

版本 4 的普通均值、极值、分位数和 `select` 默认使用[规范单位](expressions.md#canonical-units)；例如 1500 mV 默认返回 1.5 V，显式 `unit: mV` 保留 1500 mV。兼容的目标单位会连同数值一起转换，摄氏与开尔文也处理偏移。方差、标准差和 RMS 的单位按上面的统计规则推导。`duration` 仍只输出 s；样本计数和三个对象计数只输出 `1`。

未知单位不会因为填写了输出标签就获得已验证的物理关系。

## minimum_coverage：覆盖门槛

以下对照请求区间为[0,12)秒，但仅[0,8)秒有观测；在已观测的8秒内功率一直为4000W且条件已知。可核实能量为32000J。

minimum_coverage是0—1之间的比例，用来判断数据覆盖是否达到要求，不是修补数据的办法。

例如要求至少90%，就设置 `minimum_coverage=0.9`。这个字段填写在单个计算项中，或填写在明确支持它的预设参数中，不放在execution里。

普通信号标量计算在 `minimum_coverage` 大于 0 时返回 `coverage_status`，包括基础积分、时长、极值、均值，以及 v4 的样本计数、方差、标准差、RMS 和样本分位数。`sufficient` 表示观测、值有效性和条件已知范围均达到门槛，`indeterminate` 表示不足或无法确定。覆盖判断保留样本方法原有的等权统计。三个 v4 对象计数依据规则发现情况判断完整性，不接受此门槛。`select` 明细和逐消息累计也不返回这项状态。省略门槛或设置为 0 不增加这个字段。下面用手算解释三个参与判断的比例，公开摘要只给出判定结果。

- `requested_coverage`：实际观测时长÷请求时长。上例为8÷12，约0.667。
- `value_coverage`：实际观测范围内，数值有效的时长占比。上例的0—8秒功率均有效，因此是1.0。
- `condition_coverage`：实际观测范围内，条件能确定为真或假的时长占比。没有筛选条件时，等于该实际范围的完整比例。

上例的value_coverage是1.0，只能说明已有的8秒功率都有效；requested_coverage约为0.667，说明所请求的12秒只观测到三分之二。

设置90%的要求后，这个结果会被标记为覆盖不足。若partial_policy是report，仍可查看已知8秒算出的32000J；若是strict，就不给数值。最终判断还应读取coverage_status（覆盖是否达标）、status（结果是否完整）和reason（具体原因）。


全部普通计算字段见本页表格；按消息求一次表达式的场景见[逐消息累计](message-calculations.md)。
