# 数据来源



`sources`位于配置根级，是来源对象的列表。每项说明从哪里读取数据、怎样解释原时间；只有一个来源时，不必填写来源名或`signals[].source`。BLF/ASC由文件扩展名识别；填日志路径和DBC后，再配置[信号绑定](signals.md)。分析对象和请求范围由[dataset](dataset.md)控制。

程序中负责打开来源、读取记录并解释内容的组件称为读取器。`source_type`选择它要处理的格式：CSV物理量列先由文本解析成值，CAN报文字节先按DBC解码成物理量。后续`signals`把得到的值命名、按需换算并检查有效性。因此“原始值”须结合阶段理解：信号字段中的原始值已经完成CSV解析或DBC解码，不一定是文件里最初的文字或字节。

## 选择输入格式

|你已有的数据|是否填写source_type|还需要什么|
|---|---|---|
|BLF或ASC报文日志、连续日志目录|不填；按扩展名识别，也允许混合格式|DBC与要使用的报文ID/信号名|
|每行有时间和信号列的CSV|填写signal_csv|时间列、时间单位、信号类型和单位|
|含ID和十六进制字节的原始CSV|填写raw_can_csv|DBC、时间格式，以及时间/ID/数据列的映射|
|Python中已整理好的时间和值|填写memory|内存记录及信号定义|

AnalysisRunner支持上表五种显式来源，也支持默认的`asc_or_blf`来源：按扩展名识别ASC/BLF，同一来源可依次读取两种格式。`signal_csv`专门读取已解码的物理量列；它不能直接把报文字节当成电压或电流。

### 先运行一个完整任务

优先从[BLF／ASC快速开始](quickstart.md)运行随附的ASC日志和DBC，核对38J的能量。相同配置可将路径替换为自己的BLF，或者整个日志目录，无须中间转换成CSV。

```powershell
chronaxis run analysis.yaml --output can-result
```

从随册examples目录执行，输出目录须尚不存在。[CSV最小配置](examples/input-csv-minimal.yaml)和[内存最小配置](examples/input-memory-minimal.yaml)分别用于已经解码的信号表和程序内记录，不是CAN分析的前置步骤。

[时间平移示例](examples/input-csv-offset.yaml)专门演示已知2秒偏移：原0秒变成2秒，能量仍为38J。多来源只有在确知同步关系时才设置共同clock与offset，默认值不自动校时。

下面的字段表用于把示例换成自己的输入。除明确标注可为null的字段外，不把null当作省略；未知字段或错误结构在加载计划时拒绝，文件不存在、表头不符和无法解析的单元格在读取时报告。

## 来源对象的共同字段

表中字段均相对于`sources[]`，例如`paths`的完整路径为`sources[].paths`，表示sources列表中每个来源的paths。点号和`[]`用于说明层级，不是要照写的键名。每项放在sources数组中。YAML结构见[配置说明](configuration.md)。ASC和原始CSV的专用读取字段另见[文本输入](text-inputs.md)。

|字段|数据类型|必填|默认值|填写内容与作用|
|---|---|---|---|---|
|name|字符串|否|source_1、source_2等|给来源取计划内唯一名称。只有一个可用来源时，signals.source也可省略；多个候选时必须明确选择。|
|source_type|字符串|否|asc_or_blf|默认按扩展名识别ASC/BLF，可混合读取。仅要ASC可填can_asc，仅要BLF可填can_blf；CSV必须明确signal_csv或raw_can_csv，内存必须填memory。|
|time|对象|否；CSV仍需声明时间单位|relative；CAN/内存单位s|组织时间类型、单位、共享起点和偏移。缺省来源起点相互独立，不自动宣称多个来源同步。|
|metadata|对象|否|`{}`|记录本来源的说明信息。项目可自行填写键和值，例如采集仪型号；空对象或省略不增加说明。这里的键不会作为额外读取选项执行。|
|path|路径文本或路径列表|文件来源须与paths二选一|无|可填文件、目录或通配符；与paths使用相同选择规则。通常统一使用paths；memory不填写。|
|paths|路径文本或路径列表|文件来源须与path二选一|无|可填单文件、目录、通配符或显式列表。自动发现的文件自然排序，显式列表保持原顺序；默认ASC/BLF、显式can_asc和raw_can_csv的每项也可用{path: 文件, offset: 2s}；signal_csv与显式can_blf不接受逐文件offset。连续文件中所需记录不能时间回退；完整检查或原帧导出要求全来源时间有序。|

