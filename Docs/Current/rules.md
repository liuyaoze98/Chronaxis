# 事件检测规则

规则把信号值变成事件。**点事件**只有发生时刻，例如按钮从松开变成按下；**活动事件**有开始、结束和持续时间，例如温度报警持续了9秒。规则写在`rules`数组里；它们的`name`由你命名，窗口和计算项通过这个名字找到事件。

本页未另行说明的秒数例子采用默认actual。配置intervals为fixed或dbc时，持续确认、等待到期、变化窗口和配对delay_ns使用所选周期依据；原时间坐标和信号到期仍按实际记录时间。先看[三种时间依据对照](intervals.md#timing-basis)。

## 规则类型选择

所有规则都必须有[`name`](#rule-id)和[`rule_type`](#rule-rule_type)。先按最右列选择规则，再点击字段名查看本页的填写说明。字段详情把类型、必填、默认值和各取值的含义分开列出。必填字段没有默认值，漏填会报错；可选字段省略时使用表中的默认值。未列出的字段会被拒绝。

|rule_type|必填字段|可选字段及默认值|适合的问题|
|---|---|---|---|
|[`condition_duration`](#rule-duration)|[`condition`](#duration-condition)、[`minimum_duration`](#duration-duration)|[`selection_origin="onset"`](#duration-selection-origin)|条件连续成立至少3秒后，记录这段活动|
|[`rising_edge`](#rule-rising_edge)|[`condition`](#rising_edge-condition)|[`emit_initial=false`](#rising_edge-emit-initial)|按钮由松开变成按下时记一个点|
|[`falling_edge`](#rule-falling_edge)|[`condition`](#falling_edge-condition)|[`emit_initial=false`](#falling_edge-emit-initial)，不允许true|按钮由按下变成松开时记一个点|
|[`start_only`](#rule-start-only)|[`condition`](#start-only-condition)、[`window_duration`](#start-only-window-duration)|[`emit_initial=false`](#start-only-emit-initial)|触发后取固定5秒，这5秒内不重复触发|
|[`debounce`](#rule-debounce)|[`condition`](#debounce-condition)|[`enter_delay="0s"`](#debounce-enter-delay)、[`exit_delay="0s"`](#debounce-exit-delay)|忽略短暂的真/假跳变，确认后才改变活动状态|
|[`hysteresis`](#rule-hysteresis)|[`enter_condition`](#hysteresis-enter-condition)、[`exit_condition`](#hysteresis-exit-condition)|[`enter_delay="0s"`](#hysteresis-enter-delay)、[`exit_delay="0s"`](#hysteresis-exit-delay)|温度达到80进入报警，降到75退出，中间保持原状态|
|[`start_end`](#rule-start-end)|[`start_condition`](#start-end-start-condition)、[`end_condition`](#start-end-end-condition)|[`timeout=null`](#start-end-timeout)、[`emit_initial=true`](#start-end-emit-initial)|开始信号启动，结束信号停止；填写timeout可限制最长等待|
|[`window_delta`](#rule-window-delta)|[`signal`](#window-delta-signal)、[`window`](#window-delta-window)、[`direction`](#window-delta-direction)、[`threshold`](#window-delta-threshold)|[`monotonic=false`](#window-delta-monotonic)、[`coverage_policy="full"`](#window-delta-coverage-policy)、[`emit_initial=false`](#window-delta-emit-initial)、[`retrigger="edge"`](#window-delta-retrigger)|最近4秒电压升了至少5V时记一个点|

## 每种规则的完整案例

每个文件都内含自己的合成数据、来源和信号，只保留当前功能需要的字段。直接运行`chronaxis run 文件名.yaml --output 新目录`。表中的时间都来自对应文件，不要求用后文共享教学数据猜结果。

| 功能 | 最小配置 | 扩展配置 | 独立预期 |
|---|---|---|---|
| condition_duration | [最小例](examples/rule-condition_duration-minimal.yaml) | [扩展例](examples/rule-condition_duration-extended.yaml) | 最小活动[1,6)，3秒确认；扩展只积分确认后的[3,6)，10W×3s=30J |
| rising_edge | [最小例](examples/rule-rising_edge-minimal.yaml) | [扩展例](examples/rule-rising_edge-extended.yaml) | 最小在1秒记点；扩展取[1,2)，得到10J |
| falling_edge | [最小例](examples/rule-falling_edge-minimal.yaml) | [扩展例](examples/rule-falling_edge-extended.yaml) | 最小在5秒记点；扩展取[5,6)，得到10J |
| start_only | [最小例](examples/rule-start_only-minimal.yaml) | [扩展例](examples/rule-start_only-extended.yaml) | 两者在1、6秒记点；扩展得到[1,6)和[6,11)片段，3秒触发被屏蔽 |
| debounce | [最小例](examples/rule-debounce-minimal.yaml) | [扩展例](examples/rule-debounce-extended.yaml) | 最小活动[1,5)；扩展等待进入2秒、退出3秒，活动[3,8) |
| hysteresis | [最小例](examples/rule-hysteresis-minimal.yaml) | [扩展例](examples/rule-hysteresis-extended.yaml) | 最小活动[1,6)；扩展进入/退出各等1秒，活动[2,7) |
| start_end | [最小例](examples/rule-start_end-minimal.yaml) | [扩展例](examples/rule-start_end-extended.yaml) | 最小正常活动[1,5)；扩展最多等2秒，于3秒超时，活动[1,3) |
| window_delta | [最小例](examples/rule-window_delta-minimal.yaml) | [扩展例](examples/rule-window_delta-extended.yaml) | 最小首个完整窗已满足但不发初始点，只在12秒触发；扩展开启初次触发和单调检查，在4、12秒触发 |

上述18个规则/派生案例的可复核脚本为[rule_examples.py](examples/rule_examples.py)。执行`python rule_examples.py --output 新目录`，脚本按独立预期检查事件起止、确认时刻、超时状态、片段和积分。

## 先准备来源和信号

保存[完整基础配置](examples/teaching-base.yaml)；它引用合成ASC报文和DBC，并声明下列信号；分析范围取全部实际观测。这里展示的是该文件根级signals的相关条目，用于解释后续引用；不需要再粘贴一遍。不同规则的小表是各自的概念对照，共享基础数据不保证产生每张小表的全部事件；有固定预期的完整任务使用各节专用配置。

基础文件已有的信号定义摘录：用于阅读，不重复插入；完整基础文件只有一个CAN来源，无需逐项重复source。信号的frame_id和signal来自随附DBC；类型与单位自动读取。此处显式保留20s有效期，保证稀疏教学记录之间仍有效，不代表实际设备的推荐设置。

```yaml
signals:                       # 把输入字段定义为有名称、类型、单位和有效期的分析信号
  - name: temperature          # 给分析信号取名称；后续表达式和计算通过此名称引用它
    field:                     # 指定来源中的原始字段；CSV填表头，CAN填写通道/报文ID/DBC信号名
      frame_id: '0x11d'        # 选择包含信号的报文ID；从对应DBC取得，可写整数或支持的进制文本
      signal: Temperature      # 填写DBC中的信号名称，大小写须一致
    valid_for: 20s             # 设置一次有效更新最多沿用多久；依据采样周期和允许数据陈旧程度填写
  - name: power                # 给分析信号取名称；后续表达式和计算通过此名称引用它
    field:                     # 指定来源中的原始字段；CSV填表头，CAN填写通道/报文ID/DBC信号名
      frame_id: '0x100'        # 选择包含信号的报文ID；从对应DBC取得，可写整数或支持的进制文本
      signal: Power            # 填写DBC中的信号名称，大小写须一致
    valid_for: 20s             # 设置一次有效更新最多沿用多久；依据采样周期和允许数据陈旧程度填写
  - name: voltage              # 给分析信号取名称；后续表达式和计算通过此名称引用它
    field:                     # 指定来源中的原始字段；CSV填表头，CAN填写通道/报文ID/DBC信号名
      frame_id: '0x11f'        # 选择包含信号的报文ID；从对应DBC取得，可写整数或支持的进制文本
      signal: Voltage          # 填写DBC中的信号名称，大小写须一致
    valid_for: 20s             # 设置一次有效更新最多沿用多久；依据采样周期和允许数据陈旧程度填写
  - name: button_pressed       # 给分析信号取名称；后续表达式和计算通过此名称引用它
    field:                     # 指定来源中的原始字段；CSV填表头，CAN填写通道/报文ID/DBC信号名
      frame_id: '0x113'        # 选择包含信号的报文ID；从对应DBC取得，可写整数或支持的进制文本
      signal: ButtonPressed    # 填写DBC中的信号名称，大小写须一致
    valid_for: 20s             # 设置一次有效更新最多沿用多久；依据采样周期和允许数据陈旧程度填写
    choices:                   # 把输入状态代码转成分析值；每项是[输入代码,结果值]，代码查设备规范
      - [0, false]
      - [1, true]
  - name: start_signal         # 给分析信号取名称；后续表达式和计算通过此名称引用它
    field:                     # 指定来源中的原始字段；CSV填表头，CAN填写通道/报文ID/DBC信号名
      frame_id: '0x11c'        # 选择包含信号的报文ID；从对应DBC取得，可写整数或支持的进制文本
      signal: StartSignal      # 填写DBC中的信号名称，大小写须一致
    valid_for: 20s             # 设置一次有效更新最多沿用多久；依据采样周期和允许数据陈旧程度填写
    choices:                   # 把输入状态代码转成分析值；每项是[输入代码,结果值]，代码查设备规范
      - [0, false]
      - [1, true]
  - name: end_signal           # 给分析信号取名称；后续表达式和计算通过此名称引用它
    field:                     # 指定来源中的原始字段；CSV填表头，CAN填写通道/报文ID/DBC信号名
      frame_id: '0x117'        # 选择包含信号的报文ID；从对应DBC取得，可写整数或支持的进制文本
      signal: EndSignal        # 填写DBC中的信号名称，大小写须一致
    valid_for: 20s             # 设置一次有效更新最多沿用多久；依据采样周期和允许数据陈旧程度填写
    choices:                   # 把输入状态代码转成分析值；每项是[输入代码,结果值]，代码查设备规范
      - [0, false]
      - [1, true]
```

## 所有规则共用的填写方式

本页主字段表相对于`rules[]`，例如`rules[].name`。子对象另行注明，表中的字段不能直接放到配置根级。

|字段|控制作用与效果|可填写的值|数据类型|必填/默认|取值依据|
|---|---|---|---|---|---|
|<a id="rule-id"></a>`name`|给规则起一个名字，供窗口和计算项引用。例如窗口写 `rule: hot`，就使用这条规则找到的活动。|例如 `"hot"`；名称规则见下文|字符串|是；无|由配置作者取唯一标识。|
|<a id="rule-rule_type"></a>`rule_type`|选择找事件的方法。各英文值的含义见上方“适合的问题”列。|上方选择表列出的事件规则名称|字符串|是；无|按本页规则选择表确定算法。|

规则名称用英文字母或下划线开头，后面可用英文字母、数字或下划线，例如hot_1；不使用Python关键字、abs、isclose。同一计划内，规则、窗口、计算项的name不能重复。

需要计时的规则可在自身interval对象中选择时间依据，省略时继承intervals.default；纯上升沿和下降沿不接受interval。详见[计算间隔](intervals.md)。

“条件”是一个判断，例如`"temperature >= 80"`。其中`temperature`必须是你已经在`signals`或`derived`中定义的名字；完整运算符见[表达式](expressions.md)。数值信号要写比较式，不能只填`"temperature"`；已经声明为`bool`的信号可以直接填`"button_pressed"`。条件的计算结果有三种：真（成立）、假（不成立）、未知（缺值、值过期或无法计算）。**未知不等于假**；未知→真不能证明此前发生过假→真的变化。

下面所有例子都是合成数据，温度用`degC`、电压用`V`，开关信号为`bool`。未单独说明缺失时，假定信号在相邻记录之间仍有效，且观测持续到例子末尾；实际文件的有效期由信号`valid_for`决定。每个代码块之前单独标明基础文件和替换位置；不要将包含rules父键的片段再塞入rules列表。

时长是带单位的字符串，支持`ns`（纳秒）、`us`（微秒）、`ms`（毫秒）、`s`（秒），例如`"500ms"`、`"2s"`。不能写无单位的数字`2`，一分钟要写`"60s"`而不是`"1min"`。“非负”允许`"0s"`；“正时长”要求大于0。内部精度为整数纳秒，正时长换算后也必须至少为1纳秒。Python底层类型化对象中的`*_ns`字段填整数纳秒，例如2秒是2,000,000,000ns；本页配置使用YAML；`true/false/null`是布尔值与空值，Python对象中分别写`True/False/None`。字符串内的表达式另按表达式语法解释，见[配置语言](configuration-language.md)。

<a id="rule-duration"></a>
## 持续条件检测：condition_duration

例如只记录“温度达到80且连续保持2秒”的过程：

应用位置：以[teaching-base.yaml](examples/teaching-base.yaml)为基础，在文件根级加入或替换`rules`，代码已包含父键。存在同名列表时按本例替换该列表，不把父键再嵌入列表项。

```yaml
rules:                               # 列出识别活动或瞬间变化的规则；每项产生有独立ID的事件
  - name: hot                        # 为规则取唯一名称；窗口rule和计算scope通过此名选择它的事件
    condition: temperature >= 80     # 填写由已定义信号组成的真假条件；按要检测的业务情况设置
    minimum_duration: 2s             # 设置条件连续成立多久才确认活动；时长阈值由业务要求决定
    rule_type: condition_duration    # 选择活动或变化识别算法；本例条件连续成立达到minimum_duration后确认活动
```

|字段|控制作用与效果|可填写的值|数据类型|必填/默认|取值依据|
|---|---|---|---|---|---|
|<a id="duration-condition"></a>`condition`|要检查的条件。本例表示温度达到80时条件成立；低于80时不成立。|能计算出真或假的表达式，例如 `"temperature >= 80"`|字符串|是；无|用已定义信号名，按业务判断要求组合表达式。|
|<a id="duration-duration"></a>`minimum_duration`|条件连续成立这么久，才把这次过程记为一次活动。填 `"2s"` 时，持续1.9秒的过程不会被记录；填 `"0s"` 时无需等待。|大于或等于0，例如 `"2s"`|时长字符串|是；无|由业务规定连续成立的最短时间。|
|`duration_comparison`|持续时长与minimum_duration的比较。`>=`表示达到，`>`表示严格超过。60秒整只符合前者，60.000000001秒符合两者。|`>=`、`>`|字符串|否；`>=`|需求写“超过”时填`">"`；不要把60秒改为60.1秒。|
|<a id="duration-selection-origin"></a>`selection_origin`|计算每次活动的时长、平均值或积分时，选择是否计入确认前的等待时间。|`"onset"` 或 `"confirmed"`；逐项解释见下方|字符串|否；`"onset"`|按统计是否包含等待确认时间选择。|

### selection_origin：事件计算的起点

假设你想统计“温度达到80并保持至少2秒”的活动。日志记录如下：

|时刻|发生的事情|
|---|---|
|第1秒|温度达到80，开始等待，看它能否保持2秒。|
|第3秒|温度已连续2秒不低于80，这次过程达到记录要求。这个时刻叫**确认时间**。|
|第6秒|温度降到80以下，这次活动结束。|

现在要计算这次活动持续多久、消耗多少能量。前面等待确认的2秒要不要算进去，就由 `selection_origin` 决定：

|填写的值|中文含义|本例统计哪段时间|若这段时间功率始终为10W|
|---|---|---|---|
|`"onset"`|从条件开始成立时算起，包含等待确认的时间。|第1秒到第6秒，共5秒。|能量为10×5＝50J。|
|`"confirmed"`|从确认这次活动时算起，不包含等待确认的时间。|第3秒到第6秒，共3秒。|能量为10×3＝30J。|

这是可选的字符串字段，省略时为onset。YAML写法为`selection_origin: confirmed`。它改变事件内的计算起点，不改变事件确认条件。

下面把规则和能量计算项写在一起。`scope` 的 `{rule: hot}` 表示“对hot规则找到的每一次活动分别计算”；`power`是事先定义好的功率信号，单位为W。

应用位置：以[teaching-base.yaml](examples/teaching-base.yaml)为基础，在文件根级加入或替换`rules, calculations`，代码已包含父键。存在同名列表时按本例替换该列表，不把父键再嵌入列表项。

```yaml
rules:                               # 列出识别活动或瞬间变化的规则；每项产生有独立ID的事件
  - name: hot                        # 为规则取唯一名称；窗口rule和计算scope通过此名选择它的事件
    condition: temperature >= 80     # 填写由已定义信号组成的真假条件；按要检测的业务情况设置
    selection_origin: confirmed      # 选择活动计算起点；onset包含确认前等待，confirmed从确认时刻起算
    minimum_duration: 2s             # 设置条件连续成立多久才确认活动；时长阈值由业务要求决定
    rule_type: condition_duration    # 选择活动或变化识别算法；本例条件连续成立达到minimum_duration后确认活动
calculations:                        # 列出希望获得的统计或积分结果，每项独立选择范围和算法
  - name: hot_energy                 # 为这项计算结果取唯一名称；结果表用它区分计算项
    expr: power                      # 指定参与计算的数值或信号表达式；引用前面已定义的信号
    operation: integral              # 选择计算方法；本例将有效数值乘持续时间后累计，例如功率乘秒得到能量
    scope:                           # 选择计算范围；session整段会话，{rule: 名称}逐事件，{window: 名称}逐片段
      rule: hot                      # 按指定规则的每次事件分别计算；填写前面rules中的name
```

按上面的数据，这段配置得到30J。把 `"confirmed"` 改成 `"onset"`，得到50J；活动是否达到“至少2秒”的要求并没有变化。

如果还想分析活动开始前、结束后各1秒的数据，可以围绕这次活动另设一个窗口。本例活动从第1秒持续到第6秒，窗口就是第0秒到第7秒。

**`selection_origin` 不改变这个窗口的范围。** 无论填写 `"onset"` 还是 `"confirmed"`，这个窗口都保持不变。具体配置见[活动前后各取1秒并计算能量](windows.md#activity-context-example)。

**如果恰好保持2秒就结束呢？** 第1秒温度达到80，第3秒降到80以下，这次活动仍会被记录。

填 `"onset"` 时，计算第1秒到第3秒的数据。填 `"confirmed"` 时，确认和结束都在第3秒，没有可供统计的持续时间；时间计算会返回空值，并说明统计范围长度为0。

已确认的活动遇到条件为假时正常结束；遇到缺值或过期时以“数据中断”结束；日志结束时条件仍成立，则记录为“观测结束，活动是否结束尚不确定”。

<a id="rule-rising_edge"></a>
## 上升沿检测：rising_edge

应用位置：以[teaching-base.yaml](examples/teaching-base.yaml)为基础，在文件根级加入或替换`rules`，代码已包含父键。存在同名列表时按本例替换该列表，不把父键再嵌入列表项。

```yaml
rules:                           # 列出识别活动或瞬间变化的规则；每项产生有独立ID的事件
  - name: pressed                # 为规则取唯一名称；窗口rule和计算scope通过此名选择它的事件
    condition: button_pressed    # 填写由已定义信号组成的真假条件；按要检测的业务情况设置
    rule_type: rising_edge       # 选择活动或变化识别算法；本例condition由false变为true时产生瞬时事件
```

|字段|控制作用与效果|可填写的值|数据类型|必填/默认|取值依据|
|---|---|---|---|---|---|
|<a id="rising_edge-condition"></a>`condition`|例如 `"button_pressed"` 表示按钮是否按下；程序记录它从假变真的时刻。|布尔信号名或条件表达式|字符串|是；无|用已定义信号名，按业务判断要求组合表达式。|
|<a id="rising_edge-emit-initial"></a>`emit_initial`|日志开始时按钮可能已经按下。这个选项决定是否把首次读到的已知真值记为初始事件；后续数据缺失再恢复，不会再次按初始事件处理。|`false`：初始为真时不记点；`true`：初始为真时记一个点|布尔值|否；`false`|按是否接受日志开始前已存在的状态选择；各规则允许值不同。|

按钮0秒为假、1秒为真、2秒仍为真、3秒为假、4秒为真，得到1秒和4秒两个点。若最先读到的0秒就是真，只有`emit_initial=true`才在0秒记点。没有数据→真不算观察到了按下动作；按钮全程为真也不会每条记录都产生点。

<a id="rule-falling_edge"></a>
## 下降沿检测：falling_edge

应用位置：以[teaching-base.yaml](examples/teaching-base.yaml)为基础，在文件根级加入或替换`rules`，代码已包含父键。存在同名列表时按本例替换该列表，不把父键再嵌入列表项。

```yaml
rules:                           # 列出识别活动或瞬间变化的规则；每项产生有独立ID的事件
  - name: released               # 为规则取唯一名称；窗口rule和计算scope通过此名选择它的事件
    condition: button_pressed    # 填写由已定义信号组成的真假条件；按要检测的业务情况设置
    rule_type: falling_edge      # 选择活动或变化识别算法；本例condition由true变为false时产生瞬时事件
```

|字段|控制作用与效果|可填写的值|数据类型|必填/默认|取值依据|
|---|---|---|---|---|---|
|<a id="falling_edge-condition"></a>`condition`|例如 `"button_pressed"` 表示按钮是否按下；程序记录它从真变假的时刻，也就是按钮松开的时刻。|布尔信号名或条件表达式|字符串|是；无|用已定义信号名，按业务判断要求组合表达式。|
|<a id="falling_edge-emit-initial"></a>`emit_initial`|首次读到按钮未按下，无法判断它是否刚刚被松开，因此不生成下降沿事件。|当前填写 `false`，也可以省略；填 `true` 会报配置错误|布尔值|否；`false`|按是否接受日志开始前已存在的状态选择；各规则允许值不同。|

使用上一节0～4秒的按钮记录，只在3秒产生点。未知→假不会产生下降沿点，初始为真也不会产生点。

<a id="rule-start-only"></a>
## 带重复触发屏蔽的起点检测：start_only

应用位置：以[teaching-base.yaml](examples/teaching-base.yaml)为基础，在文件根级加入或替换`rules`，代码已包含父键。存在同名列表时按本例替换该列表，不把父键再嵌入列表项。

```yaml
rules:                           # 列出识别活动或瞬间变化的规则；每项产生有独立ID的事件
  - name: capture                # 为规则取唯一名称；窗口rule和计算scope通过此名选择它的事件
    condition: button_pressed    # 填写由已定义信号组成的真假条件；按要检测的业务情况设置
    window_duration: 5s          # 设置start_only一次触发后抑制新触发的时长；配套窗口post必须与此值相等
    rule_type: start_only        # 选择活动或变化识别算法；本例开始条件触发后，在window_duration内抑制重复触发
```

|字段|控制作用与效果|可填写的值|数据类型|必填/默认|取值依据|
|---|---|---|---|---|---|
|<a id="start-only-condition"></a>`condition`|条件从假变真时触发一次；如果还处于上次触发后的屏蔽时间内，本次触发就被忽略。|布尔信号名或条件表达式|字符串|是；无|用已定义信号名，按业务判断要求组合表达式。|
|<a id="start-only-window-duration"></a>`window_duration`|一次触发后，接下来多长时间不再接受新触发。1秒触发、填写5秒时，1秒至6秒之间的新触发被忽略；恰好6秒的新触发可以接受。|大于0，例如 `"5s"`|时长字符串|是；无|按一次采集需要屏蔽重复触发的时长填写。|
|<a id="start-only-emit-initial"></a>`emit_initial`|决定首次读到的已知真值是否启动一次固定窗口。之后仍须等到新的假到真变化，不能因为条件一直为真而重复触发。|`false`：初始为真不触发；`true`：初始为真也触发一次|布尔值|否；`false`|按是否接受日志开始前已存在的状态选择；各规则允许值不同。|

例如按钮在1、3、6秒各出现一次假→真，得到1秒和6秒两个点，3秒被忽略，不会留到6秒补发。若1秒后一直为真，6秒到期也不会自动再触发。

要取出两段时间，还需显式配窗口；规则本身只输出触发点：

应用位置：以[teaching-base.yaml](examples/teaching-base.yaml)为基础，在文件根级加入或替换`windows`，代码已包含父键。存在同名列表时按本例替换该列表，不把父键再嵌入列表项。 依赖：代码中的rule为capture时先加入上方start_only规则；rule为alarm时先加入hysteresis规则。保留该依赖规则，再加入本块的windows/calculations。

```yaml
windows:                  # 围绕已定义规则的事件选取时间片段，供计算或导出使用
  - name: capture_data    # 为窗口定义取唯一名称；计算或导出通过此名选择产生的片段
    rule: capture         # 选择生成窗口的事件规则；填写前面rules中的name
```

这段包含根级windows字段，保留上方capture规则后替换同名字段。省略`post`时自动沿用规则的`window_duration`；显式填写也须与它相等。本例得到`[1,6)`和`[6,11)`；`pre`可另外指定向前取多少数据。字段逐项见[窗口字段](windows.md#window-fields)。

<a id="rule-debounce"></a>
## 去抖动活动检测：debounce

应用位置：以[teaching-base.yaml](examples/teaching-base.yaml)为基础，在文件根级加入或替换`rules`，代码已包含父键。存在同名列表时按本例替换该列表，不把父键再嵌入列表项。

```yaml
rules:                           # 列出识别活动或瞬间变化的规则；每项产生有独立ID的事件
  - name: stable_pressed         # 为规则取唯一名称；窗口rule和计算scope通过此名选择它的事件
    condition: button_pressed    # 填写由已定义信号组成的真假条件；按要检测的业务情况设置
    enter_delay: 2s              # 设置进入条件需连续成立的等待时间；0s表示不额外等待
    exit_delay: 3s               # 设置退出条件需连续成立的等待时间；0s表示不额外等待
    rule_type: debounce          # 选择活动或变化识别算法；本例进入和退出条件各需保持指定时长才确认状态变化
```

|字段|控制作用与效果|可填写的值|数据类型|必填/默认|取值依据|
|---|---|---|---|---|---|
|<a id="debounce-condition"></a>`condition`|条件为真时准备进入活动，为假时准备退出；实际改变状态前还要等满下面设置的时间。|布尔信号名或条件表达式|字符串|是；无|用已定义信号名，按业务判断要求组合表达式。|
|<a id="debounce-enter-delay"></a>`enter_delay`|条件连续为真多久才开始活动。1秒变真，填2秒时活动从3秒开始。等待期间变假，本次等待取消。0秒表示立即开始。|大于或等于0，例如 `"2s"`|时长字符串|否；`"0s"`|按进入状态前需要排除的短暂波动时长填写。|
|<a id="debounce-exit-delay"></a>`exit_delay`|条件连续为假多久才结束活动。5秒变假，填3秒时活动到8秒结束，这3秒仍计入活动。等待期间变真，就取消退出等待。0秒表示立即结束。|大于或等于0，例如 `"3s"`|时长字符串|否；`"0s"`|按恢复状态需要持续稳定的时间填写。|

用同一组按钮记录看完整过程：

|时刻|按钮状态|程序怎样处理|
|---|---|---|
|第1秒|按下|开始等待，尚未记录活动。|
|第3秒|仍按下|已稳定2秒，从此刻开始活动。|
|第5秒|松开|开始等待退出，活动暂时继续。|
|第8秒|仍松开|已稳定3秒，活动在此刻结束。|

因此记录的活动是第3秒到第8秒，共5秒。开始前等待的2秒不计入活动；结束前等待的3秒计入活动。这也是它与前面 `condition_duration` 规则的区别。

如果第1.5秒就松开，按下不足2秒，不会开始活动。如果第6秒又按下，松开不足3秒，活动继续。数据缺失或过期则会中断判断，恢复后重新等待，不能把缺失时间算成“已经稳定”。

<a id="rule-hysteresis"></a>
## 迟滞活动检测：hysteresis

如果用80同时作为开始和解除报警的门槛，温度在80附近波动时，报警可能反复开关。可以改成：达到80才报警，降到75才解除。已经报警时读到77就继续报警，尚未报警时读到77就继续不报警。这种做法称为**迟滞**。

应用位置：以[teaching-base.yaml](examples/teaching-base.yaml)为基础，在文件根级加入或替换`rules`，代码已包含父键。存在同名列表时按本例替换该列表，不把父键再嵌入列表项。

```yaml
rules:                                    # 列出识别活动或瞬间变化的规则；每项产生有独立ID的事件
  - name: alarm                           # 为规则取唯一名称；窗口rule和计算scope通过此名选择它的事件
    enter_condition: temperature >= 80    # 设置进入活动的条件；与退出条件分别判断
    exit_condition: temperature <= 75     # 设置退出活动的条件；按恢复要求填写
    rule_type: hysteresis                 # 选择活动或变化识别算法；本例分别用进入和退出条件判断活动，避免一个阈值附近反复切换
```

|字段|控制作用与效果|可填写的值|数据类型|必填/默认|取值依据|
|---|---|---|---|---|---|
|<a id="hysteresis-enter-condition"></a>`enter_condition`|开始活动所需的条件。例如温度达到80才开始报警；如果设置了enter_delay，还须持续满足指定时间。|条件表达式，例如 `"temperature >= 80"`|字符串|是；无|根据进入报警的门槛填写，使用已定义信号名及其单位。|
|<a id="hysteresis-exit-condition"></a>`exit_condition`|结束活动所需的条件。例如温度降到75或以下才解除报警；温度在75和80之间时，保持此前已知的状态。|条件表达式，例如 `"temperature <= 75"`|字符串|是；无|根据解除报警的门槛填写，不与进入条件同时成立。|
|<a id="hysteresis-enter-delay"></a>`enter_delay`|进入条件连续成立多久才开始活动。温度达到80并持续2秒才报警；等满前降到77，本次等待取消。|大于或等于0，例如 `"2s"`|时长字符串|否；`"0s"`|按进入状态前需要排除的短暂波动时长填写。|
|<a id="hysteresis-exit-delay"></a>`exit_delay`|退出条件连续成立多久才结束活动。温度不高于75并持续3秒才解除报警；等满前回到77，本次等待取消，继续报警。|大于或等于0，例如 `"3s"`|时长字符串|否；`"0s"`|按恢复状态需要持续稳定的时间填写。|

|时间|温度|报警状态及原因|
|---|---|---|
|0秒|85|达到进入条件，开始报警|
|3秒|77|两个条件都不成立，沿用报警状态|
|6秒|77|仍在报警；即使这一点来自下一份连续文件也不重置|
|9秒|75|达到退出条件，结束报警|
|12秒|70|没有报警|

结果是一段`[0,9)`活动，持续9秒。方括号表示包含0秒，圆括号表示不包含9秒；9秒的75已经是退出后的值。窗口内温度均值是`(85×3 + 77×6)/9 = 239/3`。

如果记录的第一个值就是77，程序不知道此前是否曾超过80，状态为**未知**。如果报警期间数据过期或缺失，活动会中断；恢复后仍是77也不能假定报警继续。两个条件同时为真会报错，不能配置成重叠范围后期待程序替你选优先级。两个条件中的任意一个无法计算，也会使状态未知。

`debounce`相当于进入条件为`condition`、退出条件为`not condition`的稳定等待。它和迟滞均不接受`duration`、`emit_initial`。本例的温度单位`degC`是明确的原值标签；本版不会把它自动换成K。

<a id="rule-start-end"></a>
## 开始结束活动检测：start_end

应用位置：以[teaching-base.yaml](examples/teaching-base.yaml)为基础，在文件根级加入或替换`rules`，代码已包含父键。存在同名列表时按本例替换该列表，不把父键再嵌入列表项。

```yaml
rules:                               # 列出识别活动或瞬间变化的规则；每项产生有独立ID的事件
  - name: cycle                      # 为规则取唯一名称；窗口rule和计算scope通过此名选择它的事件
    start_condition: start_signal    # 设置开始活动的条件；引用上方定义的信号
    end_condition: end_signal        # 设置结束活动的条件；引用上方定义的信号
    timeout: 5s                      # 限制一次活动的最长等待/持续时间；达到上限按规则结束
    rule_type: start_end             # 选择活动或变化识别算法；本例start_condition开始活动，end_condition或timeout结束活动
```

|字段|控制作用与效果|可填写的值|数据类型|必填/默认|取值依据|
|---|---|---|---|---|---|
|<a id="start-end-start-condition"></a>`start_condition`|从假变真时开始一次活动。例如 `"start_signal"` 表示开始开关；首次读到的值为真时怎样处理，由emit_initial决定。|布尔信号名或条件表达式|字符串|是；无|根据启动动作对应的信号/条件填写。|
|<a id="start-end-end-condition"></a>`end_condition`|活动开始后，这个条件为真就结束活动，不必再等待它从假变真。开始时结束条件已经为真，则不输出零时长活动。|布尔信号名或条件表达式|字符串|是；无|根据结束状态对应的信号/条件填写。|
|<a id="start-end-timeout"></a>`timeout`|例如填 `"5s"`，4秒开始的活动最晚在9秒结束。日志提前结束或结束信号缺失时，不能凭没有响应就认定超时。0秒不是“不限时”的写法。|正时长：设置最长持续时间；`null`：不设置上限|时长字符串或空值|否；`null`|按业务允许的最长活动时间填写；不需上限则省略或null。|
|<a id="start-end-emit-initial"></a>`emit_initial`|决定日志中第一个已知开始状态为真时，是否开始活动。这个规则的默认值为true，与rising_edge不同。|`true`：初始开始条件为真就启动；`false`：等待后续从假变真|布尔值|否；`true`|按是否接受日志开始前已存在的状态选择；各规则允许值不同。|

`timeout`从**活动开始**计时。4秒开始，9秒还没结束，就产生`[4,9)`、状态`timeout`。若结束条件恰好在9秒成立，按正常结束处理，状态是`closed`。记录只到7秒则属于提前结束观测，不能声称设备超时。

一次活动进行中，即使又收到开始信号，也不会留到当前活动结束后补启动。活动结束后，需要再次看到开始条件从假变真，才会开始下一次活动。

例如开始信号从第4秒起一直为真，第9秒活动结束后，不会立即开始下一次。开始、结束条件同时成立时，也不会输出一段时长为0的活动。

活动已经开始后，开始信号缺失不会直接终止它；结束信号缺失会中断它，因为无法判断活动何时结束。`timeout`不填或为null表示没有超时上限；填写时必须大于0。

完整例子得到`[0,2)`正常结束、`[4,9)`超时、`[11,14)`正常结束，三段信号均值分别10、52、110。见[可运行案例](examples.md)。旧Sclicer的`start_end`含义不同，转换前必须读[迁移](migration.md)。

<a id="rule-window-delta"></a>
## 滑动窗口变化量检测：window_delta

应用位置：以[teaching-base.yaml](examples/teaching-base.yaml)为基础，在文件根级加入或替换`rules`，代码已包含父键。存在同名列表时按本例替换该列表，不把父键再嵌入列表项。

最小变化量规则使用默认行为；替换基础文件的根级rules。

```yaml
rules:                         # 列出识别活动或瞬间变化的规则；每项产生有独立ID的事件
  - name: change               # 为规则取唯一名称；窗口rule和计算scope通过此名选择它的事件
    signal: voltage            # 选择用于变化量判断的分析信号；填写上方signals中的名称
    window: 4s                 # 设置向前比较变化量的时间窗口长度；依据业务变化尺度填写
    direction: rise            # 选择变化方向；rise检测上升，fall检测下降，any检测任一方向的幅度
    threshold: 5               # 设置触发变化的幅度门槛；数值单位与所选信号一致
    rule_type: window_delta    # 选择活动或变化识别算法；本例检查向前窗口内的变化幅度、方向及配置的单调性要求
```

需要限制单调性或初次触发时，再用下段替换同一rules字段：

```yaml
rules:                         # 列出识别活动或瞬间变化的规则；每项产生有独立ID的事件
  - name: change               # 为规则取唯一名称；窗口rule和计算scope通过此名选择它的事件
    signal: voltage            # 选择用于变化量判断的分析信号；填写上方signals中的名称
    window: 4s                 # 设置向前比较变化量的时间窗口长度；依据业务变化尺度填写
    direction: rise            # 选择变化方向；rise检测上升，fall检测下降，any检测任一方向的幅度
    threshold: 5               # 设置触发变化的幅度门槛；数值单位与所选信号一致
    monotonic: true            # 控制窗口内是否要求持续同向变化；true检查，false仅检查规定的变化幅度
    emit_initial: true         # 控制初始已为真时是否发出初始事件；true发出，false等待实际变化
    rule_type: window_delta    # 选择活动或变化识别算法；本例检查向前窗口内的变化幅度、方向及配置的单调性要求
```

`signal`接受数值信号别名或受支持的数值表达式；不能填布尔条件。`window`必须为正。`threshold`必须是非负有限数值，单位与计算的信号相同。电压阈值5表示5V，**没有除以4秒**，不是5V/s。

|字段|控制作用与效果|可填写的值|数据类型|必填/默认|取值依据|
|---|---|---|---|---|---|
|<a id="window-delta-signal"></a>`signal`|检查哪个数值的变化。可以填 `"voltage * 2"`；不能填 `"voltage > 5"`，后者得到的是真假而不是数值。|数值信号名或数值表达式，例如 `"voltage"`|字符串|是；无|选择已定义的数值信号或合法数值表达式。|
|<a id="window-delta-window"></a>`window`|每次检查往前看多长时间。在6秒检查4秒窗口，就是比较2秒到6秒的数据；不是每4秒检查一次，也不是取4条记录。|大于0，例如 `"4s"`|时长字符串|是；无|按希望比较的历史跨度填写。|
|<a id="window-delta-direction"></a>`direction`|选择检查上升、下降，还是不区分方向的变化。|`"rise"`、`"fall"`、`"any"`；含义见下表|字符串|是；无|按需要检测上升、下降或双向变化选择。|
|<a id="window-delta-threshold"></a>`threshold`|变化量达到这个数才算满足条件，等于阈值也算。电压单位是V时，填5表示5V；填写数字 `5`，不填写字符串 `"5V"`。|大于或等于0；可填整数或小数|数字|是；无|按允许的变化量填写，使用信号单位。|
|<a id="window-delta-monotonic"></a>`monotonic`|设true时，rise要求整段不下降，fall要求整段不上升，any要求整段单向变化。相等的平台不算反向；0→10→5虽净上升5，但不是单调上升。|`false`：比较首尾；`true`：还检查中途有没有反向变化|布尔值|否；`false`|按是否允许窗口内先升后降等反向变化选择。|
|<a id="window-delta-coverage-policy"></a>`coverage_policy`|首尾有数而中间缺失时，仍然无法判断变化条件。当前只允许full；不能通过其他值跳过窗口中间的缺失。|当前版本填 `"full"`，表示整个窗口都要有有效数据|字符串|否；`"full"`|目前使用full，要求完整窗口。|
|<a id="window-delta-emit-initial"></a>`emit_initial`|决定首个完整、可判断的窗口已经达到变化要求时，是否记一个点。填true也不会补齐缺失窗口；后续缺失后的恢复不算首次窗口。|`false`：等到条件由不满足变为满足；`true`：首个完整窗口满足时也触发|布尔值|否；`false`|按是否接受日志开始前已存在的状态选择；各规则允许值不同。|
|<a id="window-delta-retrigger"></a>`retrigger`|两种设置都不会在条件一直满足时反复触发。once在首次触发后停止产生新点；它不会放宽首次触发需要的窗口、阈值等条件。|`"edge"`：每次由不满足变为满足都触发；`"once"`：本次会话最多触发一次|字符串|否；`"edge"`|按会话内需要一次还是多次触发选择。|

`direction`三种写法的区别如下。判断时都拿计算出的变化量与threshold比较：

|值|检查什么|变化量怎么算|2V升到7V时的变化量|
|---|---|---|---|
|`"rise"`|有没有上升足够多|结束值减开始值|5V|
|`"fall"`|有没有下降足够多|开始值减结束值|−5V，因此不满足“下降至少5V”|
|`"any"`|无论上升下降，变化是否足够大|首尾差的绝对值|5V|

电压在0、2、4、6、8、10、12、14秒分别为0、0、5、5、0、0、5、5V，上述配置在4秒和12秒产生点事件。每个点前后各取1秒，片段均值都是2.5V。

4秒窗必须有完整4秒的可用数据，首尾都有数还不够：中间过期或缺失仍不能判断。单调上升的反例是0→10→5V，虽然末值比首值高5V，但中间下降过，不能触发。分析范围从10秒开始时，不会自行读取之前的数据补窗，最早14秒才可能有完整窗口。

即使没有新记录，随着时间推移，窗口内的数据也会变化。例如0秒为4V、1秒为0V、2秒起为8V，并且这些记录始终有效。在第4秒看过去4秒，能看到4→0的下降，不满足单调上升；到了第5秒，只看第1秒到第5秒，已经不包含那次下降，可以满足单调上升要求。

这条规则记录的是“变化要求在何时满足”，所以输出点事件。如果要计算触发前后的平均电压，需另设一个时间窗口。具体写法见下一节。

## 配窗口和计算项

活动规则用`anchor="activity"`，点规则用`anchor="point"`。例如报警前后各取2秒：

应用位置：以[teaching-base.yaml](examples/teaching-base.yaml)为基础，在文件根级加入或替换`windows, calculations`，代码已包含父键。存在同名列表时按本例替换该列表，不把父键再嵌入列表项。 依赖：代码中的rule为capture时先加入上方start_only规则；rule为alarm时先加入hysteresis规则。保留该依赖规则，再加入本块的windows/calculations。

```yaml
windows:                             # 围绕已定义规则的事件选取时间片段，供计算或导出使用
  - name: context                    # 为窗口定义取唯一名称；计算或导出通过此名选择产生的片段
    rule: alarm                      # 选择生成窗口的事件规则；填写前面rules中的name
    pre: 2s                          # 设置起点之前保留多久上下文；0s表示不提前
    post: 2s                         # 设置结束点之后保留多久上下文；0s表示不延长
calculations:                        # 列出希望获得的统计或积分结果，每项独立选择范围和算法
  - name: mean_temperature           # 为这项计算结果取唯一名称；结果表用它区分计算项
    expr: temperature                # 指定参与计算的数值或信号表达式；引用前面已定义的信号
    operation: time_weighted_mean    # 选择计算方法；本例按有效值持续时长加权求平均
    scope:                           # 选择计算范围；session整段会话，{rule: 名称}逐事件，{window: 名称}逐片段
      window: context                # 按指定窗口的每个片段分别计算；填写前面windows中的name
```

这段配置计算报警前2秒到解除后2秒的平均温度。若只想计算报警期间的平均温度，把 `scope` 改成 `{rule: alarm}`。日志没有覆盖的前后时间仍会标为缺失，不会自动补出温度值。

多次报警的窗口是否合并，见[窗口配置](windows.md#window-fields)。请求与响应的配对属于另一种分析，见[配对规则](sequences.md)。

底层类与函数参数见[stability](reference/chronaxis.core.stability.md)、[window_delta](reference/chronaxis.core.window_delta.md)、[规则解析](reference/chronaxis.planning.nodes.md)。

完整输入和三次活动核对见[start_end完整案例](examples.md#start-end-case)。

### 严格超过指定时长

`minimum_duration: 60s` 配合 `duration_comparison: ">"` 表示连续成立严格超过60秒。`selection_origin`仍默认`onset`，积分覆盖整个合格活动；显式`confirmed`才从确认时刻开始。程序时间精度为1ns，实际间隔模式在60秒后第一个可表示时刻确认；固定/DBC模式仅随所选报文推进，达到60秒整不会确认，要等累计严格超过60秒的那条报文。跨连续分卷不重置候选；无效更新或有效期到期仍中断连续性。
