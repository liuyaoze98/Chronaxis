# 业务预设

预设就是一组已经写好的规则和计算项。你告诉它“哪条信号表示请求、哪条表示响应”，它替你生成两条上升沿规则和一组配对。**角色**表示信号在这组规则中的用途；`role_bindings`把角色名对应到你在`signals`中定义的别名。

预设在加载计划时展开为derived、rules、windows、sequences或calculations；运行后通过这些生成节点读取结果。先准备满足角色要求的信号，再选择预设。

本页未另行说明的秒数例子采用默认actual。配置intervals为fixed或dbc时，持续确认、等待到期、变化窗口和配对delay_ns使用所选周期依据；原时间坐标和信号到期仍按实际记录时间。先看[三种时间依据对照](intervals.md#timing-basis)。

一个预设填写为`presets`数组中的一个对象，例如本页的请求响应配置。对象里的字段完整路径例如`presets[].name`；下表使用相对字段名。`parameters`和`role_bindings`中的字段因预设种类而不同，后面分别列出。

|字段|数据类型|必填|省略时的值|可填写的值及用途|
|---|---|---|---|---|
|name|字符串|是|无|命名本次预设实例，由配置作者自行取名。本预设的名字，例如`cmd`。生成的规则会用这个名字作前缀，例如`cmd_request`；不能与其他预设重复，也不能让生成的名字与已有规则、窗口、计算项重名。名字的格式见[配置约定](configuration.md)。|
|preset_type|字符串|是|无|选择要组合执行的业务功能。`charge_session`找充电时段；`fault_context`截取故障发生前后的数据；`command_response`检查请求是否得到响应；`threshold_excursion`统计超过阈值的时段。|
|version|字符串|否|`"1"`|选择预设的规则定义版本；根据本页支持版本填写。填`"1"`，表示使用当前版本的预设定义。这里不是数字`1`。|
|parameters|对象|是|无|组织所选预设的业务参数；数值来自试验目标或设备协议。填写所选预设的参数，见下面四张表。不同种类的参数不能混用。|
|role_bindings|对象|否，阈值预设除外|空对象|指定每个业务用途使用哪条原始绑定信号；值取自signals[].name。把角色名对应到已声明的信号名。例如YAML写法`request: start_button`表示用`start_button`信号判断请求。各角色要求见后文。|

建议明确写角色映射。没有写某个角色时，除阈值预设外，程序会按信号的`semantic_id`等声明寻找对应信号；必须恰好找到一条。找不到或找到多条都会报错，信号名相似不作为选择依据。

本页“角色要求”规定某个用途能接受什么输入。例如充电的`current`角色需要符合单位、正负方向和测量位置要求的电流。这些条件也称为语义契约；版本取自本页角色表。自动查找表示按这些声明选信号，不是根据CSV表头猜测含义。显式绑定只决定选谁，仍需满足角色要求。

## 完整最小例与扩展例

以下文件均引用随附的0～4秒合成CAN输入，包含所需来源、信号和预设，可以独立运行。先读最小例，再比较扩展例；无须复制后文的教学基础文件。命令为`chronaxis run 文件名.yaml --output 新目录`。

| 功能 | 最小文件与输入 | 扩展文件及新增内容 | 核对结果 |
|---|---|---|---|
| 充电时段 | [preset-charge-minimal.yaml](examples/preset-charge-minimal.yaml)：模式在1～3秒为1，电流10A | [preset-charge-energy.yaml](examples/preset-charge-energy.yaml)：增加400V电压、能量和电荷积分 | 活动[1,3)；扩展得到8000/3600Wh和20/3600Ah |
| 故障上下文 | [preset-fault-minimal.yaml](examples/preset-fault-minimal.yaml)：报警在1秒上升，取后1秒 | [preset-fault-context.yaml](examples/preset-fault-context.yaml)：改取前1秒、后2秒，并允许初始报警 | 最小片段[1,2)，扩展[0,3)；初始为false，本例开启emit_initial不增加事件 |
| 请求响应 | [preset-command-minimal.yaml](examples/preset-command-minimal.yaml)：1秒请求、2秒响应，明确绑定角色 | [preset-command-automatic.yaml](examples/preset-command-automatic.yaml)：增加业务声明，省略role_bindings，自动选相同信号 | 两者都配成一对，延迟1秒 |
| 阈值报警 | [preset-threshold-minimal.yaml](examples/preset-threshold-minimal.yaml)：温度70、85、77、75、70，每秒更新 | [preset-threshold-delay.yaml](examples/preset-threshold-delay.yaml)：增加500ms进入和解除确认 | 最小活动[1,3)；扩展在1.5秒确认进入、3.5秒确认解除，活动[1.5,3.5)，两者均2秒 |

## 先准备来源和信号

保存[完整基础配置](examples/electrical-base.yaml)；它引用合成ASC报文和DBC，并声明下列信号；分析范围取全部实际观测。这里展示的是该文件根级signals的相关条目，用于解释后续引用；不需要再粘贴一遍。不同规则的小表是各自的概念对照，共享基础数据不保证产生每张小表的全部事件；有固定预期的完整任务使用各节专用配置。

基础文件已有的信号定义摘录：用于阅读，不重复插入；完整基础文件只有一个CAN来源，无需逐项重复source。信号的frame_id和signal来自随附DBC；类型与单位自动读取。此处显式保留20s有效期，保证稀疏教学记录之间仍有效，不代表实际设备的推荐设置。

```yaml
signals:                                   # 把输入字段定义为有名称、类型、单位和有效期的分析信号
  - name: temperature                      # 给分析信号取名称；后续表达式和计算通过此名称引用它
    field:                                 # 指定来源中的原始字段；CSV填表头，CAN填写通道/报文ID/DBC信号名
      frame_id: '0x11d'                    # 选择包含信号的报文ID；从对应DBC取得，可写整数或支持的进制文本
      signal: Temperature                  # 填写DBC中的信号名称，大小写须一致
    valid_for: 20s                         # 设置一次有效更新最多沿用多久；依据采样周期和允许数据陈旧程度填写
  - name: voltage                          # 给分析信号取名称；后续表达式和计算通过此名称引用它
    field:                                 # 指定来源中的原始字段；CSV填表头，CAN填写通道/报文ID/DBC信号名
      frame_id: '0x11f'                    # 选择包含信号的报文ID；从对应DBC取得，可写整数或支持的进制文本
      signal: Voltage                      # 填写DBC中的信号名称，大小写须一致
    valid_for: 20s                         # 设置一次有效更新最多沿用多久；依据采样周期和允许数据陈旧程度填写
    measurement_location: pack_terminal    # 声明实际测点；pack_terminal表示电池包端，须依据接线和设备定义
  - name: current                          # 给分析信号取名称；后续表达式和计算通过此名称引用它
    field:                                 # 指定来源中的原始字段；CSV填表头，CAN填写通道/报文ID/DBC信号名
      frame_id: '0x114'                    # 选择包含信号的报文ID；从对应DBC取得，可写整数或支持的进制文本
      signal: Current                      # 填写DBC中的信号名称，大小写须一致
    valid_for: 20s                         # 设置一次有效更新最多沿用多久；依据采样周期和允许数据陈旧程度填写
    measurement_location: pack_terminal    # 声明实际测点；pack_terminal表示电池包端，须依据接线和设备定义
    sign_convention: positive_is_charge    # 声明正负值的业务含义；positive_is_charge表示正电流为充电，不执行取反
  - name: mode                             # 给分析信号取名称；后续表达式和计算通过此名称引用它
    field:                                 # 指定来源中的原始字段；CSV填表头，CAN填写通道/报文ID/DBC信号名
      frame_id: '0x118'                    # 选择包含信号的报文ID；从对应DBC取得，可写整数或支持的进制文本
      signal: Mode                         # 填写DBC中的信号名称，大小写须一致
    valid_for: 20s                         # 设置一次有效更新最多沿用多久；依据采样周期和允许数据陈旧程度填写
  - name: request                          # 给分析信号取名称；后续表达式和计算通过此名称引用它
    field:                                 # 指定来源中的原始字段；CSV填表头，CAN填写通道/报文ID/DBC信号名
      frame_id: '0x11a'                    # 选择包含信号的报文ID；从对应DBC取得，可写整数或支持的进制文本
      signal: Request                      # 填写DBC中的信号名称，大小写须一致
    valid_for: 20s                         # 设置一次有效更新最多沿用多久；依据采样周期和允许数据陈旧程度填写
    choices:                               # 把输入状态代码转成分析值；每项是[输入代码,结果值]，代码查设备规范
      - [0, false]
      - [1, true]
  - name: response                         # 给分析信号取名称；后续表达式和计算通过此名称引用它
    field:                                 # 指定来源中的原始字段；CSV填表头，CAN填写通道/报文ID/DBC信号名
      frame_id: '0x11b'                    # 选择包含信号的报文ID；从对应DBC取得，可写整数或支持的进制文本
      signal: Response                     # 填写DBC中的信号名称，大小写须一致
    valid_for: 20s                         # 设置一次有效更新最多沿用多久；依据采样周期和允许数据陈旧程度填写
    choices:                               # 把输入状态代码转成分析值；每项是[输入代码,结果值]，代码查设备规范
      - [0, false]
      - [1, true]
```

## 先判断充电预设是否符合目标

`charge_session`版本1采用固定的组合方式：模式等于指定编码、电流**严格大于**门槛，连续**达到**指定时长后，把条件开始到结束的整个区间作为统计范围。能量输出Wh，电量输出Ah。这些规定适合你的目标时再使用预设；名字包含“充电”不足以决定入口。

| 你的要求 | 采用的入口及原因 |
|---|---|
| 模式等于指定编码、电流`>5A`、连续`>=3s`，输出Wh | 可用充电预设；还需有依据地声明其电流方向和测点。|
| 电流`>=10A`，恰好10A也要参与 | 用[持续条件](rules.md)＋[事件范围积分](calculations.md)；预设的`>10`会排除这部分。|
| 连续时间严格`>60s`，恰好60秒排除 | 普通规则填写`minimum_duration: 60s`和`duration_comparison: ">"`；不要把60s改成60.1s来近似。|
| 直接输出kWh，或组合多个自定义状态条件 | 普通规则保留你的完整条件，积分`unit`填`kWh`，不必改造预设或另写计算器。|
| 仅按明确公式`电压×电流`积分，没有充电方向或测点要求 | 普通积分无需为套用预设额外填`sign_convention`或`measurement_location`。|

例如随附[能量例](examples/preset-charge-energy.yaml)在1～3秒模式为1，电流10A、电压400V。预设门槛5A与普通条件`mode == 1 and current > 5`都选出[1,3)，能量为400×10×2＝8000J＝2.222222…Wh。把门槛改为10A时，预设没有合格区间；普通条件`current >= 10`仍得到这段，若指定kWh则为0.002222222…kWh。两种数值的单位不同，不能直接比较大小。

普通规则的`selection_origin`默认就是`onset`，包含达到持续门槛之前已经连续成立的部分；显式选择`confirmed`才从确认时刻开始。覆盖率门槛按需求填写，不因为这是充电任务就自动补上95%。

## 充电时段：charge_session.parameters

这里的charge_session是preset_type取值，不是父键。本表字段位于`presets[].parameters`，例如parameters对象内填写下列参数。

|字段|数据类型|必填|省略时的值|可填写的值及用途|
|---|---|---|---|---|
|mode_value|整数|是|无|选择哪种设备模式被视为充电；从设备状态编码表取得。表示已定义mode信号中的充电模式整数值，例如设备用`1`表示充电就填`1`。值必须能由mode信号的整数类型及有效范围表示。|
|current_min|数值|是|无|设置充电识别的最低电流门槛；按试验要求以安培填写。电流门槛，单位A，可为负数。判断条件是电流**大于**它；填`5`时，恰好5A不满足条件。|
|minimum_duration|时长字符串|是|无|设置确认充电前条件必须连续成立的时长；按业务确认要求填写。模式匹配且电流超过门槛要连续保持多久，达到后才确认充电时段。可为0，例如`"3s"`表示连续3秒。确认后统计范围从条件最初成立时开始，包含这3秒。|
|compute_energy|布尔值|否|`false`|控制是否生成能量积分。`true`增加电压×电流的功率信号和Wh能量计算项，因此还需要voltage角色；`false`不生成这两项。|
|compute_charge|布尔值|否|`false`|控制是否生成电荷量积分。`true`增加电流对时间的积分，输出Ah电荷量；`false`不生成电荷计算项。两个compute选项可分别设置，也可同时开启。|
|minimum_coverage|数值|否|`0`|设置结果所需的最低数据覆盖比例；按允许缺失程度填写。0到1，含两端。例如`0.9`要求至少90%的覆盖率；任何一项覆盖率未达到它，coverage_status就标为indeterminate。这个门槛不删除已算出的数值；是否保留部分数值由partial_policy决定。覆盖判定见[统计与积分](calculations.md)。|
|partial_policy|字符串|否|继承`execution.partial_policy`|控制数据不全时是否保留部分计算值。`"report"`：数据缺失时可返回能够算出的部分，并标明不完整；`"strict"`：所需计算时段内有缺失时，计算值为空。仅影响生成的能量、电荷计算项，详见[数值例子](execution.md)。|

以预设name为 `"charge"` 为例，两个选项分别决定是否增加以下计算：

|compute_energy|compute_charge|生成什么|
|---|---|---|
|false|false|只生成charge_activity，用来找出充电时段。|
|true|false|另生成charge_power功率信号和charge_energy能量计算项，单位Wh。|
|false|true|另生成charge_charge电荷量指标，单位Ah。|
|true|true|功率、能量、电荷量三项都生成。|

把预设name换成其他名字，生成名称的前缀也随之改变。

## 故障前后数据：fault_context.parameters

这里的fault_context是preset_type取值，不是父键。本表字段位于`presets[].parameters`，例如parameters对象内填写下列参数。

|字段|数据类型|必填|省略时的值|可填写的值及用途|
|---|---|---|---|---|
|pre|时长字符串|否|0s|设置每次故障发生前要取的上下文时长；按定位问题所需的历史长度填写。故障发生前保留多久，须大于等于0。例如故障在10秒，填`"2s"`就从8秒开始取数据。|
|post|时长字符串|否|0s|设置每次故障发生后要取的上下文时长；按观察恢复过程所需长度填写。故障发生后保留多久，须大于等于0。pre和post至少一项大于0；post填`"3s"`时，上例取到13秒之前。|
|emit_initial|布尔值|否|`false`|控制初次观测就为真是否算一次新事件。`false`：第一条有效记录已经是报警状态时，不认定刚发生了一次故障；`true`：把这个初始报警也记作故障点，并为它生成前后片段。|

生成`<name>_alarm`上升沿规则和`<name>_context`窗口。相邻故障的窗口各自保留，不自动合并。

## 请求与响应：command_response.parameters

这里的command_response是preset_type取值，不是父键。本表字段位于`presets[].parameters`，例如parameters对象内填写下列参数。

|字段|数据类型|必填|省略时的值|可填写的值及用途|
|---|---|---|---|---|
|min_delay|时长字符串|否|0s|设置协议允许的最短响应延迟；根据请求响应规范填写。响应最早可以比请求晚多久，须大于等于0；填`"0s"`时可在同一时刻响应。|
|max_delay|时长字符串|是|无|设置协议允许的最长响应延迟；根据超时要求填写。响应最迟可以比请求晚多久，不能小于min_delay；恰好在这个截止时刻响应仍算成功。|
|emit_initial|布尔值|否|`false`|控制初次观测就为真是否算一次新事件。`false`：请求、响应信号最初就为真时，都不因此产生事件；`true`：两条信号各自最初为真时也产生事件。|
|max_pending|整数|否|`65536`|限制同时等待响应的请求数量；依据最大并发请求数及资源预算填写。大于0；最多同时保存多少个尚未得到响应的请求。超过此数报错，不会丢弃最早的请求。|

生成`<name>_request`、`<name>_response`上升沿和`<name>_pair`配对。排队、缺失数据和超时处理见[请求与响应](sequences.md)。

## 超阈值时段：threshold_excursion.parameters

这里的threshold_excursion是preset_type取值，不是父键。本表字段位于`presets[].parameters`，例如parameters对象内填写下列参数。

|字段|数据类型|必填|省略时的值|可填写的值及用途|
|---|---|---|---|---|
|unit|字符串|否|所绑定signal角色的单位|声明阈值的单位；从所选信号unit原样取得。阈值的单位，必须与signal角色的信号单位相同。例如信号单位为`degC`时通常省略；需要显式说明时可填`"degC"`。|
|enter_threshold|数值|是|无|设置开始报警的高阈值；按报警规范填写，使用parameters.unit的单位。信号大于等于这个值时开始判断是否进入报警；必须大于exit_threshold。例如80。|
|exit_threshold|数值|是|无|设置解除报警的低阈值；按恢复规范填写，使用parameters.unit的单位。已经报警后，信号小于等于这个值时开始判断是否解除；例如75。位于75和80之间时沿用此前状态。|
|enter_delay|时长字符串|否|`"0ns"`|设置进入报警前的连续确认时间；按抗抖动要求填写。大于等于0。进入条件连续保持多久才确认报警；0表示条件成立就确认。|
|exit_delay|时长字符串|否|`"0ns"`|设置解除报警前的连续确认时间；按恢复稳定时间要求填写。大于等于0。解除条件连续保持多久才确认解除；0表示条件成立就解除。|

所有数值阈值都须是有限数值，不能填NaN或Infinity。时长可使用`ns/us/ms/s`，例如`"200ms"`；完整写法见[配置约定](configuration.md)。

<a id="preset-role-requirements"></a>
## 各角色的要求

下表每个角色的值都是**字符串形式的信号名**，例如YAML写法`current: pack_current`。这些不是额外输入列，而是在选择已经声明的信号。

|预设|角色字段|何时需要|信号必须满足的要求|省略映射时用于查找的semantic_id|
|---|---|---|---|---|
|charge_session|mode|始终需要|dtype为`int64`或`uint64`，unit为`"1"`|`battery.mode`|
|charge_session|current|始终需要|dtype为`float64`，unit为`"A"`，sign_convention为`"positive_is_charge"`，measurement_location为`"pack_terminal"`|`battery.current`|
|charge_session|voltage|compute_energy为true时需要；如果主动写了映射，也会检查它|dtype为`float64`，unit为`"V"`，measurement_location为`"pack_terminal"`|`battery.voltage`|
|fault_context|alarm|始终需要|dtype为`bool`，unit为`"1"`|`fault.alarm`|
|command_response|request|始终需要|dtype为`bool`，unit为`"1"`|`command.request`|
|command_response|response|始终需要|dtype为`bool`，unit为`"1"`|`command.response`|
|threshold_excursion|signal|必须明确写映射，不能省略|dtype为`int64`、`uint64`或`float64`，unit等于parameters.unit|不自动查找|

自动查找还要求信号的`semantic_contract_version`为字符串`"1"`。明确写映射时无需这两个semantic字段，但仍检查类型、单位等要求。所有角色信号必须能够确定正有效期，并使用`backward_hold`。有效期优先取显式`valid_for`，省略时取当前信号`period`或所属DBC报文周期的3倍；各角色独立计算，不借用驱动信号的周期。需要保持旧值却没有可用周期时必须补充声明。其作用是：新样本到来前沿用最近的有效值，但超过valid_for就视为缺失。质量检查会排除缺失、非有限、越界等异常样本，不能通过预设跳过这些检查。

`positive_is_charge`表示正电流是充电方向；`pack_terminal`表示在电池包端测量。如果设备用负电流表示充电，应先明确预处理成充电为正的新输入，再绑定转换后的列并声明positive_is_charge。当前公开signals的A→A、scale=-1会被单位检查拒绝；不能通过只改sign_convention反号。见[换算边界](signals.md#signal-conversion)。填写这些字段也不能替代实际接线、单位和标定核对。

## 业务声明：何时填写，如何取得

先选择使用方式，再决定是否需要`semantic_id`和`semantic_contract_version`。这些字段不能代替类型、单位、测点或正负方向的实际核对。

| 使用方式 | semantic_id | semantic_contract_version | 其他要求 |
|---|---|---|---|
| 普通规则与计算 | 可省略 | 可省略 | 表达式只引用name |
| 预设明确填写role_bindings | 可省略 | 可省略 | 仍满足上表对应角色的类型、单位、方向、位置和有效期要求 |
| 预设省略某个角色，由程序查找 | 填上表该角色规定的字符串，如command.request | 填字符串`"1"`，来自本版角色约定 | 在signals中必须恰有一条候选同时满足所有条件；0条或多条合格候选均报PlanValidationError |
| threshold_excursion | 不用它寻找角色 | 不用它寻找角色 | signal角色必须显式指定 |

例如扩展请求响应配置在request信号上增加`semantic_id: command.request`和`semantic_contract_version: "1"`，response信号对应填`command.response`和`"1"`。它们表示按本页第1版请求/响应角色规则使用这两条信号；不是给整个分析文件升级版本。整个文件仍写`config_version: 3`，预设实例省略version时采用`"1"`，三者控制不同对象。

原始绑定`signals`中的可选业务文本可以省略或填null；若提供semantic_contract_version必须同时提供semantic_id。`derived`中的可选业务文本应省略或填非空文本，不能填null。派生结果的这些声明用于描述和追溯，不会使其成为本版预设的角色候选；显式绑定也只在signals中选择。具体派生字段见[表达式](expressions.md)。

## 请求响应

应用位置：以[electrical-base.yaml](examples/electrical-base.yaml)为基础，在文件根级加入或替换`presets`，代码已包含父键。存在同名列表时按本例替换该列表，不把父键再嵌入列表项。

```yaml
presets:                             # 选择预先组合好的规则与计算，并提供角色信号和业务参数
  - name: cmd                        # 给本次预设实例取唯一名称；展开的规则/计算名称使用此前缀
    role_bindings:                   # 明确指定哪条已有信号担任每个角色；角色名由预设定义
      request: request               # 为request角色选择上方已定义的分析信号名；仍须符合该角色要求
      response: response             # 为response角色选择上方已定义的分析信号名；仍须符合该角色要求
    parameters:                      # 提供本预设的业务参数；各预设支持的字段不同，不能互相套用
      max_delay: 2s                  # 设置请求到响应的最大允许延迟；必须不小于最小延迟
    preset_type: command_response    # 选择业务任务；charge_session充电、fault_context报警上下文、command_response配对、threshold_excursion阈值
```

会生成`cmd_request`、`cmd_response`两条上升沿和`cmd_pair`配对。设置`emit_initial=true`同时允许两端初始为真时产生点；不要重复写同ID普通规则。配对结果和缺失处理见[请求响应](sequences.md)。

## 阈值报警和总持续时间

应用位置：以[electrical-base.yaml](examples/electrical-base.yaml)为基础，在文件根级加入或替换`presets`，代码已包含父键。存在同名列表时按本例替换该列表，不把父键再嵌入列表项。

```yaml
presets:                                # 选择预先组合好的规则与计算，并提供角色信号和业务参数
  - name: hot                           # 给本次预设实例取唯一名称；展开的规则/计算名称使用此前缀
    role_bindings:                      # 明确指定哪条已有信号担任每个角色；角色名由预设定义
      signal: temperature               # 为signal角色选择上方已定义的分析信号名；仍须符合该角色要求
    parameters:                         # 提供本预设的业务参数；各预设支持的字段不同，不能互相套用
      enter_threshold: 80               # 设置进入报警的高阈值；必须大于恢复阈值
      exit_threshold: 75                # 设置恢复的低阈值；按业务允许恢复范围填写
    preset_type: threshold_excursion    # 选择业务任务；charge_session充电、fault_context报警上下文、command_response配对、threshold_excursion阈值
```

固定使用“值≥80进入，值≤75退出”；进入阈值必须严格大于退出阈值。不能用此预设直接表示“过低报警”，那种需求应写自己的hysteresis条件。例子的温度单位degC在本版作为相同原单位使用，输入单位必须也是degC，不能同时做比例、偏移或方向转换后宣称已核实换算。

生成`hot_activity`和`hot_duration`。逐段时长通过`iter_calculations()`读取；总时长在`result.metadata.threshold_durations`，发布后在`run_manifest.json`的`run.threshold_durations`。当前公开摘要用value和unit表示时长，unit固定为s；不会同时提供纳秒字段。

|观测情况|总时长结果|为什么|
|---|---|---|
|85持续3秒，77持续6秒，75后解除|9秒，complete|完整知道哪段在报警|
|两次报警2秒和4秒，中间正常且数据完整|6秒，complete|分别相加，中间不计|
|全程已知不报警|0秒，complete|确实观测到没有报警|
|最初3秒只有77，随后85持续到9秒|value=6，unit=s，status=partial；只代表已知报警部分|最初3秒不知之前是否已进入报警|
|只有77，始终无法确定此前状态|None，indeterminate|不能把未知当作零|
|没有有效观测时段，例如只有一个孤立时间点|None，no_observation|没有可统计的时间长度|

例如实际观测了9秒：前3秒无法判断是否报警，后6秒确定在报警。当前公开摘要包含以下五个字段：

|字段|本例的值|含义|
|---|---|---|
|preset_id|hot|产生摘要的预设实例名称。|
|rule_id|hot_activity|该预设生成的活动规则名称。|
|value|6.0|可确定的累计报警秒数；不是全9秒内的完整总时长。|
|unit|s|value的单位，固定为秒。|
|status|partial|部分时段无法判断，读取value时必须同时保留此状态。|

普通计算项的partial_policy与这个预设摘要是两个不同接口；不能把底层详细时长模型中的known_active_duration_ns等字段当作当前公开摘要字段。完整可运行例见[preset-threshold-partial.yaml](examples/preset-threshold-partial.yaml)：第0～1秒温度77无法判断先前报警状态，第1～3秒已知报警，故value=2.0、status=partial。

等待确认也可能造成初始状态未知。例如[preset-threshold-delay.yaml](examples/preset-threshold-delay.yaml)的exit_delay为500ms：第0秒首次看到70°C，需到0.5秒才确认未报警；第1.5～3.5秒的活动完整，逐活动时长为2s/complete，但整个会话的累计摘要为2s/partial，因为最初0.5秒尚未确认状态。两处status描述的统计范围不同，不能相互替代。

摘要描述的是实际观测到的时间。若请求到12秒但日志只到9秒，还须查看运行清单中的观测范围；这个摘要不能证明第9～12秒没有报警。

## 充电与故障前后文

充电预设的条件是模式匹配且电流严格大于声明门槛，持续到指定时间后确认活动。例如下列片段要求模式1、电流大于5A、持续3秒，并按电压×电流计算能量：

应用位置：以[electrical-base.yaml](examples/electrical-base.yaml)为基础，在文件根级加入或替换`presets`，代码已包含父键。存在同名列表时按本例替换该列表，不把父键再嵌入列表项。

```yaml
presets:                           # 选择预先组合好的规则与计算，并提供角色信号和业务参数
  - name: charge                   # 给本次预设实例取唯一名称；展开的规则/计算名称使用此前缀
    role_bindings:                 # 明确指定哪条已有信号担任每个角色；角色名由预设定义
      mode: mode                   # 为mode角色选择上方已定义的分析信号名；仍须符合该角色要求
      current: current             # 为current角色选择上方已定义的分析信号名；仍须符合该角色要求
      voltage: voltage             # 为voltage角色选择上方已定义的分析信号名；仍须符合该角色要求
    parameters:                    # 提供本预设的业务参数；各预设支持的字段不同，不能互相套用
      mode_value: 1                # 指定表示充电的模式代码；从设备状态编码表取得
      current_min: 5               # 设置充电判断的电流下限；按业务目标填写，单位A
      minimum_duration: 3s         # 设置充电条件连续成立多久才确认；按业务要求填写
      compute_energy: true         # 选择是否计算充电能量；true需要电压角色，false不生成能量项
    preset_type: charge_session    # 选择业务任务；charge_session充电、fault_context报警上下文、command_response配对、threshold_excursion阈值
```

`fault_context`用于查看故障刚出现前后的数据。例如故障在第10秒出现，pre填2s、post填3s，就取第8秒到第13秒的数据。日志没有覆盖完整范围时，结果会说明实际取到了哪部分。

它不会计算故障持续了多久。如果需要记录整段报警，应使用condition_duration或hysteresis规则。

完整类型、构建函数与生成字段见[presets](reference/chronaxis.presets.md)和[preset_models](reference/chronaxis.planning.preset_models.md)。全部可运行输入见[示例](examples.md)。