用load_analysis_plan加载时，相对路径以配置文件所在目录为起点；用AnalysisPlan.from_dict构建时，以传入的base_dir为起点，未传则用当前工作目录。

## 目录与连续文件

```yaml
sources:                  # 列出输入来源；每项规定数据位置、格式和时间解释方式
  - paths: data/can       # 选择输入文件、连续分卷列表或目录；相对路径基于本配置，目录按自然序读取
    dbc_by_channel:       # 为每个CAN通道指定解码用DBC文件；键是通道编号的字符串
      '1': network.dbc    # 为这个通道指定DBC文件；路径相对当前配置文件，通道键须为字符串
```

目录内 `part1.asc、part2.blf、part10.asc`按1、2、10读取。只取ASC可写`paths: data/can/*.asc`；需要子目录时明确写`data/can/**/*.asc`。空目录或无匹配文件报错，不静默跳过。显式列表`[part10.asc, part2.asc]`保持原顺序。

文件之间有已知时间偏移时，把它与文件写在一起，例如`paths: [{path: part1.asc, offset: 0s}, {path: part2.asc, offset: 100s}]`；偏移叠加来源的time.offset。逐文件偏移适用于默认ASC/BLF、显式can_asc和raw_can_csv；signal_csv与显式can_blf只支持来源统一的time.offset。适用来源也可写offsets数组，但不能与文件对象中的offset同时声明。独立试验要分别运行，见[批量任务](batch.md)。

### time的全部字段

下表位于`sources[].time`内，例如`unit`完整写作`sources[].time.unit`。这不是信号的`signals[].unit`。

|字段|数据类型|必填|默认值|可填写的值与含义|
|---|---|---|---|---|
|time_type|字符串|否|relative|选择输入时间从哪里开始计数。采集启动后经过的时间填relative；带日期或从1970-01-01 UTC起算的时间填absolute。查采集软件时间设置，不能仅根据数字大小判断。|
|unit|字符串|CSV需要；CAN/内存可省略|CAN/内存s|声明时间列数字的单位或日期文本格式。s秒、ms毫秒、us微秒、ns纳秒、ISO8601日期文字；值来自文件格式说明。例如CSV的5000和ms表示5秒。BLF固定s；ISO8601用于absolute。|
|clock|字符串|relative可省略；absolute不填|来源专属名称|为相对计时的共同零点命名。根据同步记录命名，例如test_button表示同一次试验按钮触发；同名只表达已经同步的声明，不会移动记录时间。|
|offset|时间字符串|否|`"0s"`|给换算后的输入时间统一加一个偏移。根据校时结果填写，可正可负；CSV比共同零点提前2秒开始则填-2s，原5秒变为共同3秒。0s或省略不平移时间。|
|timezone|字符串；signal_csv/memory还允许null|按来源与时间格式决定|不补时区|只为绝对时间提供所需时区。signal_csv/memory可用系统支持的地区名或固定偏移；ASC与原始CSV仅支持UTC或±HH:MM。ASC absolute必须填写；原始CSV的iso8601文字无时区时也要填写。relative、BLF以及原始CSV numeric不填写。|

字段位置统一为`sources[].time.timezone`，但允许值依输入格式而异。ASC/原始CSV显式null无效；signal_csv/memory的null表示不补时区。已有时区的日期按其中偏移解释，不再使用分钟整数形式。

## CAN：来源与信号定位

第一段放入`sources`列表，第二段放入`signals`列表。需要实际的trial.blf和network.dbc；字段定位必须与DBC相符。

应用位置：以自己新建的分析文件为基础，在文件根级加入或替换`sources`，代码已包含父键。存在同名列表时按本例替换该列表，不把父键再嵌入列表项。 示例文件名是待替换的输入路径，须准备相应CSV/DBC/CAN数据；本块本身不是完整任务。

```yaml
sources:                  # 列出输入来源；每项规定数据位置、格式和时间解释方式
  - path: trial.blf       # 指定单个输入文件；相对路径从本配置文件所在目录计算
    dbc_by_channel:       # 为每个CAN通道指定解码用DBC文件；键是通道编号的字符串
      '1': network.dbc    # 为这个通道指定DBC文件；路径相对当前配置文件，通道键须为字符串
```

