# 统计与积分

根级`calculations`声明要取得的数值。`operation`选择计算方式，`scope`默认使用全部分析范围，逐事件或窗口计算时再填写，`expr`选择参与的信号或表达式。数值与单位、完整性状态一起返回，读取方法见[结果](results.md)。

## 完整最小例与计算方法对照

[calculation-minimal.yaml](examples/calculation-minimal.yaml)只计算一次积分。它引用随附的合成CAN功率记录：0秒0W、1秒10W、4秒0W、5秒0W，分析[0,5)，有效期4秒。结果为0×1+10×3+0×1=30J。

[calculation-operations.yaml](examples/calculation-operations.yaml)使用同一数据，分别增加所有计算方法、显式结果单位及覆盖策略。执行`chronaxis run 文件名.yaml --output 新目录`。范围右端5秒只限定观测终点，不作为被选中的样本。

| 计算项 | 输出 | 根据 |
|---|---|---|
| integral | 30J | 10W持续3秒 |
| sample_minimum / sample_maximum / sample_mean | 0W / 10W / 10÷3W | [0,5)内三次真实更新，分别为0、10、0 |
| min_time / max_time | 0W / 10W | 取有正持续时间的有效区间中的最小/最大值；返回数值，不是值发生的时刻 |
| time_weighted_mean | 6W | 30J÷5秒 |
| duration，condition为power > 0 | 3s | 条件在[1,4)为真 |
| select | 三行，时刻0、1、4秒 | 保留原值和质量，读取selections而非标量calculations |
| energy_Wh | 30÷3600Wh | 积分后将J换成Wh；覆盖率完整，0.9门槛达标 |

## 配置片段

在已声明功率信号power（W）的完整计划根级加入下段。每项产生独立结果，name用于从结果表中找到它。

应用位置：以[analysis.yaml](examples/analysis.yaml)为基础，在文件根级加入或替换`calculations`，代码已包含父键。存在同名列表时按本例替换该列表，不把父键再嵌入列表项。

先运行最小配置；下方扩展配置增加可选控制。两段是替换关系，不同时重复写入同一个父键。

```yaml
calculations:              # 列出希望获得的统计或积分结果，每项独立选择范围和算法
  - name: energy           # 为这项计算结果取唯一名称；结果表用它区分计算项
    operation: integral    # 选择计算方法；本例将有效数值乘持续时间后累计，例如功率乘秒得到能量
    expr: power            # 指定参与计算的数值或信号表达式；引用前面已定义的信号
```

### 扩展设置

下面只增加90%的覆盖要求；积分单位J、前值保持法zoh和部分结果策略report均使用默认值。若需要Wh等其他结果单位或strict策略，再单独填写。

```yaml
calculations:                # 列出希望获得的统计或积分结果，每项独立选择范围和算法
  - name: energy             # 为这项计算结果取唯一名称；结果表用它区分计算项
    operation: integral      # 选择计算方法；本例将有效数值乘持续时间后累计，例如功率乘秒得到能量
    expr: power              # 指定参与计算的数值或信号表达式；引用前面已定义的信号
    minimum_coverage: 0.9    # 设置要求的最低有效数据比例；0到1，按可信性要求选择
```

## 字段参考

字段路径均为`calculations[].<字段>`。

| 字段 | 类型、必填与默认 | 用途与组合条件 |
|---|---|---|
|name| 字符串，必填 | 命名计算项，供结果表定位；由配置作者自行取名。唯一计算项标识，不能与规则、窗口或其他节点重名。 |
| operation | 字符串，必填 | 选择返回哪一种统计量或积分量；按下表的权重和输出类型选择。从下表选择计算方法；不同方法对输入类型、单位和时间有不同要求。 |
| scope | 字符串或对象，可省略，默认session | 选择每项结果统计的范围：session计算整个会话；`{rule: hot}`逐个计算hot事件的选择范围；`{window: context}`逐个计算context窗口。引用名称必须已定义。 |
| expr | 表达式字符串，通常必填 | 指定要统计或筛选的值。可填信号名、派生信号名或白名单表达式，例如power或voltage * current。数值计算要求数值表达式；select也接受bool/enum；duration要求bool，且与condition二选一。 |
| condition | 表达式字符串，可省略 | 控制哪些时间或样本参与计算；用已有信号按业务筛选要求写真假表达式，如power > 0。仅在条件已知为真时选取数据；省略表示不增加筛选。duration可直接使用它，不再填写expr。未知条件不是False。 |
| unit | 字符串，可省略 | 选择输出数值采用的单位；按下方允许单位表填写。通常从输入与运算推导；duration固定s；select必须与输入单位相同；积分可指定支持的等价结果单位，例如W积分为J或Wh。不是任意标签。 |
| method | 字符串，仅integral可填，默认zoh | 控制积分怎样处理相邻更新之间的数值；目前只允许zoh。有效区间内保持左侧值积分；其他操作填写此字段会报错。 |
| partial_policy | 字符串，可省略 | 控制缺失时是否提供可计算的部分结果；按是否允许部分结果选择。继承execution.partial_policy，通常report；report返回已知部分，strict在所需数据不全时不给数值。 |
| minimum_coverage | 有限数，默认0 | 规定数据至少覆盖多大比例才算达标；按数据完整性要求填写。0～1；普通标量计算的数据覆盖门槛。0表示不额外要求最低比例，不等于将缺失当0。样本统计的值仍按真实样本计算；覆盖判定不改变其权重。select返回明细，不生成标量覆盖状态。 |

