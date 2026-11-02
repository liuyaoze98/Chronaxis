# 逐消息累计

根级`message_calculations`对每条目标CAN消息计算一次表达式并累计。它使用当前消息携带的值，适用于按已知周期计算单次贡献的任务；普通信号时间积分使用`calculations`，二者的时间依据不同。

## 完整最小例与方向分组扩展

[message-minimal.yaml](examples/message-minimal.yaml)使用[message-clean.asc](examples/data/message-clean.asc)与[power.dbc](examples/data/power.dbc)。0秒有两条ID为0x100、功率4000W的消息，每条按0.1秒贡献400J，合计800J。两条消息即使同刻仍分别累计；不按普通信号去重。1秒记录只在请求范围之外，不计入[0,1)。

[message-directions.yaml](examples/message-directions.yaml)使用[方向输入](examples/data/message-direction.asc)和[方向DBC](examples/data/message-direction.dbc)，先将Power绑定为power、Direction绑定为direction，再分别声明正方向与负方向计算。0、1、2秒方向值为1、-1、0，各条功率4000W；前两条分别贡献400J到正/负组，0方向不进入任一组。完整输出同时保留贡献明细，可按计算项ID核对跳过原因。

两例命令：`chronaxis run 文件名.yaml --output 新目录`。所有公式参数和方向信号均在同一完整文件中定义。下方已有BLF例另演示一条缺值报文，不是本最小ASC例的数据。

本例还在signals中声明`period: 100ms`：当前公开运行入口会初始化已使用信号的有效期，DBC没有报文周期时需显式提供period或valid_for。这里不会把100ms再乘到消息贡献上；实际每条消息的乘数仍由公式中的`parameters.period`明确指定，两处字段不会自动关联。

## 消息能量：4000W×0.1秒×2次=800J

下面是`message_calculations`的一项片段；信号power需已在完整计划定义；本例只有一个CAN来源，自动采用它：

应用位置：以[message-energy.yaml](examples/message-energy.yaml)为基础，在文件根级加入或替换`message_calculations`，代码已包含父键。存在同名列表时按本例替换该列表，不把父键再嵌入列表项。

```yaml
message_calculations:       # 按每条目标CAN报文计算贡献再累计；与按实际时间积分分别配置
  - name: energy            # 为逐消息累计结果取唯一名称；用于识别对应结果行
    update_message:         # 指定触发一次求值的目标报文；通道和ID从日志/DBC取得
      frame_id: 0x100       # 指定每到一条便求值的报文ID；从DBC取得
    parameters:             # 定义逐消息公式使用的固定参数；名称由公式引用，值来自采集/业务规范
      period:               # 提供名为period的公式参数；在本例表示每条消息计入的时间
        value: 0.1          # 填写每条消息代表的时间数值；从消息周期或业务规则取得
        unit: s             # 声明该公式参数的单位；本例s表示秒
    expr: power * period    # 定义单条目标消息的贡献；使用该报文信号和parameters常量
    unit: J                 # 声明累计结果的单位；须与表达式量纲相符
```

两条同刻4000W消息各贡献400J；第三条缺值记missing_input；非目标ID不算尝试。总计800J、3次尝试、2次贡献、1次跳过。period是明确给定的固定周期，不从时间间隔推断，也不再乘实际报文之间的时间间隔。

### message_calculations每一项的全部字段

主表相对于`message_calculations[]`；下方三个子表分别位于`message_calculations[].update_message`、`message_calculations[].parameters.<参数名>`和`message_calculations[].split_by_sign`。参数名由公式引用，例如period，不能把value直接放在parameters层。

|字段|数据类型|必填|省略时的值|取值及含义|
|---|---|---|---|---|
|name|字符串|是|无|命名本项累计结果；由配置作者自行取唯一名称。计算项名称，例如`energy`，不能与其他生成节点重名。|
|source|字符串|多个候选来源时必填|唯一原始报文来源|选择提供原始报文的来源；从sources[].name取得。已声明的asc_or_blf、can_blf、can_asc或raw_can_csv来源名；本计算仅引用同一来源的目标报文。|
|profile|字符串|否|从所选来源确定|选择与输入格式对应的消息计算配置规范；根据source_type填写下列精确名称。can_blf填`"sclicer-functions-v1"`并与来源采用的实现一致；通常省略profile；asc_or_blf、can_asc和raw_can_csv填`"can-text-v1"`。|
|operation|字符串|否|legacy_sum|选择如何合并每次计算的结果；目前仅支持求和。填`"legacy_sum"`，把每次成功求值的结果相加。|
|message_policy|字符串|否|current_message-v1|选择每次求值使用哪些信号更新；目前只允许当前消息。填`"current_message-v1"`，每次只取当前报文的值。不能增加cache_policy来启用旧缓存。|
|update_message|对象|是|无|指定触发求值的报文身份；从日志通道和DBC报文定义取得。指定哪一种报文触发计算，四个字段见下表。|
|expr|字符串|是|无|规定每条目标消息贡献多少；根据业务公式组合当前消息信号与已声明参数。每条报文计算一次的表达式，例如`"power * period"`。信号须来自本来源、本报文；参数须在本指标parameters里声明；不能引用普通derived信号或另一报文的值。算符见[表达式](expressions.md)。|
|unit|字符串|是|无|声明单次贡献及累加结果的单位；按公式量纲取得。公式结果单位，例如`"J"`；它不会自动增加一次时间积分。|
|parameters|对象|否|`{}`|定义公式所需常量；参数名由公式引用，数值从协议或业务规定取得。公式常量，键为参数名，每个值是含value和unit的对象。例如本页period子项填写value: 0.1和unit: s。|
|split_by_sign|对象|否|不按方向筛选|控制是否按一个方向信号分组累计；需要正负分组时填写。选择只累计正方向或负方向的消息；三个字段见下表。要同时得到两个方向，分别声明两个不同name的指标。|