应用位置：以自己新建的分析文件为基础，在文件根级加入或替换`signals`，代码已包含父键。存在同名列表时按本例替换该列表，不把父键再嵌入列表项。 示例文件名是待替换的输入路径，须准备相应CSV/DBC/CAN数据；本块本身不是完整任务。

```yaml
signals:                     # 把输入字段定义为有名称、类型、单位和有效期的分析信号
  - name: voltage            # 给分析信号取名称；后续表达式和计算通过此名称引用它
    field:                   # 指定来源中的原始字段；CSV填表头，CAN填写通道/报文ID/DBC信号名
      frame_id: 0x100        # 选择包含信号的报文ID；从对应DBC取得，可写整数或支持的进制文本
      signal: PackVoltage    # 填写DBC中的信号名称，大小写须一致
```

本例假定DBC包含信号单位和该报文周期。程序从DBC推导数值类型、单位与帧类型；有效期默认是周期3倍。只有DBC没有周期且本任务需要有效期时，再填写`period`或`valid_for`。多通道/多帧候选不能唯一确定时才补充对应定位字段。

### CAN共同字段

下表字段位于`sources[]`，适用于BLF、ASC和原始报文CSV；signal_csv和memory不使用DBC。

|字段|数据类型|必填|默认值|可填写的值与含义|
|---|---|---|---|---|
|dbc_by_channel|对象|是|无|决定每个通道用哪个DBC解码。键从日志通道取得，写十进制编号文本且无前导零；值是实际DBC路径。例如{"1":"network.dbc"}为第一路通道选择文件。配置从1开始，程序自动对应内部0；旧0基配置的所有通道编号需加1。当前每个来源使用一个通道及其DBC。|
|reader|对象|原始CSV必填；其他CAN可省略|按格式取默认值|组织读取选项。共同的reader.decode_policy默认strict；文本格式及列布局见[文本输入](text-inputs.md)。reader中的各字段并非每种来源都接受。|
|reader.input_check|字符串|否|`"auto"`|auto按任务依赖检查时间；full要求完整来源时间顺序。适用于can_blf、can_asc、asc_or_blf和raw_can_csv。普通ASC只检查所需通道/ID的顺序，来源最早/最晚时间仍在同次读取中统计；详见下方检查范围。|

### BLF读取入口的额外选项

以下字段只由can_blf入口接受：显式source_type: can_blf，或默认来源全部为BLF且未设置逐文件偏移时使用该入口。默认混合ASC/BLF、can_asc及raw_can_csv不能显式填写这些字段。

|字段（相对于sources[]）|数据类型|必填|默认值|可填写的值与含义|
|---|---|---|---|---|
|legacy_profile|字符串|否|sclicer-functions-v1|选择BLF读取实现，当前只接受sclicer-functions-v1，通常省略。|
|reader.decode_scope|字符串|否|`"requested"`|控制解码哪些报文。requested只解码任务需要的报文；all请求全量解码检查。一般分析沿用默认，需要额外核查日志时再选all；能否用于本任务组合由计划检查决定。|

<a id="decode-policy"></a>
### reader.decode_policy：CAN解码策略

此字段位于每个CAN来源的reader映射内，控制如何处理DBC解码，适用于asc_or_blf、can_blf、can_asc、raw_can_csv；不是计算间隔或信号转换字段。替换已有来源bus的reader时，可写下面的子映射；只包含reader父键，不是完整sources列表：

```yaml
reader:                    # 设置来源的读取选项；本片段放在对应sources列表项内
  decode_policy: strict    # 选择已选CAN帧长度检查和解码失败处理；按输入章节的路径对照表选择
```

|decode_policy|用途与行为|
|---|---|
|strict（新版默认）|要求报文长度和结构符合DBC；结构正确而所需值不能解码时记为无效，继续分析。|
|partial|显式允许短载荷的部分解码；能取得的值正常交付，取得不到的所需值无效。仍不接受损坏的报文结构。|
|legacy|保留下方路径表所列行为；文本CAN长度严格且DecodeError失败，旧BLF路径不新增长度检查，解码失败可产生无效值。|

