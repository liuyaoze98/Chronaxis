# 信号绑定与有效期

根级列表`signals`把来源中的一列或一个DBC字段定义为分析信号。多个候选来源时才用`source`引用`sources[].name`，`field`定位原字段，`name`提供表达式使用的名称。信号定义负责输入值转换、有效性检查和最近值的保持时间；后续规则与计算只引用定义好的名字。

本页“输入值”指CSV文本解析成的值，或CAN报文经过DBC解码得到的值。执行这些步骤的程序组件称为读取器。ASC/BLF按扩展名自动识别；CSV或内存才需要用`sources[].source_type`明确选择。DBC里的比例和偏移在解码时已经执行；`signals`中的换算是其后的额外步骤。“枚举标签”指给离散状态取的文本名称，例如`"idle"`，它是编码转换后的分析值，不是另一个文件中的字段名。

## 数值信号：先运行ASC／BLF最小配置

使用随附[signal-types.asc](examples/data/can/signal-types.asc)和[teaching.dbc](examples/data/can/teaching.dbc)。DBC中Current_mA单位为mA，Enabled编码0/1表示关闭/开启，ModeCode的枚举表将0/7对应为idle/running。解码后的教学数据是：

|时间|Current_mA|Enabled|ModeCode|
|---|---|---|---|
|0ms|5000|0|0|
|100ms|7000|1|7|
|200ms|5000|1|7|
|300ms|5000|0|0|

完整文件[signal-number-minimal.yaml](examples/signal-number-minimal.yaml)只读取电流并求最大值；类型与单位由DBC推导。有效期200ms是此教学例的明确选择，未填写的额外设置不需要照抄：

```yaml
config_version: 3                       # 声明分析文件采用的字段结构版本；当前填写整数3
dataset:                                # 设置本次分析名称及可选的对象、会话和时间范围
  name: signal_example                  # 命名本次分析数据集；名称写入结果身份字段
sources:                                # 列出输入来源；每项规定数据位置、格式和时间解释方式
  - paths: data/can/signal-types.asc    # 选择输入文件、连续分卷列表或目录；相对路径基于本配置，目录按自然序读取
    dbc_by_channel:                     # 为每个CAN通道指定解码用DBC文件；键是通道编号的字符串
      '1': data/can/teaching.dbc        # 为这个通道指定DBC文件；路径相对当前配置文件，通道键须为字符串
signals:                                # 把输入字段定义为有名称、类型、单位和有效期的分析信号
  - field:                              # 指定来源中的原始字段；CSV填表头，CAN填写通道/报文ID/DBC信号名
      frame_id: '0x101'                 # 选择包含信号的报文ID；从对应DBC取得，可写整数或支持的进制文本
      signal: Current_mA                # 填写DBC中的信号名称，大小写须一致
    name: current                       # 给分析信号取名称；后续表达式和计算通过此名称引用它
    valid_for: 200ms                    # 设置一次有效更新最多沿用多久；依据采样周期和允许数据陈旧程度填写
calculations:                           # 列出希望获得的统计或积分结果，每项独立选择范围和算法
  - name: maximum_current               # 为这项计算结果取唯一名称；结果表用它区分计算项
    operation: sample_maximum           # 选择计算方法；本例取范围内有效真实样本的最大值
    expr: current                       # 指定参与计算的数值或信号表达式；引用前面已定义的信号
```

在examples目录执行`chronaxis run signal-number-minimal.yaml --output out-number`，maximum_current应为7000mA。换为BLF只需替换日志路径，不改信号结构。普通最大值计算不需要配置conversion、scope或session。

### 扩展：换算成安培并识别无效值

[signal-number-conversion.yaml](examples/signal-number-conversion.yaml)使用同一日志，仅修改信号换算和质量要求。以下片段替换上一例的signals：