省略calculations或填写`[]`表示不配置普通计算；null不合法。已填写的expr、condition、unit不能使用空字符串代替省略。name、operation缺失、引用不存在、单位冲突或duration同时填写expr与condition时，计划检查以`PlanValidationError`指出具体字段。

可在单个计算项中用interval选择时间依据，省略时继承intervals.default。仅时间积分、持续时间和按时长统计使用它；样本统计与select不接受。详见[计算间隔](intervals.md)。

## 计算方法

|operation|具体意思|示例|
|---|---|---|
|integral，method=zoh|假定一条有效记录的值持续到下一次更新，用该值乘持续秒数，再把各段相加|1000W持续2秒=2000J|
|sample_minimum/sample_maximum/sample_mean|对选中的有效真实样本统计，每个样本计一次|0秒0、1秒10、4秒0的样本均值10/3|
|min_time/max_time/time_weighted_mean|前两者返回有正持续时间的有效值中的最小值/最大值，单位与数值相同，绝不是发生时间；mean按时长加权|上例[0,4)中0保持1秒、10保持3秒，极值0/10，均值7.5|
|duration|已知True的累计秒数|True两段各1秒，得到2s|
|select|保留选中的行及质量/来源|返回多行数据，供逐行查看时间和值，不把它们压成一个汇总数字|

样本统计是否包含最后那个时间点，由选择区间决定；上表样本均值的例子包含三条记录。积分目前采用ZOH，即每段时间使用前一次仍有效的值；method省略即可采用`"zoh"`，尚不支持线性插值积分。普通计算与逐消息累计分别配置；字段结构见本页字段参考。

## 结果单位如何选择

单位大小写和符号须原样填写。`A·s`中间是乘点，不是星号。下表列出本版单位注册表；不在表中的文本不会自动获得物理换算关系。

| 类别 | 允许的同类单位与倍率 |
|---|---|
| 无量纲 | `"1"` |
| 电压 | V；1mV=0.001V |
| 电流 | A；1mA=0.001A |
| 功率 | W；1kW=1000W |
| 能量 | J；1Wh=3600J；1kWh=3600000J |
| 时间 | s；1ms=0.001s |
| 电荷量 | A·s；1Ah=3600A·s |

积分：W/kW默认得到J，可选J/Wh/kWh；A/mA默认得到A·s，可选A·s/Ah；无量纲数值积分默认s，可选s/ms。其他输入单位积分默认追加`*s`，例如V得到`V*s`，只允许相同结果标签，不能猜成其他物理量。

样本统计和时间极值/均值默认保留输入单位，可显式选择注册表中同类单位，例如电压均值从V输出mV。`duration`只输出s，不能填ms；`select`必须保持输入单位，不在选行时换算。未知单位仅允许保持相同标签，不能随意改名。

## minimum_coverage：覆盖门槛

以下对照请求区间为[0,12)秒，但仅[0,8)秒有观测；在已观测的8秒内功率一直为4000W且条件已知。可核实能量为32000J。

minimum_coverage是0—1之间的比例，用来判断数据覆盖是否达到要求，不是修补数据的办法。

例如要求至少90%，就设置 `minimum_coverage=0.9`。这个字段填写在单个计算项中，或填写在明确支持它的预设参数中，不放在execution里。

普通信号计算integral、duration、min_time、max_time、time_weighted_mean、sample_minimum、sample_maximum和sample_mean在minimum_coverage大于0时返回coverage_status。sufficient表示所需的观测、值有效性和条件已知范围均达到门槛；indeterminate表示不足或无法确定。这个字段不是数值覆盖率，也不会把样本统计改成时间加权统计。select明细和逐消息累计不属于这组标量结果。省略或填写0不因此增加该字段。计算覆盖判定时使用下面三个概念。公开摘要不提供这三个比例字段；以下用手算解释它们各自回答的问题：

- `requested_coverage`：实际观测时长÷请求时长。上例为8÷12，约0.667。
- `value_coverage`：实际观测范围内，数值有效的时长占比。上例的0—8秒功率均有效，因此是1.0。
- `condition_coverage`：实际观测范围内，条件能确定为真或假的时长占比。没有筛选条件时，等于该实际范围的完整比例。

上例的value_coverage是1.0，只能说明已有的8秒功率都有效；requested_coverage约为0.667，说明所请求的12秒只观测到三分之二。

设置90%的要求后，这个结果会被标记为覆盖不足。若partial_policy是report，仍可查看已知8秒算出的32000J；若是strict，就不给数值。最终判断还应读取coverage_status（覆盖是否达标）、status（结果是否完整）和reason（具体原因）。


全部普通计算字段见本页表格；按消息求一次表达式的场景见[逐消息累计](message-calculations.md)。
