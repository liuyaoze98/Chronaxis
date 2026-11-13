# 表达式与派生信号


表达式是配置中的计算式或条件。`voltage * current`计算功率；`current > 5`判断电流是否大于5A。先在signals里绑定这些信号，表达式才能引用它们；原始CAN信号的类型和单位通常从DBC自动取得。

表达式放在`derived.<名称>.expr`、`rules[].condition`等明确接受表达式的字段中。派生信号输出随时间变化的值，条件输出真、假或未知。它使用受限表达式语法，不执行任意Python代码。下文列出支持的运算符和函数。

枚举信号用文本名称表示离散状态，例如`choices`把设备代码7转换为`"running"`，表达式就写`mode == "running"`。状态名称称为枚举标签，比较标签时使用字符串。需要比较原始整数编码时，使用 `enum_code(mode) == 7`；数值类型的状态信号可以直接写 `state == 7`。两种写法及编码要求见[整数状态与枚举编码](#enum-code)。

## 完整最小例与扩展例

[expression-minimal.yaml](examples/expression-minimal.yaml)引用0～4秒合成CAN记录，先定义电压400V和电流10A，再派生功率，求得最大功率4000W。无需自行准备前置配置。

[expression-extended.yaml](examples/expression-extended.yaml)使用相同数据，增加“电流>5A且电压>300V持续2秒”的活动，再对活动积分。活动在2秒确认，默认从0秒起算，得到4000W×4s=16000J。两个文件都可用`chronaxis run 文件名.yaml --output 结果目录`运行。

## 先准备来源和信号

保存[完整基础配置](examples/electrical-base.yaml)；它引用合成ASC报文和DBC，并声明下列信号；分析范围取全部实际观测。这里展示的是该文件根级signals的相关条目，用于解释后续引用；不需要再粘贴一遍。不同规则的小表是各自的概念对照，共享基础数据不保证产生每张小表的全部事件；有固定预期的完整任务使用各节专用配置。

基础文件已有的信号定义摘录：用于阅读，不重复插入；完整基础文件只有一个CAN来源，无需逐项重复source。信号的frame_id和signal来自随附DBC；类型与单位自动读取。此处显式保留20s有效期，保证稀疏教学记录之间仍有效，不代表实际设备的推荐设置。

```yaml
signals:                   # 定义公式使用的信号
  - name: temperature      # 公式中的信号名称
    field:                 # 输入中的原始字段
      frame_id: '0x11d'    # 信号所属报文 ID
      signal: Temperature  # DBC 中的信号名
    valid_for: 20s         # 设置一次有效更新最多沿用多久；依据采样周期和允许数据陈旧程度填写
  - name: voltage          # 公式中的信号名称
    field:                 # 输入中的原始字段
      frame_id: '0x11f'    # 信号所属报文 ID
      signal: Voltage      # DBC 中的信号名
    valid_for: 20s         # 设置一次有效更新最多沿用多久；依据采样周期和允许数据陈旧程度填写
  - name: current          # 公式中的信号名称
    field:                 # 输入中的原始字段
      frame_id: '0x114'    # 信号所属报文 ID
      signal: Current      # DBC 中的信号名
    valid_for: 20s         # 设置一次有效更新最多沿用多久；依据采样周期和允许数据陈旧程度填写
  - name: mode             # 公式中的信号名称
    field:                 # 输入中的原始字段
      frame_id: '0x118'    # 信号所属报文 ID
      signal: Mode         # DBC 中的信号名
    valid_for: 20s         # 设置一次有效更新最多沿用多久；依据采样周期和允许数据陈旧程度填写
  - name: request          # 公式中的信号名称
    field:                 # 输入中的原始字段
      frame_id: '0x11a'    # 信号所属报文 ID
      signal: Request      # DBC 中的信号名
    valid_for: 20s         # 设置一次有效更新最多沿用多久；依据采样周期和允许数据陈旧程度填写
    choices:               # 把输入状态代码转成分析值；每项是[输入代码,结果值]，代码查设备规范
      - [0, false]
      - [1, true]
  - name: response         # 公式中的信号名称
    field:                 # 输入中的原始字段
      frame_id: '0x11b'    # 信号所属报文 ID
      signal: Response     # DBC 中的信号名
    valid_for: 20s         # 设置一次有效更新最多沿用多久；依据采样周期和允许数据陈旧程度填写
    choices:               # 把输入状态代码转成分析值；每项是[输入代码,结果值]，代码查设备规范
      - [0, false]
      - [1, true]
```

## 配置片段：功率、工作事件与能量

已有两个float64信号：`voltage`单位V，`current`单位A。可在完整计划中加入：

应用位置：以[electrical-base.yaml](examples/electrical-base.yaml)为基础，在文件根级加入或替换`derived, rules, calculations`，代码已包含父键。存在同名列表时按本例替换该列表，不把父键再嵌入列表项。

```yaml
derived:                                      # 用已定义信号的表达式生成新信号；先定义再在后续功能中引用
  power:                                      # 定义名为power的派生信号，后面的计算通过此名称引用
    expr: voltage * current                   # 规定派生值如何由已有信号计算；名称必须先在signals或前面的derived中定义
rules:                                        # 列出识别活动或瞬间变化的规则；每项产生有独立ID的事件
  - name: working                             # 窗口或计算引用的规则名称
    condition: current > 5 and voltage > 300  # 填写由已定义信号组成的真假条件；按要检测的业务情况设置
    duration_comparison: ">="                 # 达到门槛即满足；要求严格超过时填>
    minimum_duration: 2s                      # 设置条件连续成立多久才确认活动；时长阈值由业务要求决定
    rule_type: condition_duration             # 选择活动或变化识别算法；本例条件连续成立达到minimum_duration后确认活动
calculations:                                 # 本例的统计结果
  - name: energy                              # 结果表中的计算名称
    expr: power                               # 使用已定义的信号或公式
    operation: integral                       # 按有效持续时间积分
    scope:                                    # 选择计算范围；session整段会话，{rule: 名称}逐事件，{window: 名称}逐片段
      rule: working                           # 按指定规则的每次事件分别计算；填写前面rules中的name
```

含义是：先计算功率；电流超过5A且电压超过300V连续保持2秒时确认活动；对每次活动算能量。上面只展示要加入的三个字段，来源、信号、时间范围仍须按[完整教程](quickstart.md)填写。

只计算一次的公式可以直接填入calculations[].expr，例如`expr: voltage * current`；需要多个规则或计算共用时，再命名为derived信号。

## 派生信号字段

派生信号采用名称到对象的映射，字段完整路径为`derived.<信号名>.expr`和`derived.<信号名>.unit`，例如`derived.power.expr`。power是自己取的名称；不要另加name键或把derived写成列表。

`derived`是“名称到定义”的映射，不是列表。名称与signals共享命名空间，不能重名；可以引用其他派生信号，但不能形成循环依赖。省略derived或填写`{}`表示不增加派生信号；null不合法。

| 完整路径 | 类型、默认与含义 |
|---|---|
| `derived.<名称>.expr` | 定义派生值的计算公式。必填字符串；从已定义的signals或derived中取名称，按业务公式组合，如voltage * current。不能引用未定义名称或形成循环。 |
| `derived.<名称>.unit` | 声明计算结果的物理单位。可省略，程序从公式和输入单位推导，如V×A得到W；显式填写时须为非空字符串，并与可推导结果一致。版本 4 会把数值换算到兼容的目标单位，例如 1500 W 指定 kW 后得到 1.5。 |
| `derived.<名称>.semantic_id` | 声明派生结果的业务含义，供描述和追溯；可省略，填写时采用项目约定的非空文本，如battery.power。表达式仍用派生名称；本版预设不从derived选择角色。 |
| `derived.<名称>.semantic_contract_version` | 记录派生结果业务含义的约定版本；可省略，填写时从项目业务规范取得非空文本，如"1"。它不改变config_version，也不使派生结果成为预设自动候选；不能填null。 |
| `derived.<名称>.sign_convention` | 说明派生结果正负号的物理含义；可省略，填写项目规定非空文本，如positive_is_charge，须与计算公式及输入方向一致。仅作声明，不把数值取反，不能填null。 |
| `derived.<名称>.measurement_location` | 记录派生结果对应的实际测点；按参与计算的传感器位置填写非空文本，如pack_terminal。可省略；声明不更换测点，不能填null。 |
| `derived.<名称>.metadata` | 保存本派生结果的自定义备注；键和值来自项目记录规则，如{formula_revision: "1"}。可省略或填{}；不是额外计算选项。 |

可选文本字段省略表示未声明，不能填null。派生信号的类型和有效性由表达式输入决定，不另填dtype或valid_for。未知引用、循环依赖、非法语法或类型/单位冲突会在计划检查时失败；除零等随数据出现的问题生成无效值，见[错误处理](troubleshooting.md)。

## 数字、名字和括号

|写法|含义|限制|
|---|---|---|
|`5`、`-2`、`0x1`、`0b1`|整数常量|运算结果需符合int64/uint64范围；比较阈值的大整数规则见下文|
|`0.5`、`1e3`|浮点数常量|必须是有限数值；不接受表示无穷大的`1e309`|
|`True`、`False`|布尔常量，表示真和假|表达式里的大小写按此填写，不写JSON布尔的`true`/`false`|
|`"charge"`|枚举标签字符串|只能按已声明的枚举标签做相等/不等比较；不能当普通文本处理|
|`current`|signals或derived中声明的简单名称|区分大小写；不自动查找同名原文件列|
|`(current > 5) and (voltage > 300)`|括号指定分组|可以嵌套；括号不会自动转换类型或单位|

YAML中可写`condition: mode == "charge"`。表达式本身是字符串，内部的`"charge"`是枚举标签；外层YAML与内部表达式分别解释，见[配置语法](configuration-language.md)。

别名只能用英文字母或下划线开头，后续可以有英文字母、数字和下划线，例如current_1。不能包含空格、中文或点号，不能使用 Python 关键字或所选配置版本保留的函数名，包括本页列出的所有内置函数。原文件的中文列名或带点号字段仍可放在field中，但须另外取一个合法name用于表达式。

## 数值运算

假设`x=6.0`、`y=2.0`，二者均为float64且单位为`1`（无单位）。

|运算符|示例|结果|说明|
|---|---|---|---|
|`+`|`x + y`|8.0|相加|
|`-`|`x - y`|4.0|相减|
|`*`|`x * y`|12.0|相乘|
|`/`|`x / y`|3.0|相除；整数相除也输出float64，不是向下取整|
|一元`+`|`+x`|6.0|保留原数值|
|一元`-`|`-x`|−6.0|取相反数|

这些运算用于数值，不能拿bool或枚举标签相加。除数为0、整数结果越界等会使该次计算无效，并记录原因，不返回一个正常的0。

## 比较运算

仍用`x=6.0`、`y=2.0`：

|运算符|示例|结果|含义|
|---|---|---|---|
|`==`|`x == y`|False|相等|
|`!=`|`x != y`|True|不相等|
|`<`|`x < y`|False|小于|
|`<=`|`x <= 6`|True|小于或等于|
|`>`|`x > y`|True|大于|
|`>=`|`x >= 6`|True|大于或等于|

链式比较也支持：`0 <= x < 10`等同于`(0 <= x) and (x < 10)`。等号比较写`==`；单个`=`不是比较。

bool之间和同一声明范围的枚举标签之间只支持`==`、`!=`，不支持`<`等大小比较。例如`mode == 'charge'`合法的前提是mode声明了标签charge；`mode == 'charging'`在标签未声明时会报错。

## 逻辑：and、or、not

|运算符|示例|怎么读|
|---|---|---|
|`and`|`current > 5 and voltage > 300`|两个条件都满足|
|`or`|`alarm or current > 100`|至少一个条件满足；alarm须是bool信号|
|`not`|`not alarm`|对已知真/假取反；未知仍为未知|

不能把数值当作条件：`current and voltage`会报错。应明确写比较，如`current > 0 and voltage > 0`。这里不使用`&`、`|`、`~`，也不能写其他语言的`&&`、`||`、`!`。

数据缺失时会出现UNKNOWN（无法判断）。完整规则如下，左右互换不改变and/or结果：

|A|B|A and B|A or B|
|---|---|---|---|
|True|True|True|True|
|True|False|False|True|
|True|UNKNOWN|UNKNOWN|True|
|False|False|False|False|
|False|UNKNOWN|False|UNKNOWN|
|UNKNOWN|UNKNOWN|UNKNOWN|UNKNOWN|

`not True=False`，`not False=True`，`not UNKNOWN=UNKNOWN`。程序仍记录输入的问题；不能依赖`and`/`or`来隐藏未知名称、非法语法或除零等质量信息。

## 内置函数

在配置文件开头使用整数 `config_version: 4`，可以让程序换算已登记的单位，并使用下列函数。当前开发版仅接受配置版本 4。

| 你想做什么 | 表达式举例 | 结果怎样读 |
|---|---|---|
| 把功率明确写成 kW | `to_unit(power, "kW")` | 1500 W 得到 1.5 kW；数值和单位一起变 |
| 写出阈值本身的单位 | `voltage > quantity(500, "mV")` | 无论电压声明为 V 还是 mV，阈值都是 0.5 V |
| 依开关选择一路功率 | `where(use_left, left_power, right_power)` | 开关必须为布尔信号；为真就取左路。此时右路缺值或刷新不影响结果；开关未知时结果也未知 |
| 同一时刻挑小值或大值 | `minimum(t1, t2, t3)`、`maximum(t1, t2)` | 两路或更多兼容数值一起比较；任一必要温度缺失，本次就没有可确定的极值 |
| 把值限制在上下界之间 | `clip(power, quantity(1.25, "kW"), quantity(2, "kW"))` | 若输入为 1、3 kW，按 kW 输出的两条结果是 1.25、2，均值是 1.625 kW |
| 平方或开方 | `square(current)`、`sqrt(square(current))` | −3 A 平方得 9 A²，再开方得 3 A。负数开方无效；不能对单位 A 直接开方 |

`where` 影响哪些点进入样本统计：所选信号每次真实更新都算一个样本；切换到另一支也算一次。开关仅刷新同一状态，或只有未选信号更新，不会把旧值多算一遍。同刻的更新一起处理。它与 `calculations[].condition` 用途不同：前者在两路值中选一路，后者只决定这个时段是否参加计算。

### 全部内置函数参数参考

下列签名中的参数默认是位置参数；只有 `isclose` 的容差和 `lookup` 的选项使用关键字。`x`、`a`、`b` 可以引用已声明信号或合法表达式。字符串字面量要写引号，例如 `"mV"`，不是另一个信号名。配置错误会在加载／校验时拒绝；某次数据无效只使该次表达式结果无效，并保留质量原因。

| 完整调用 | 参数和静态要求 | 返回值、单位和数据错误 |
|---|---|---|
| `abs(x)` | 一个数值输入；不接受关键字 | 同类型的绝对值；int64最小负数无法表示绝对值，记溢出 |
| `isclose(a, b, atol=数值, rtol=数值)` | 两个可比较数值；两容差都必填，均为非负有限数字字面量 | 布尔值，判据与容差单位见下节；输入无效或中间运算失败时未知 |
| `quantity(value, "unit")` | value只能是有限数字字面量（可带正负号），不能是信号或`1/10`；整数须在64位范围；unit必须已登记 | 给常量明确单位与尺度；`quantity(500,"mV")`是500mV，不生成新样本 |
| `to_unit(x, "unit")` | 数值输入；目标是已登记且量种兼容的单位字面量 | 同一物理值换算成目标单位；必要时提升float64，精度／范围错误记无效 |
| `where(condition, when_true, when_false)` | 三个位置参数；condition为bool，两支为兼容数值。两支的名称、语法、类型、单位都须静态合法 | 条件为真／假时只采用对应分支的值与质量；条件未知则结果未知。不能用未选分支隐藏不存在的名称 |
| `minimum(a, b, ...)`、`maximum(a, b, ...)` | 至少两个数值，单位和类型必须可统一；有多个原声明尺度时，裸常量可能歧义，改用quantity | 该时刻的最小／最大值，通常为[规范单位](#canonical-units)；任何必要输入缺失均传播，不忽略缺失通道 |
| `clip(x, lower, upper)` | 三个兼容数值；下界不能大于上界。常量倒置在校验时拒绝；动态倒置在运行时判无效 | 将x限制在闭区间内；必要输入无效则结果无效。`clip(power,quantity(1,"kW"),quantity(2,"kW"))`明确界限 |
| `square(x)` | 一个数值，单位允许平方；摄氏绝对温度先显式换到K | 数值平方、单位平方；定宽溢出或浮点超限时无效 |
| `sqrt(x)` | 一个数值，已知单位的各量种指数须可开平方；先换算尺度 | float64及开方后的单位；负值无效。例如sqrt(square(current))是电流绝对值，不是原带符号电流 |
| `mod(a, b)` | 同类型int64或uint64、单位1；裸整数按输入类型解释 | 同类型余数，符号随除数；除数0时无效 |
| `bit_test(x, bit)` | x为单位1整数；bit是0～63的整数常量 | bool；有符号数按64位补码取位，原无效值继续无效 |
| `bit_extract(x, start, width)` | x为单位1整数；start为0～63、width为1～64-start的整数常量 | uint64、单位1；从最低位编号0提取连续位 |
| `to_int64(x)`、`to_uint64(x)`、`to_float64(x)` | 一个数值输入；显式to_unit/quantity尺度优先，否则采用规范单位 | 指定类型、保持所选单位；小数转整数不截断，超限不回绕，不能精确表示时无效 |
| `enum_code(x)` | x必须为保留原整数编码且具有code_dtype的枚举来源；不能传标签文字 | 返回原int64/uint64、单位1；独立检查原码质量，不从标签反推编码 |
| `lookup(x, "table", mode="linear", bounds="invalid")` | 数值x；已声明表名和选项均为字符串字面量；两个位置参数，其余只能关键字 | 按表输出单位返回值；线性为float64，阶梯类型由表决定，见[一维查表](#lookup-reference) |

例如 `where(enabled, power, missing_name)` 即使enabled始终为真也会在校验时失败。`minimum(v_in_V, v_in_mV, 1)` 无法确定1按V还是mV解释，应写 `quantity(1,"V")`；只有唯一可采用的原声明尺度时，裸常量才继承该尺度。

<a id="enum-code"></a>

### 整数状态位、枚举编码与类型转换（版本 4）

这些写法可放进 `derived.<名称>.expr`、`rules[].condition` 或 `calculations[].expr`。如果状态已经声明为 `int64` 或 `uint64`，可直接写 `state == 0x1`，不必先建立枚举映射。声明为 `enum` 后，`mode == "charge"` 比较标签；`enum_code(mode) == 0x1` 则比较保留的原始整数编码，两者选择不同的比较依据。

| 函数与参数 | 含义与要求 |
|---|---|
| `mod(x, y)` | 无单位整数求余；两项使用相同整数类型，除数为 0 时结果无效 |
| `bit_test(x, bit)` | 检查某一位，返回布尔值；bit 是 0～63 的整数常量，从最低位 0 开始 |
| `bit_extract(x, start, width)` | 提取连续位，返回 uint64；start 为 0～63，width 为 1～64-start，均为整数常量 |
| `to_int64(x)`、`to_uint64(x)`、`to_float64(x)` | 显式转数值类型；小数不截断、溢出不回绕，不能精确表示时无效 |
| `enum_code(x)` | 读取枚举记录保留的整数编码；不从文字标签反推。两个编码共用同一标签时仍能区分；没有标签映射的有效编码也能返回 |

位函数的输入必须为单位 `1` 的 int64/uint64。例如 flags=6（二进制 110），`bit_test(flags,0)` 为 False，`bit_extract(flags,1,2)` 为 3。有符号整数按 64 位补码解释。内存枚举使用 `enum_code` 时须声明 `code_dtype` 并提供原始编码；DBC 枚举从信号定义取得编码类型。无效记录不会因为取编码而变有效。

类型转换保留物理量含义，默认先按规范单位解释。例如 1500 mV 换成 1.5 V 后不能精确转成整数；若需要整数毫伏，写 `to_int64(to_unit(voltage, "mV"))`。

### abs(x)：取绝对值

`abs(-3)`得到3；`abs(current)`的单位仍是A。必须恰好一个位置参数，不接受`abs(x=current)`。输入只能是数值。

int64最小值是−9223372036854775808，它的绝对值超过int64上限，因此不是正常可用结果；不能把溢出后的负数当绝对值返回。

### isclose(a, b, atol=..., rtol=...)：允许误差的比较

`==`比较精确相等。实际测量中通常允许一点误差，此时可写：

```text
isclose(voltage, 400, atol=0.1, rtol=0)
```

表示电压与400V的差不超过0.1V。两个容差都必须写，且为有限、非负的数字常量：不能省略一个，也不能用信号名或`1/10`代替字面数字。

|参数|可填写的内容|必填及默认值|含义和本例写法|
|---|---|---|---|
|a|数值信号、数值表达式或数字|必填，无默认值；放在第一个位置|要检查的数，本例写voltage。|
|b|数值信号、数值表达式或数字|必填，无默认值；放在第二个位置|用来比较的基准，本例写400，按电压单位解释为400V。|
|atol|大于或等于0的有限数字常量|必填，无默认值；写成atol=数值|允许的固定差值。atol=0.1表示允许相差0.1V。|
|rtol|大于或等于0的有限数字常量|必填，无默认值；写成rtol=数值|按b的绝对值增加的容差比例。rtol=0不增加；rtol=0.01增加1%。|

比较时，裸数字先继承另一项的原声明单位，然后两项转换到规范单位；`atol`的数字直接按该规范单位解释，`rtol`无单位。规范单位是运算统一使用的尺度，例如mV→V、mA→A、kW→W，完整对照见[规范单位](#canonical-units)。

例如voltage声明为mV且值为500.0，`isclose(voltage,501,atol=0.1,rtol=0)`先比较0.5V和0.501V，再允许0.1V的差，因此为True。若允许误差只是0.1mV，应写`atol=0.0001`（V），结果为False。voltage声明为V且值为0.5时，用`isclose(voltage,0.501,atol=0.0001,rtol=0)`得到相同的False。

`atol`不能写quantity、信号或计算式。即使先用to_unit把输入显式改成mV，比较仍会统一到V，不能据此把atol当成mV。

程序把两部分允许误差相加：固定差值atol，加上b的绝对值乘rtol。公式是 `abs(a-b) <= atol + rtol*abs(b)`。

例如a=102、b=100、atol=0、rtol=0.02，允许相差100×2%=2，实际也相差2，所以结果为True。比例按第二个数b计算，因此交换a和b不一定得到相同结果。输入无效或计算失败时，结果是UNKNOWN。

<a id="lookup-reference"></a>
### 一维查表与插值

根级 `lookups` 定义用户提供的标定点，表达式 `lookup` 按输入坐标查找输出。标定关系来自设备规范、试验或已确认数据，不是内置的电压转功率规律。

| `lookups[]`字段 | 类型与要求 | 填写依据 |
|---|---|---|
|name|必填名称，表内唯一；最多64张表|由配置作者命名，lookup用字符串引用|
|points|必填2～4096个`[输入,输出]`点对|输入坐标严格递增且不重复；只能用有限数字，不能是bool或文本|
|input_unit|必填已登记单位字符串|点对第一列的物理单位；调用输入须可换算到它|
|unit|必填已登记单位字符串|第二列的物理单位，也是查表结果单位|

输入坐标须能由float64精确表示；线性模式的输出也必须能精确转成float64。阶梯模式可保留int64／uint64整数；若同表有浮点输出，则所有输出须能精确转float64。负整数与超出int64上限的正整数不能混为同一整数表。

调用为 `lookup(x, "curve", mode="linear", bounds="invalid")`。x与表名是且仅是两个位置参数；mode和bounds可省略，但填写时只能用关键字和字符串字面量。

|选项|默认值和允许值|行为|
|---|---|---|
|mode|linear（默认）|在相邻两个标定点间作线性插值；恰在点上返回该点|
|mode|previous|取输入坐标左侧最近标定点的输出；恰在点上取本点|
|mode|next|取输入坐标右侧最近标定点的输出；恰在点上取本点|
|bounds|invalid（默认）|超出表两端时返回无效值，不外推|
|bounds|clamp|超出表两端时使用最近端点的输出|

未知表名、未登记／不兼容单位、重复横坐标、超出点数、动态表名或非法选项在校验时拒绝；运行中缺值、精度损失或默认策略下越界会标为无效。完整[标定曲线配置](examples/lookup-power.yaml)包含ASC、DBC绑定及点表；下方示例展示实际结果。

#### 示例：电压到标定功率

[下载 ASC 查表示例](examples/lookup-power.yaml)，和它的 `data/joint.asc`、`data/joint.dbc` 保持相对位置。运行 `python -m chronaxis run lookup-power.yaml --output result`。示例中 3 V 对应 10 W，11 V 对应 50 W。读到 7 V 时，`lookup(voltage,'curve')` 取中间值 30 W；若写 `mode='previous'` 则取 10 W，写 `mode='next'` 则取 50 W。范围外的输入默认无效，只有希望沿用最近端点时才填 `bounds='clamp'`。

在示例的 0 到 3 秒（不含第 3 秒），三次读数是 3、7、3 V。默认线性查表依次得到 10、30、10 W，所以会话结果 `rated_power` 约为 16.67 W。它是三次功率的样本平均值。

## 运算先后顺序

从先到后：括号/函数调用 → 一元`+ -` → `* /` → 二元`+ -` → 六种比较 → `not` → `and` → `or`。同一层的算术按从左到右处理。

因此`x + y * 2`在上述数值下为10，而`(x + y) * 2`为16。复杂条件建议保留括号，让别人不用回忆优先级也能读懂。

## 单位推导与自动换算

|写法|解释|
|---|---|
|`current > 5`|current单位A时，5按5A比较|
|`voltage + 1`|voltage单位V时，加的是1V|
|`current * 2`、`current / 2`|2是无单位倍率，结果仍为A|
|`voltage * current`|V×A得到W|
|功率×秒、安培×秒|支持W×s=J、A×s=A·s；两个乘数交换顺序也支持|
|`voltage / other_voltage`|两者同单位V时，结果无单位|

版本 4 自动换算已登记的兼容单位：500 mV + 2 V 得到 2.5 V，V 除以 A 得到 Ohm。输入单位与目标单位不同时，通常不用手填比例；一旦显式填写 scale 或 offset，就表示完整换算，不会再乘一遍单位倍率。两个温度相减得到温差；摄氏温度需先明确换到 K 才能参与乘法。

用户自定义的未知单位组合可通过派生信号显式声明结果标签，但会保留`unverified`，意思是程序没有验证这条单位关系；填上一个单位名称不证明物理关系正确。

<a id="canonical-units"></a>
### 规范单位对照

规范单位是计算采用的统一尺度。输出单位可以另选；isclose.atol按此处的比较单位填写。

复合单位优先使用已登记的W、J，例如电功率变化率写W/s，电功率的倒数写1/W，电能的倒数写1/J。这些文字可作为单位再次解析。显示简化不替代数值换算：mA×V仍带千分之一尺度；N*m仍表示力矩，不自动改成J；绝对温度和温差也保持区别。

| 输入单位 | 规范单位 |
|---|---|
|%, 1|1|
|mV, V; mA, A; kW, W|V; A; W|
|Wh, kWh, J; Ah, A*s|J; A*s|
|ms, us, ns, s|s|
|degC, K; delta_degC, delta_K|K; delta_K|
|mOhm, kOhm, MOhm, Ohm|Ohm|
|deg, rad; rpm, rad/s|rad; rad/s|
|kPa, bar, Pa|Pa|
|m, N, N*m, Hz|m, N, N*m, Hz|

## 数据类型、数值精度与错误处理

两个实际信号的算术要求dtype相同。例如float64电流与int64倍率信号不能直接相乘，可在输入声明中统一类型，版本 4 也可用 `to_float64` 等下列显式转换函数；没有 Python 的 `float()` 或 `int()` 函数。版本 4 的单位换算也可能将整数提升为 float64。数值常量另有明确处理，例如float64信号可以乘整数常量2。

int64和uint64信号之间可以直接比较大小，程序按整数比较，不先转成可能丢精度的小数。整数信号与float64信号比较前，则需要先统一类型。

比较时的整数常量可以超出信号类型范围。例如int64信号与9,223,372,036,854,775,808比较，程序仍能正确判断信号更小。但这不表示该常量也能用于int64加法：算术需要额外检查能否用目标类型表示。

- 名称不存在、单位冲突、函数不支持等是配置错误，检查计划时就拒绝。
- 除数恰好为0、某次输入缺失、数值运算越界等发生在处理实际数据时；该次结果无效，附带原因。
- 无效结果怎样影响活动和统计，见[时间和统计](concepts.md)以及[数据不完整时的处理](execution.md)。

## 不支持的写法及替代办法

|不支持|例子|需要怎么做|
|---|---|---|
|幂、取模、整除、矩阵乘|`x ** 2`、`x % 2`、`x // 2`、`x @ y`|版本4用`square(x)`求平方、`mod(x,2)`求整数余数；整除和矩阵乘不支持|
|位运算和位移|`x & 1`、`x \| 1`、`x ^ 1`、`~x`、`x << 1`、`x >> 1`|版本4用`bit_test(flags,0)`检查最低位，用`bit_extract(flags,1,2)`取从第1位开始的两位|
|成员/身份判断|`x in [1,2]`、`x not in ...`、`x is None`、`x is not None`|枚举选择可写`mode == 'a' or mode == 'b'`；缺值通过质量信息处理|
|属性、下标和切片|`battery.current`、`x[0]`、`x[1:3]`|使用signals里声明的简单别名；不能在式子里取历史数组|
|其他函数或方法|`min(x,y)`、`round(x)`、`float(x)`、`signal('x')`、`x.mean()`|版本4用`minimum(x,y)`求小值；只调用本页列出的函数|
|参数展开|`abs(*items)`、`isclose(x,y,**opts)`|按上面固定签名逐个填写|
|容器、推导式、条件表达式|`[x,y]`、`{'x':x}`、`[v for v in x]`、`x if flag else y`|数值条件选择用`where(flag,x,y)`；其他容器或推导式不支持|
|赋值、lambda、导入|`x = 2`、`(x := 2)`、`lambda x: x`、`__import__('os')`|表达式只计算值或判断条件，不执行脚本|
|None、复数、字节串和文本操作|`None`、`1j`、`b'abc'`、`'a' + 'b'`|数据缺失用输入/质量规则表示，字符串可用于枚举标签和函数明确要求的单位等参数|

本页各项支持/拒绝例子及双后端预期由[readability_examples.py](examples/readability_examples.py)实际核对。它验证的是本页规则，不把支持这些写法扩大为支持全部Python语法。