```yaml
signals:                         # 把输入字段定义为有名称、类型、单位和有效期的分析信号
  - field:                       # 指定来源中的原始字段；CSV填表头，CAN填写通道/报文ID/DBC信号名
      frame_id: '0x101'          # 选择包含信号的报文ID；从对应DBC取得，可写整数或支持的进制文本
      signal: Current_mA         # 填写DBC中的信号名称，大小写须一致
    invalid_values: [65535.0]    # 列出解析/解码后、额外换算前表示无效的值；按数据规范匹配实际类型和值
    name: current                # 给分析信号取名称；后续表达式和计算通过此名称引用它
    valid_for: 200ms             # 设置一次有效更新最多沿用多久；依据采样周期和允许数据陈旧程度填写
    valid_range: [-100, 100]     # 检查换算后的值是否在含两端的上下限内；按传感器或业务允许范围填写
    conversion:                  # 设置读取后额外的单位换算；不重复DBC已执行的缩放和偏移
      input_unit: mA             # 声明CSV解析或DBC解码后、额外换算前的单位；查列说明或DBC物理单位
      scale: 0.001               # 设置额外数值乘数；按输入与目标单位的合法换算倍率填写，避免重复DBC换算
    unit: A                      # 声明分析值的单位；按物理含义填写，无量纲用字符串"1"；仅标签不执行换算
```

5000mA换成5A，最大值变成7A。这个例子专门演示额外换算与异常码，因此保留conversion、invalid_values和valid_range；普通计算不需要这些字段。DBC对Current_mA按0.5缩放后输出浮点值，失效码填写解码后的65535.0。valid_range用换算后的安培检查：101A无效、100A有效。样例没有异常值，所以最大值仍为7A。

## 完整字段参考