默认asc_or_blf允许ASC/BLF混合；显式can_asc/can_blf限定对应格式。显式文件列表保持顺序，目录与通配符自然排序。ASC/CSV的文字和列结构首先由reader检查，decode_policy不能让无法解析的文本成为有效帧。经典CAN与DBC FD标记的支持范围见[信号定位](#can-field)。

### 解码失败时各读取路径的处理

reader.decode_policy决定已选数据帧的长度检查与解码失败处理。strict用于要求长度完整的输入；partial允许短帧只提供可解出的字段；legacy仅用于需要保留指定旧路径行为的迁移。

|实际读取路径及情况|strict|partial|legacy|
|---|---|---|---|
|文本CAN路径：载荷长度不等于DBC长度|失败|允许短于DBC；超长或DLC与实际字节不一致失败|按strict检查，长度不符失败|
|文本CAN路径：长度检查后cantools抛DecodeError|本条解码值无效，不沿用前值|本条解码值无效，不沿用前值|任务失败|
|can_blf旧路径：载荷长度不等于DBC长度|失败|允许短于DBC；超长或DLC与实际字节不一致失败|不新增长度检查，交原解码器处理|
|can_blf旧路径：原解码器解码失败|返回空解码结果，所需值无效|返回空解码结果，所需值无效|返回空解码结果，所需值无效|
|未选报文|按所需观测/导出范围读取，不因未选择的信号执行这项DBC解码|同左|同左|

文本结构损坏、输入时间错误以及未列出的I/O或程序异常仍可能使任务失败；不能把partial理解成忽略所有错误。没有完整字段的短帧不补零。

路径由规范化后的source_type决定：can_asc、raw_can_csv和保留为asc_or_blf的混合路径使用文本CAN适配层；can_blf使用旧BLF路径。省略source_type或填写asc_or_blf时，纯ASC归一为can_asc，包括设置了逐文件offsets的情况；纯BLF且未填offsets时归一为can_blf；混合ASC/BLF，或纯BLF且设置offsets时保留asc_or_blf。不能只看某一个文件后缀判断legacy行为。


<a id="can-field"></a>
### signals[].field：选择CAN报文中的信号

BLF、ASC和原始报文CSV使用相同的绑定结构。必填`frame_id`和`signal`；唯一DBC通道可省略`channel`，field不接受message字段，报文由通道、ID和信号名定位。

|字段|数据类型|必填及默认|填写内容与例子|
|---|---|---|---|
|channel|正整数|唯一DBC通道时可省略|选择信号来自哪个CAN通道。从1开始的用户通道编号，须与dbc_by_channel一致。ASC文字通道1填写1；程序自行转换为内部0。|
|frame_id|整数或字符串|必填，无默认|选择包含所需信号的报文ID，从DBC报文定义取得。0x100十六进制、0b100000000二进制、256十进制都表示256；无前缀010按十进制10。范围0～536870911，显式标准帧最多2047。|
|signal|非空字符串|必填，无默认|选择目标报文中的哪一个DBC信号。复制该报文定义里的名称，例如PackVoltage，大小写一致；这里不填分析别名voltage。|
|is_extended|布尔值|可省略，自动识别|限制标准/扩展ID帧的选择。false只选标准帧，true只选扩展帧；依据DBC与实际日志标志填写。省略时自动识别，小ID也可能是扩展帧，不能按ID数值猜。null不合法。|
|is_fd|布尔值|可省略，自动识别|限制经典CAN/CAN FD帧的选择。false选经典CAN，true选CAN FD；依据日志实际类型填写。省略保留自动识别，不按载荷长度猜；null不合法。|

JSON不允许直接写带进制前缀的数值，因此写`"frame_id": "0x100"`或`"frame_id": 256`；YAML可写`frame_id: 0x100`。前缀大小写均可；不接受负数、浮点数、布尔值或八进制前缀。两个类型选项省略表示自动识别，显式`null`不合法。

当前JSON Schema对ID字符串先检查数字格式；加载计划时，Python还会把它转换为整数并检查范围。例如`is_extended: false`配`frame_id: "0x800"`会被计划加载器拒绝，因为2048超过标准帧上限2047。编辑器只显示Schema检查通过，不能替代`chronaxis validate analysis.yaml`的完整检查。

例如标准帧和扩展帧都使用ID `0x100`，且都含`PackVoltage`。日志只有扩展帧时可根据实际标志选中扩展定义；同一绑定后续又遇到也符合条件的标准帧时，程序会提示补充`is_extended`，不会把两类数据混在一个信号中。ID不存在或信号名写错时会直接说明缺项，不要求用类型参数掩盖错误。

DBC标为FD但日志实际为经典CAN的已支持兼容继续保留，并记录提示；显式设置类型只用于选择报文，不修改输入帧。每个来源仍使用一个通道和对应DBC，连续文件按原序处理。DBC已经应用的factor/offset不能重复执行。

### 解码范围与时间检查范围

以下两个选项回答不同的问题，完整路径分别为`sources[].reader.decode_scope`和`sources[].reader.input_check`：

- `decode_scope`只用于BLF旧读取入口，决定解码哪些报文。默认 `"requested"` 处理当前任务需要的报文；`"all"` 用于全量解码检查。
- `input_check`用于所有CAN来源，决定时间检查范围。默认 `"auto"` 根据任务决定；`"full"` 检查完整来源的时间顺序，不是开启所有信号解码或所有诊断输出。

例如只按固定周期累计整份文件的消息能量，可能不需要报文时间；但找活动或筛选某段时间，就需要检查时间。运行explain后，可在 `input_requirements` 查看本次需要的信号和时间检查范围。未检查的记录不能据此认定为正确。

普通ASC及混合ASC/BLF的`auto`模式只要求所需通道和报文ID按原顺序推进；无关Tx帧的微秒回退不会阻断分析。来源范围与记录顺序分开处理：最早/最晚观测时间在同次读取中统计，原始时间不改写。显式`full`或原帧导出仍拒绝全来源回退；目标报文及跨连续文件的目标时间回退始终报错，不自动排序、钳平或清洗。ASC的relative增量仍按全部相关时间行依次累加，不能把跳过无关解码理解为丢弃这些增量。原始CSV沿用其列解析及时间策略，不能由ASC的说明推定它会忽略任意坏行。

普通规则、窗口、计算和导出也可以省略`dataset.domain`，程序采用输入实际观测范围；多来源取观测范围的并集，没有观测数据不生成事件，会话统计返回空值。仅整文件逐消息累计且不需要时间时，可以不额外建立时间范围；存在时间筛选、事件或其他时间相关功能时仍检查所需时间。省略domain不会关闭时间相关功能所需的检查。详见[分析范围](dataset.md)和[当前消息累计](message-calculations.md)。

## CSV：每行是一次明确更新

下面是`sources`列表中的一项，文件`part1.csv`和`part2.csv`须包含时间列`time_ms`及所引用的信号列。

应用位置：以自己新建的分析文件为基础，在文件根级加入或替换`sources`，代码已包含父键。存在同名列表时按本例替换该列表，不把父键再嵌入列表项。 示例文件名是待替换的输入路径，须准备相应CSV/DBC/CAN数据；本块本身不是完整任务。

```yaml
sources:                             # 列出输入来源；每项规定数据位置、格式和时间解释方式
  - paths: [part1.csv, part2.csv]    # 选择输入文件、连续分卷列表或目录；相对路径基于本配置，目录按自然序读取
    source_type: signal_csv          # 选择数据格式；memory内存记录、signal_csv物理量表、can_blf/can_asc/raw_can_csv原始CAN
    time_column: time_ms             # 填写CSV时间列的实际表头，大小写和文件一致
    time:                            # 说明输入时间数值的类型、单位、共同起点和校准偏移
      unit: ms                       # 声明输入时间数值的单位；根据文件说明填写s/ms/us/ns等受支持单位
    reader:                          # 设置当前来源的文本解析、列映射或解码行为；可用子字段取决于来源格式
      missing_values: ['', NA]       # 列出CSV中表示缺失的文本；遇到它们产生无效更新，不按零计算
```

下表位于`sources[]`；例如编码写在`sources[].reader.encoding`，不是来源顶层。

|signal_csv专用字段|数据类型|必填|默认值|含义与例子|
|---|---|---|---|---|
|time_column|字符串|是|无|选择哪一列提供记录时间。复制CSV实际表头，例如time_ms；大小写须一致，填错会在读取表头时失败。|
|reader.encoding|字符串|否|`"utf-8"`|选择把文件字节读成文本的编码。根据导出设置填写utf-8、utf-8-sig、gbk等实际编码；省略按utf-8读取，不自动猜测。|
|reader.delimiter|字符串|否|`","`|选择分隔各列的字符。根据原文件填写一个字符；逗号CSV填逗号，制表符文件填双引号字符串"\t"。不能把多个字符当一个分隔符。|
|reader.missing_values|字符串数组|否|`[""]`|规定哪些CSV单元格文字表示无效更新。按设备导出约定填写，例如["", "NA"]；精确匹配且不自动去空格。空列表表示不额外声明缺失文本，null不是列表；出现NA后不会继续保持上一条有效值。|

`path`和`paths`二选一。显式列表按给定顺序读取；目录和通配符自然排序。比如part1结束于第10秒，part2却从第0秒重新计时，直接连接读取会因时间回退而报错。

上例把空单元格和NA都声明为无效值。如果上一行电流为5A，下一行写NA，程序就从下一行时刻起认为电流未知，不再沿用5A。需要查输入位置时显式开启diagnostics.trace并读取input_trace；默认摘要结果不保存逐单元格原始位置。

例如原列`Current_mA`转成别名`current`：

应用位置：以自己新建的分析文件为基础，在文件根级加入或替换`signals`，代码已包含父键。存在同名列表时按本例替换该列表，不把父键再嵌入列表项。 示例文件名是待替换的输入路径，须准备相应CSV/DBC/CAN数据；本块本身不是完整任务。

```yaml
signals:                 # 把输入字段定义为有名称、类型、单位和有效期的分析信号
  - name: current        # 给分析信号取名称；后续表达式和计算通过此名称引用它
    field: Current_mA    # 指定来源中的原始字段；CSV填表头，CAN填写通道/报文ID/DBC信号名
    dtype: float64       # 选择分析值类型；float64小数、int64有符号整数、uint64非负整数、bool真假、enum状态名称
    unit: A              # 声明分析值的单位；按物理含义填写，无量纲用字符串"1"；仅标签不执行换算
    valid_for: 200ms     # 设置一次有效更新最多沿用多久；依据采样周期和允许数据陈旧程度填写
    conversion:          # 设置读取后额外的单位换算；不重复DBC已执行的缩放和偏移
      input_unit: mA     # 声明CSV解析或DBC解码后、额外换算前的单位；查列说明或DBC物理单位
      scale: 0.001       # 设置额外数值乘数；按输入与目标单位的合法换算倍率填写，避免重复DBC换算
```

上例0.001明确把毫安换为安培。`valid_for=200ms`仅是示意，真实项目应按采集方式确认。字段名与别名可以不同，表达式统一写`current`。

## 内存：把记录直接写进配置

下面是`sources`列表中的一项。`rows`保存原始时间和值，适合构造可手工复算的例子。

应用位置：以自己新建的分析文件为基础，在文件根级加入或替换`sources`，代码已包含父键。存在同名列表时按本例替换该列表，不把父键再嵌入列表项。 本段直接提供内存记录，不需要外部文件；信号和计算需在完整计划中另行定义。

```yaml
sources:                   # 列出输入来源；每项规定数据位置、格式和时间解释方式
  - source_type: memory    # 选择数据格式；memory内存记录、signal_csv物理量表、can_blf/can_asc/raw_can_csv原始CAN
    rows:                  # 提供内存来源的记录列表；每条记录含时间及该时刻的字段值
      - time: 0s           # 填写本条合成记录的发生时间，按本来源的time声明解释
        values:            # 列出本条记录实际更新的原字段及值；字段名供signals.field选择
          power: 4000      # 本时刻原字段power的合成输入值；其类型和单位由下方信号定义说明
          active: 1        # 本时刻原字段active的合成输入值；其类型和单位由下方信号定义说明
      - time: 1s           # 填写本条合成记录的发生时间，按本来源的time声明解释
        values:            # 列出本条记录实际更新的原字段及值；字段名供signals.field选择
          power: 4000      # 本时刻原字段power的合成输入值；其类型和单位由下方信号定义说明
          active: 0        # 本时刻原字段active的合成输入值；其类型和单位由下方信号定义说明
      - time: 8s           # 填写本条合成记录的发生时间，按本来源的time声明解释
        values:            # 列出本条记录实际更新的原字段及值；字段名供signals.field选择
          power: 4000      # 本时刻原字段power的合成输入值；其类型和单位由下方信号定义说明
          active: 0        # 本时刻原字段active的合成输入值；其类型和单位由下方信号定义说明
```

下表位于`sources[]`；记录时间的完整路径为`sources[].rows[].time`。

|memory专用字段|数据类型|必填|默认值|含义与例子|
|---|---|---|---|---|
|rows|对象数组|是|无|提供直接放在配置里的输入记录。按时间顺序填写time和values，数据可来自Python整理或手工合成；[]表示没有观测，不能据此产生正常零结果。|
|rows[].time|时间字符串|是|无|指定这条记录发生的时刻。相对时间写1s等带单位文本，绝对时间写明确日期时间；内存记录不接受用裸数字让time.unit猜单位。|
|rows[].values|对象|是|无|指定这个时刻更新了哪些原字段。键由输入数据命名，供signals.field选择；值来自实测或已声明的合成数据，可为数字、布尔、字符串或null。例如power: 4000表示该字段本次为4000，是否有效及单位由信号声明决定。|

内存行的`time`必须带单位（绝对时间则明确日期/时区），不是按`source.time.unit`猜裸数字。上面的3条记录是手工准备的测试数据，方便先算出预期答案再检查规则；真实数据很多时改用CSV或BLF文件，程序可以分批读取，不必把整份记录写进配置。[SourceSpec/MemoryRow](reference/chronaxis.core.models.md)和[MemorySourceAdapter](reference/chronaxis.sources.memory.md)给出底层类型化接口。

## 多来源时间同步

两份文件都写“3秒”，不一定表示同一时刻。例如CAN采集从按下试验按钮开始计时，CSV仪表提前2秒就已开始计时。按钮后的第3秒，在CAN里是3秒，在CSV里是5秒。

此时要把CSV的时间减去2秒，才能与CAN一起计算。时间转换使用“原时间换成规定单位后，加offset”；因此CSV填写`offset="-2s"`。如果仪表晚开始2秒，则应加2秒。

两个来源的time字段可写成：

时间同步示意：下面两个说明标签不是配置字段。分别将各自time的子字段替换到对应sources列表项的time中；不把“CAN来源的time”等文字复制到文件。

```yaml
CAN来源的time:             # 说明输入时间数值的类型、单位、共同起点和校准偏移
  clock: test_button    # 命名相对时间的共同起点；来自同步依据，同名不会自动校时
CSV来源的time:             # 说明输入时间数值的类型、单位、共同起点和校准偏移
  unit: ms              # 声明输入时间数值的单位；根据文件说明填写s/ms/us/ns等受支持单位
  clock: test_button    # 命名相对时间的共同起点；来自同步依据，同名不会自动校时
  offset: -2s           # 给换算后的时间加固定偏移；依据时钟校准结果填写，不是数值偏移
```

这是两个time字段的展示，不是可直接提交的完整sources数组；把其中对象分别放入相应来源的`time`字段。CSV原值5000ms会先变为5秒，再减2秒，得到共同时间3秒。

`clock`是对共同起点的声明。把两个不同起点强行写成相同名字不会真的同步数据。偏移量必须来自已知采集起点、同步记录或能确认发生在同一时刻的事件；如果不知道偏了多少，先分别分析，不能任意拼在一起算功率。

若两份文件都已有带日期和时区的绝对时间，可使用absolute方式统一到UTC时间。本版只支持已知的固定偏移，不会自动识别相似波形，也不会校正两个时钟越来越不同步的漂移。

时间对齐后，仍要检查信号是否有效。例如该时刻电压已经过期，就不能继续拿旧电压乘新的电流。可运行例子见[CAN与CSV联合分析](examples.md#can-joint-analysis)。

## ASC和原始CAN CSV

can_asc和raw_can_csv都读取未解码的CAN报文。前者按指定ASC版本读报文，后者从原始报文列直接解码，两者都需要DBC；这和已经有电压/电流列的signal_csv不同。全部字段、日期/日内时间、通道和跨文件偏移见[文本CAN输入](text-inputs.md)。