`update_message`只必填frame_id；channel省略时采用来源通道，两个帧型选项可省略，实际匹配出现歧义时才要求补充：

|字段|数据类型|取值及含义|
|---|---|---|
|channel|整数|选择目标报文所在通道；从采集通道说明取得。从1开始的用户通道号，必须等于所选来源的通道；第一路填1，内部转换自动完成。|
|frame_id|整数或字符串|选择目标报文ID；从对应DBC的报文定义取得。必填；0x前缀为十六进制、0b为二进制、无前缀为十进制。JSON带前缀时使用字符串。范围与[信号绑定](inputs.md#can-field)相同。|
|is_extended|可选布尔值|限定目标报文使用标准ID还是扩展ID；按日志帧类型填写。`false`限定标准帧，`true`限定扩展帧；省略时自动识别。相同数值ID的两种帧不能混为一类，显式null无效。|
|is_fd|可选布尔值|限定经典CAN还是CAN FD；按实际采集帧类型填写。`false`限定经典CAN，`true`限定CAN FD；省略时按实际帧识别，显式null无效。|

`parameters`中每个参数的两个字段全部必填，无默认值：

|字段|数据类型|取值及含义|
|---|---|---|
|value|数值|设置公式常量的数值；从协议周期、换算系数或业务规定取得。常量的有限数值，例如周期0.1。按float64使用，不填布尔值、字符串、NaN或Infinity。|
|unit|字符串|设置该常量的单位；依据常量的物理含义填写。常量单位，例如周期用`"s"`、纯比例因子用`"1"`；不是给常量附加一个任意注释。|

`split_by_sign`须填写signal和bucket；value_policy可省略，默认raw_decoded-v1：

|字段|数据类型|取值及含义|
|---|---|---|
|signal|字符串|选择判断方向的原信号；从同报文的signals[].name取得。方向信号的别名；它可以不出现在expr中，但必须来自同一条报文，类型为数值或bool。|
|bucket|字符串|选择累计正方向还是负方向；根据本计算项的业务目标选择。`"positive"`仅累计方向原值大于0的消息；`"negative"`仅累计小于0的消息。等于0不进入任何一组；bool的true按正值、false按0处理。|
|value_policy|字符串|选择按哪一阶段的方向值分组；目前仅允许解码后的原值。填`"raw_decoded-v1"`：按报文刚解码出的方向值分组，不先对它做scale、offset或方向转换，也不沿用前一条值。|

方向信号决定“这一条消息算到哪一组”，公式决定“这一条加多少”。例如方向值为正，但公式算出−10J，这条消息会向正方向组加上−10J，不会自动取绝对值。方向值为0时，两个方向组都不累计它。

两个组最后各自保留6位小数。完全没有消息参与计算，与两条有效贡献10J和−10J相加得到0，是不同情况。完整输入案例见[逐消息完整案例](examples.md#message-energy)。

## 汇总与贡献明细

如果只要总数、不需要逐条核对，设置 `outputs.contributions="none"`。公开计算结果保留value、unit、status、reason、quality及计算项身份，不提供参与/跳过次数或逐原因计数。需要逐次贡献与跳过原因时选择full并读取contributions；配置和输入信息的详细程度由诊断设置决定。

[省略domain](dataset.md)时，可以累计所引用CAN来源的全部文件；默认reader.input_check=auto不会为这个不需要时间的计算额外建立时间范围。如果仍填写domain，就按该范围筛选消息。

`full`保留每次尝试，适合追溯错误；`none`适合已明确只需汇总的任务。它是输出/执行策略选择，不是对性能目标的承诺。性能取决于输入和计算组合，需要用实际任务测量。