本表仅适用于单个信号声明；报文组及组内子项另见下方结构表。本表字段相对于`signals[]`：`conversion.scale`即`signals[].conversion.scale`，不是与name并列的scale。CAN的field对象见[报文定位](inputs.md#can-field)；CSV/memory的field则是原字段名称字符串。

下表路径均以`signals[]`开头。省略可选字段时使用表中默认；除明确允许空值的元数据外，不要用`null`代替省略。

| 字段 | 类型、必填与默认 | 控制作用、填写依据、选项与效果 |
|---|---|---|
| `name` | 字符串，必填 | 命名分析信号，供表达式和计算引用。自行取计划内唯一标识，例如`current`；用非保留的英文字母/下划线开头名称，不能含空格。 |
| `source` | 字符串，唯一来源时可省略 | 选择该信号从哪个来源读取。填本文件已定义的`sources[].name`，如`meter`；不是CSV路径。 |
| `field` | 字符串或映射，必填 | 定位来源中的原字段。CSV填表头原文`Current_mA`，内存填`rows[].values`中的键；CAN按DBC填通道、报文ID和信号名，见[定位字段](inputs.md#can-field)。大小写必须对应。 |
| `dtype` | 字符串，CAN可省略 | 选择分析值类型。`float64`：有限小数；`int64`：-2^63至2^63-1整数；`uint64`：0至2^64-1整数；`bool`：true/false；`enum`：状态名称文本。依据数据含义选；CAN省略且未提供choices时按DBC物理值范围推导数值类型；显式choices的目标全部为布尔/字符串时可推导bool/enum。仅DBC有枚举表不会自动改成enum，仍可直接写state == 1。CSV/内存需要明确类型。 |
| `unit` | 非空字符串，CAN可省略 | 声明分析值的单位，计算会检查单位兼容性。按目标物理量填`A`、`V`等，无量纲写带引号的`"1"`。CAN省略时采用DBC单位；DBC未给单位则用unknown，bool/enum用"1"。仅改单位标签不会换算数值。 |
| `valid_for` | 正时长，可省略 | 限制一次有效更新可被后续时刻沿用多久。依据采样周期和允许的陈旧时间填`200ms`等；0ms、负数、null或无限不合法。省略取period或DBC报文周期的3倍，取不到所需周期时报配置错误。详见本页时间例。 |
| `period` | 正时长，可省略 | 声明本信号正常更新周期，供省略valid_for时计算默认有效期。查采集设置或设备报文规范，如`100ms`；优先于DBC报文周期，不按相邻记录猜测。省略可用DBC周期，0/null不合法。它不会创建新样本。 |
| `conversion` | 对象，可省略 | 组织读取后的额外单位换算：input_unit声明输入单位，scale设置乘数，offset设置加数。省略或{}采用各子字段默认值；null无效。不是DBC的原始位解码设置。 |
| `conversion.input_unit` | 非空字符串或null，默认null | 声明额外换算前的单位。CSV查列说明；CAN查DBC解码后的物理单位，不填原始位编码的量纲。例：输入5000mA要分析为5A，填mA并配unit=A、scale=0.001。省略/null沿用unit；非空DBC单位须与此声明逐字一致，unit省略时可由DBC补入，但额外换算仍须明确声明。 |
| `conversion.scale` | 有限数，默认1 | 设置额外数值乘数，公式为输入值×scale+offset。按输入/目标单位倍率取值，例如mA→A为0.001。两端已知单位须为合法倍率；bool/enum只允许1。YAML的true/false是真假值，不是可用乘数。 |
| `conversion.offset` | 有限数，默认0 | 设置乘法之后加上的数值，单位为目标unit。只有单位关系未获验证且确有校准公式时才按公式填写，例如未知标签sensor_raw→sensor_value可加2；两端均为已知单位以及bool/enum必须为0。不是时间偏移，不接受true/false。 |
| `choices` | 二元列表的列表；CAN的enum可从DBC读取，其余默认[] | 把输入代码转换为分析中的真假值或状态名称。每项写`[输入代码, 分析值]`，代码查设备编码表；bool如`[[0,false],[1,true]]`，enum如`[[0,idle],[7,running]]`。代码允许整数/布尔/字符串，类型必须匹配；bool目标只能true/false，enum目标必须非空文本。CAN选择enum且未填choices时读取DBC枚举表；没有枚举表或需要自定义标签时可手填choices；若DBC解码值为float（包括0.5或1.0），不能用choices匹配，须保留数值dtype并使用数值条件。不得截断为整数或重复执行DBC缩放。CSV/内存enum需手填；bool省略时只接受原生布尔。数值信号不使用此字段。见完整编码例。 |
| `valid_range` | 两个数的列表，可省略 | 限制换算后数值的允许上下界，含两端。按传感器量程或分析要求填，例如安培范围`[-100,100]`；下限不得大于上限。101A记OUT_OF_RANGE，既不裁剪成100也不补0。省略时不额外限制该物理范围，类型、缺失等检查仍执行。[]/null非法，bool/enum不适用。 |
| `invalid_values` | 标量列表，默认[] | 列出表示无效的输入值，在额外换算前按类型和值排除。查设备无效码，并确认CSV解析或DBC解码得到的值；例如输入整数65535填`[65535]`，不能填换算后65.535。省略或[]不增加这项排除；null不能代替列表。详见原值类型表。 |
| `sample_policy` | 字符串，默认backward_hold | 选择两次更新之间如何取得信号值。目前仅支持`backward_hold`：在有效期内沿用最近一次更新；不做线性插值。通常省略。 |
| `same_time_policy` | 字符串，默认error | 控制同一信号同一时刻的多条更新如何处理。`error`：值、值类型、有效性或质量有冲突时报错，相同更新可合并；`last_by_sequence`：选来源稳定序号最大的更新。依据重复记录处理要求选，不按数值大小或文件名挑选。 |
| `semantic_id` | 非空字符串或null，默认null | 声明业务含义，供预设自动寻找角色或结果追溯。普通计算可省略；自动查找时按[角色表](presets.md#preset-role-requirements)填如`battery.current`，不能自行猜名称。表达式仍用name，不用此点分名称。 |
| `semantic_contract_version` | 非空字符串或null，默认null | 标明semantic_id采用哪一版含义约定。普通计算可省略；预设自动查找须填写字符串`"1"`并提供semantic_id，含义和单位按预设角色表核对。普通信号可记录其他非空版本文本，但不会因此满足自动查找条件。此值来自业务角色规范，不随config_version=3填写为3。 |
| `mapping_version` | 非空字符串或null，默认null | 记录原字段到此分析信号的绑定版本，供结果追溯。由项目维护者自行编号，如`"meter-map-2026-01"`；改变列/DBC对应关系时按项目规则更新。省略不影响普通计算，也不会自动生成版本。 |
| `sign_convention` | 非空字符串或null，默认null | 声明正负值对应的物理方向。按设备规范及实际数据核对后填写；充电预设电流要求`positive_is_charge`，即正值表示充电。普通信号可省略或用项目约定非空文本。此声明不取反、不校准；数据方向不符须先处理输入。 |
| `measurement_location` | 非空字符串或null，默认null | 记录实际测量位置。查接线/传感器说明；电池包端填`pack_terminal`。普通信号可省略或填项目约定位置文本；充电预设的电流、电压角色必须为pack_terminal，包括显式角色绑定。不会由信号名称推断或改变测点。 |
| `metadata` | 映射，默认{} | 保存本信号自定义说明，例如`{sensor_serial: S001}`；键和值由项目记录规则决定。省略/{}无附加说明，不能放入这里来启用换算或质量功能。 |

<a id="signal-field-decisions"></a>
## CAN信号的默认值与报文集中绑定

CAN的`dtype`和`unit`可以省略：程序读取所绑定信号的DBC定义，数字状态保持数字类型，因此`state == 1`或`state == 0x1`都可用于条件。需要状态文字时显式填`dtype: enum`，省略`choices`即可读取DBC的枚举表；手填`choices`时采用手工表，不再另外合并DBC表。

如果DBC解码结果是浮点数（包括`1.0`这种没有小数部分的浮点值），当前不能将它作为`enum`编码，手填`choices`也不能解除此限制。此时应使用数值类型，例如`dtype: float64`，再通过`state == 1`等数值条件判断状态，不要截断或取整编码来规避限制。

仅当缺少这些默认信息时，加载配置才读取DBC，并在同次加载中复用同一数据库。DBC没有单位时标为unknown，不声称已经确认物理单位；CSV和内存没有DBC，仍须明确dtype和unit。DBC修改后要重新加载计划。

同一条报文的多个信号可以共用定位和周期。本节改用专门的配套输入：[pack.asc](examples/grouped/pack.asc)、[pack.dbc](examples/grouped/pack.dbc)，以及[完整配置](examples/grouped/analysis.yaml)，三者保存在同一目录。此DBC的0x120报文同时定义PackVoltage和ChargeState；不能将下面片段放进前面的teaching.dbc例子。

以下是完整配置中的signals摘录，已包含在下载文件中。DBC周期100ms使voltage默认有效300ms；state显式覆盖为200ms。

```yaml
signals:                       # 把输入字段定义为有名称、类型、单位和有效期的分析信号
  - frame_id: 0x120            # 选择本组所属报文；从DBC取得ID，所有子信号须属于该报文
    signals:                   # 列出本报文需要的子信号；继承组级定位，可覆盖周期、有效期和同刻策略
      - name: voltage          # 给分析信号取名称；后续表达式和计算通过此名称引用它
        signal: PackVoltage    # 填写本组报文内的DBC信号名称；大小写须一致
      - name: state            # 给分析信号取名称；后续表达式和计算通过此名称引用它
        signal: ChargeState    # 填写本组报文内的DBC信号名称；大小写须一致
        dtype: enum            # 选择分析值类型；float64小数、int64有符号整数、uint64非负整数、bool真假、enum状态名称
        valid_for: 200ms       # 设置一次有效更新最多沿用多久；依据采样周期和允许数据陈旧程度填写
```

实际输出：[计算表](examples/grouped/results/会话结果.csv)、[事件表](examples/grouped/results/事件结果.csv)。

在这三个文件所在目录运行`chronaxis run analysis.yaml --output pack-result`。0、0.1、0.2秒电压分别为40、42、41V，peak_voltage为42V；状态依次为idle、charging、idle，在0.1秒产生一次charging上升沿。0.4秒无关报文只确定来源终点。

分组还可共用channel、is_extended、is_fd、valid_for、same_time_policy。子信号不重复source或报文定位；它自己的dtype、unit、choices、conversion和质量条件仍独立。分组只减少重复声明，不合并不同信号的数值或更新时刻。

### 报文组与组内信号的字段位置

报文组是signals列表中的另一种结构，不能按单信号表给组本身填写name/field。

|位置|用途与填写规则|
|---|---|
|signals[].frame_id|选择组内所有信号所属报文；必填，从DBC取得ID。|
|signals[].signals|列出该报文中要使用的子信号；必填非空列表。|
|组级source|选择本组使用的输入来源。整个计划仅声明一个来源时可省略；多个来源时填写sources[].name，即使只有一个来源是CAN。|
|组级channel、is_extended、is_fd|限定公共通道与帧类型；可省略以使用当前唯一匹配。不能放进子项。|
|组级period、valid_for、same_time_policy|设置全组的周期、有效期和同刻冲突处理；均可省略。子项填写同名字段时只覆盖自身。|
|signals[].signals[].signal|选择DBC信号；必填，名称必须属于组级指定的报文。|
|signals[].signals[].name|定义分析别名，供后续表达式引用；必填。|
|子项dtype、unit、choices、conversion及质量/语义字段|只影响本信号，允许值沿用上方单信号参考；CAN推导及省略条件相同。|
|子项禁止字段|不能填写field、source、signals、frame_id、channel、is_extended、is_fd。不同报文必须另建组。|

例如sources同时声明CAN来源bus和CSV来源meter时，应在报文组的frame_id同级填写source: bus；不要在组内每个子信号重复填写source。仅有一个CAN来源并不意味着整个计划只有一个来源。

### 不同来源怎样填写布尔值

|来源|未填写choices时|需要其他编码时|
|---|---|---|
|memory|values中使用原生true/false|整数0/1等须提供choices，例如[[0,false],[1,true]]。|
|signal_csv|单元格只接受精确小写文本true/false|True、FALSE、1、前后带空白均不自动转换；须定义与原单元格对应的choices。|
|CAN|只有读取器提供原生bool时可直接接受|DBC输出整数0/1时显式填写[[0,false],[1,true]]；float编码不能用此映射。|

CSV先按reader.missing_values匹配缺失标记，再解析布尔；例如NA在缺失列表中时产生无效值，不报布尔格式错误。choices中每个输入代码按类型和值必须唯一；多个不同代码可以映到同一个分析值，例如[[0,false],[1,true],[2,true]]。CSV还会检查文本歧义：整数1与字符串"1"不能同时作为两种输入码。


## 怎样选择转换、编码和质量字段

先确认CSV解析或DBC解码得到什么，再决定是否需要额外转换或剔除。下面六项分别处理不同问题；原始CAN表的value_map用于报文结构字段，不能替代分析信号的choices。

| 字段 | 什么时候填写、根据什么选择 | 省略或填写后的例子 |
|---|---|---|
| conversion.input_unit | 核对CSV列说明，或DBC解码后的物理单位；不是看原始位编码。目标单位由unit声明。 | 输入5000mA要得到5A：填mA、unit=A、scale=0.001；省略等同unit，不能让程序猜mA。详见[换算](#signal-conversion)。 |
| conversion.scale | 仅在读取器单位与目标单位的合法倍率不同时填写；按两单位的换算关系选择。布尔true不是数值1。 | mA→A填0.001；A→A省略保持1，不能填-1或2做方向/标定。 |
| choices | 原始开关/状态是代码时，依据设备编码表逐项对应；作用于解析后的编码，不是给任意文字改名。 | bool的整数0/1需[[0,false],[1,true]]；enum的整数1→running需[[1,running]]。省略时bool只接受布尔输入，CAN的enum可从DBC枚举表取得映射；其他来源缺少映射会被拒绝。见[编码例子](#signal-choices)。 |
| valid_range | 根据传感器物理范围或已确认的业务允许范围填写，使用转换后的单位；不为让结果通过随意扩大。 | mA→A后5A落在[-100,100]内；101A产生OUT_OF_RANGE，保持无效直到后续有效更新。省略不加这项范围限制。 |
| invalid_values | 根据数据规范中的“无效哨兵”填写，先确认读取器解析/解码后的类型和值。 | CSV文字65535.0解析为整数，应填[65535]；省略[]不增加哨兵检查。不能用它接管坏文本解析错误。见[类型对照](#signal-invalid-values)。 |
| measurement_location | 需要预设核对测量位置或追溯时，根据实际测点填写；不按信号名字猜。 | 电池包端测量填pack_terminal。普通信号省略不限制位置；充电预设的电流/电压角色缺少或填错位置会被拒绝。见[预设角色](presets.md#preset-role-requirements)。 |

<a id="signal-choices"></a>
## 布尔和枚举

布尔信号在表达式中表示真假；枚举信号表示离散状态名称，例如`idle`和`running`。这些名称是配置作者根据设备编码含义取的文本，后续表达式须使用相同拼写。两者都不参与数值缩放。

使用本页已给出的`signal-types.asc`和对应DBC。两个完整最小文件分别为[开关映射](examples/signal-bool-minimal.yaml)、[状态映射](examples/signal-enum-minimal.yaml)，均包含dataset、sources、signals及一条上升沿规则，可直接执行`chronaxis run 文件名.yaml --output 输出目录`。

开关配置将DBC信号Enabled的整数0变成false、1变成true；`condition: enabled`在100ms从假变真，输出一个事件。状态配置从DBC枚举表将ModeCode的0变成`idle`、7变成`running`；`condition: mode == "running"`也在100ms产生一个事件。300ms为分析终点，不计入会话范围。

完整扩展文件[signal-state-combined.yaml](examples/signal-state-combined.yaml)同时绑定两个DBC信号，运行应得到100ms的一个enabled_running事件。以下片段替换最小数值例的signals；同时将calculations删除，并改用下方规则。两个信号和来源均已在本页日志及DBC中定义；本扩展示例保留手工choices以演示覆盖DBC映射，普通枚举最小例直接省略choices。

```yaml
signals:                                        # 把输入字段定义为有名称、类型、单位和有效期的分析信号
  - choices:                                    # 把输入状态代码转成分析值；每项是[输入代码,结果值]，代码查设备规范
      - [0, false]
      - [1, true]
    field:                                      # 指定来源中的原始字段；CSV填表头，CAN填写通道/报文ID/DBC信号名
      frame_id: '0x102'                         # 选择包含信号的报文ID；从对应DBC取得，可写整数或支持的进制文本
      signal: Enabled                           # 填写DBC中的信号名称，大小写须一致
    name: enabled                               # 给分析信号取名称；后续表达式和计算通过此名称引用它
    valid_for: 200ms                            # 设置一次有效更新最多沿用多久；依据采样周期和允许数据陈旧程度填写
  - choices:                                    # 把输入状态代码转成分析值；每项是[输入代码,结果值]，代码查设备规范
      - [0, idle]
      - [7, running]
    field:                                      # 指定来源中的原始字段；CSV填表头，CAN填写通道/报文ID/DBC信号名
      frame_id: '0x103'                         # 选择包含信号的报文ID；从对应DBC取得，可写整数或支持的进制文本
      signal: ModeCode                          # 填写DBC中的信号名称，大小写须一致
    name: mode                                  # 给分析信号取名称；后续表达式和计算通过此名称引用它
    valid_for: 200ms                            # 设置一次有效更新最多沿用多久；依据采样周期和允许数据陈旧程度填写
    dtype: enum                                 # 选择分析值类型；float64小数、int64有符号整数、uint64非负整数、bool真假、enum状态名称
rules:                                          # 列出识别活动或瞬间变化的规则；每项产生有独立ID的事件
  - condition: enabled and mode == "running"    # 填写由已定义信号组成的真假条件；按要检测的业务情况设置
    name: enabled_running                       # 为规则取唯一名称；窗口rule和计算scope通过此名选择它的事件
    rule_type: rising_edge                      # 选择活动或变化识别算法；本例condition由false变为true时产生瞬时事件
```

每项`choices`只有左右两个值：左边是输入代码，右边是分析值。`[7,running]`不表示从第7列读取；列由field选择。bool映射右边必须是YAML真假值，不能写字符串`"true"`；enum右边必须是非空文本。未列入映射的可解析代码成为无效更新，旧状态不再沿用。

代码按类型匹配：整数`1`、布尔`true`和字符串`"1"`是不同代码。CSV只有文字，若同时声明整数1和字符串"1"，两者都对应单元格文字1，无法区分，会在建立来源时被拒绝；正常代码文字也不能同时列入missing_values。没有choices时，bool只接受原生布尔输入，不把任意非零数当真；enum必须具有手工映射或可读取的DBC枚举表。不能解析的CSV文本可能直接触发读取错误，不能依赖映射将所有坏文本变成未知。

<a id="signal-conversion"></a>
## DBC解码与信号额外换算

CAN读取器先从位编码取得数值，再执行DBC的factor和offset。CSV读取器先把单元格文本解析成数值或编码。signals.conversion中的scale/offset作用于读取器交付的值：`分析值 = 读取器输出值 × scale + offset`。DBC已完成的换算不应再填写一次。

| 读取器输出和目标 | signals中unit与conversion的填写 | 结果或检查 |
|---|---|---|
| 已解码5000mA，分析需要A | conversion.input_unit=mA，unit=A，conversion.scale=0.001；offset默认0 | 得到5A |
| DBC已经输出5A，分析仍需要A | conversion.input_unit=A，unit=A；conversion.scale/offset省略 | 保持5A |
| 已知单位A→A，想填scale=2或offset=-2 | 当前公开入口拒绝 | 这两个字段不是任意标定入口 |
| 已知单位A→A，想填scale=-1反向 | 当前公开入口拒绝 | sign_convention只声明方向，不能改变数值 |
| 任一单位不在当前单位表 | 有限scale/offset仍按声明执行，单位关系记unverified | 表示程序没有验证单位关系，不代表换算正确 |

已知单位包括1、V/mV、A/mA、W/kW、J/Wh/kWh、s/ms、Ah/A·s。两端已知时要求同一物理量、scale符合单位倍率，offset必须为0。当前公开signals没有direction_factor字段。温度等未知标签不会获得单位转换验证；不要改造单位名称来绕过检查。

若业务需要校准或改变方向，可在进入Chronaxis前明确处理输入，例如把确认以放电为正的电流乘-1写入新的CSV列，再按A→A、scale=1、offset=0绑定；保留原文件并记录处理公式。充电预设的具体方向要求见[角色要求](presets.md#preset-role-requirements)。

<a id="signal-invalid-values"></a>
## 原值类型与无效值

“额外转换前的值”已经过读取器解析或DBC解码，不一定等于文件中的文字，更不等于CAN原始位编码。invalid_values按原生类型和值同时匹配；目标dtype=float64不会把匹配前的所有值都变成float。

| CSV单元格文字 | 读取器交付值 | 对应invalid_values写法 |
|---|---|---|
| 65535或65535.0 | 整数65535 | [65535]；[65535.0]不会命中整数 |
| 1.5 | 浮点数1.5 | [1.5] |
| NA，且列入sources[].reader.missing_values | 缺失值None | 优先用missing_values处理文本缺失标记 |
| bad，未声明为缺失文本 | 无法解析为数值 | 读取报错；不能保证交给invalid_values再处理 |

missing_values匹配CSV原始单元格文字，invalid_values匹配解析后的类型和值。CAN场景若DBC把编码65535解码成6553.5，哨兵必须按解码后的值及类型声明，不能直接抄原位编码。

## 读取失败和无效更新

处理顺序为：读取器解析/DBC解码 → 检查缺失、非有限数、原值质量及invalid_values → 数值额外换算或bool/enum映射 → 目标类型与数值范围检查。映射编码和CSV文本之间的细节见[布尔和枚举](#signal-choices)。

| 输入情况 | 运行行为 | 应采取的动作 |
|---|---|---|
| 已声明为缺失文本的NA | 产生无效更新，旧值被替换；分析可继续，结果标记缺失 | 核对缺失时段及结果完整性 |
| 未声明为缺失的非法数字bad | CSV读取失败，公开运行抛AnalysisError，cause中保留SourceReadError、ValueError以及底层十进制解析异常 | 修正单元格，或确认其含义后声明为missing_values |
| 转换后的数值超出valid_range | 产生OUT_OF_RANGE无效更新；不截成边界数，也不补0 | 核对原数据、单位和真实业务范围 |

配置声明错误由PlanValidationError指出字段位置；已进入信号归一化阶段的无效值通过结果status/reason/quality呈现。不能将任意读取错误都解释为UNKNOWN并继续。处理步骤见[排错](troubleshooting.md)，状态含义见[结果](results.md)。

## valid_for：最近值可以沿用多久

不填写`valid_for`时，程序使用当前信号周期的3倍：先取该信号的`period`，没有填写时再从DBC读取所属报文周期。没有DBC的已解码CSV或内存信号可填写`period`。需要沿用历史样本、但不能取得周期时，会要求补充`period`或`valid_for`，不按相邻记录的间隔猜测周期。逐消息计算本身不沿用旧值，但当前公开运行入口仍会补齐已使用信号的默认有效期；因此也须提供可用的period、valid_for或DBC报文周期。公式参数parameters.period不会自动填入信号period。

例如电压周期100ms，默认有效期300ms；电流周期10ms，默认有效期30ms。各信号独立确定，不把计算驱动信号的周期套给其他信号。`valid_for: 500ms`会覆盖这项默认值。到期判断始终使用报文实际时间：电压在1秒更新，300ms有效期意味着1.3秒起旧电压不可用，不会因为固定周期计数较慢而继续使用。

`period`声明信号本身的周期，不会自动修改计算的间隔选项或导出的重采样网格。需要固定周期积分、报警或网格时，仍使用各功能的相应配置。

`valid_for: 3s`表示一次有效更新在仍有观测依据时，最多沿用3秒。新更新到来会替换旧值；没有新更新时，到期时刻开始未知。它不决定采样频率，也不是等待事件的timeout或条件确认时长minimum_duration。

快速开始的功率只在0、1、3、4秒更新，值依次为2、4、8、10W；更新间隔为1、2、1秒。6秒另有无关的0x7FE报文，表示来源观测到6秒，不是第五个功率样本。最后[4,6)在有效期内沿用10W：

| 最近更新 | 采用3s有效期 | 改为1s有效期 |
|---|---|---|
| 0秒：2W | [0,1)沿用2W，1秒被4W替换 | 同左 |
| 1秒：4W | [1,3)沿用4W | [1,2)为4W；[2,3)无有效功率 |
| 3秒：8W | [3,4)沿用8W，4秒被10W替换 | 同左 |
| 4秒：10W | [4,6)沿用10W | [4,5)为10W；[5,6)无有效功率 |

有效期端点不包含在旧值的有效区间中。若到期时正好有新有效更新，从该时刻采用新值。若2秒收到NA，则3s有效期也不能继续沿用1秒的4W：2秒起变为未知。日志只观测到6秒时，valid_for不会替你制造6秒之后的数据。

相关入口：[输入来源](inputs.md)、[表达式](expressions.md)、[业务预设](presets.md)。
