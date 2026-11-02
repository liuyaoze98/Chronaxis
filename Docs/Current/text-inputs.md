# 读取ASC和原始CAN报文CSV



先分清两种CSV。`signal_csv`已经有时间、电压、电流等物理量列；`raw_can_csv`的一行还是报文ID和十六进制字节，必须用DBC把字节解成信号。文件扩展名相同不表示内容相同。

**DBC**是CAN报文的字段说明文件：例如ID 0x100的第一个字节表示Voltage、比例是1、单位V。它不提供日志的采集时刻，但可以声明报文周期，供默认有效期等功能使用；它也不替你确认测量位置和电流方向。ASC是文本报文日志，BLF是另一种二进制日志；文本入口和BLF入口都把解码后的信号送入同一个分析引擎。

本页配置位于根级`sources`列表，每段来源示例都是其中一项；解码后的信号由`signals`引用。原始CSV读取报文列，ASC读取报文行，两者输出带统一时间的信号更新。

## 完整最小例与列映射扩展

下载[ASC最小配置](examples/input-asc-minimal.yaml)、[joint.asc](examples/data/joint.asc)和[joint.dbc](examples/data/joint.dbc)，保留配置里的data相对目录。在examples目录运行：

```powershell
chronaxis run input-asc-minimal.yaml --output asc-minimal-result
```

该配置只绑定Voltage并计算一次积分。DBC把第一个字节按2×原值+1换算：原字节1、3、1得到3、7、3V，各持续1秒，结果为13V·s。`signals`不再次重复DBC比例。

[原始CSV最小配置](examples/input-raw-csv-minimal.yaml)读取[raw-can-example.csv](examples/data/raw-can-example.csv)，使用同一DBC和信号定义，结果也为13V·s。此样例显式设置id_base: 16，将CSV的id列按十六进制读取，文字100对应DBC的十进制256；data列是01 05等字节，不能直接当作电压。

[列映射扩展配置](examples/input-raw-csv-mapping.yaml)只把接收方向从固定true改为读取direction列，并用value_map把Rx转成true、Tx转成false。`strip: true`使第一行的“ Rx ”先去掉两端空格再匹配；本数据都是Rx，所以积分仍为13V·s。换成未列出的文字会报映射错误，不会自动当成发送或接收。

```powershell
chronaxis run input-raw-csv-minimal.yaml --output raw-csv-result
chronaxis run input-raw-csv-mapping.yaml --output raw-mapping-result
```

三个配置都包含来源、信号和计算的全部定义，并逐字段注释；输出目录须尚不存在。下文片段用于替换真实输入格式，不能代替这些完整任务。

## 完整来源字段

下表字段相对于`sources[]`，例如`reader.decode_policy`的完整路径为`sources[].reader.decode_policy`。以下共同字段用于`sources`中的`source_type="can_asc"`或`"raw_can_csv"`项：

|字段|数据类型|必填|默认值|字段作用、可填内容与效果|取值依据|
|---|---|---|---|---|---|
|name|字符串|否|source_1等|给本来源设置唯一名称。来源名称，例如 `"bus"`。|由项目命名，后续signals.source引用。|
|source_type|字符串|原始CSV必填；ASC可省略|asc_or_blf|选择原始CAN文本格式。`"can_asc"`读取ASC；`"raw_can_csv"`读取报文CSV。|查看实际文件内容；ASC通常省略source_type；原始报文CSV填raw_can_csv。|
|path|路径文本或路径列表|与paths二选一|无|指定文件、目录、通配符或显式列表；选择规则与paths相同。|文件实际位置；相对本配置所在目录。|
|paths|路径文本或路径列表|与path二选一|无|指定文件、目录、通配符或显式列表；展开后1～4096个连续文件；相对配置文件目录。|按采集先后列实际路径；显式列表保持顺序，目录或通配符自然排序。|
|dbc_by_channel|对象|是|无|指定所选通道的解码定义文件。每个来源必须且只能填写一个通道及其一个DBC，例如 `{"1":"sample.dbc"}`。键为从1开始的十进制正整数文字，不带前导零。|日志通道和匹配的DBC；路径相对配置文件。|
|time|对象|ASC可省略；CSV需声明单位|relative，ASC单位s|组织这份来源的时间解释和同步设置。由下列时间字段组成。|采集软件设置、日志头及同步记录。|
|time.time_type|字符串|否|relative|选择相对起点计时还是日历时间。`"relative"`：相对共同起点；`"absolute"`：有日历日期的绝对时间。|日志实际含义；没有可靠日期时不能虚构absolute。|
|time.unit|字符串|CSV需要；ASC可省略|ASC为s|声明输入时间数字的单位或文本表示。s秒、ms毫秒、us微秒、ns纳秒或ISO8601日期文本。ASC填s；CSV与time_format的组合见下表。|格式说明；ASC秒，CSV按time_format表选择。|
|time.clock|字符串|relative可省略；absolute不填|来源专属名称|命名相对时间的共同零点。共同起点的名称，如 `"test_start"`；不能靠名称把两台记录器自动同步。|同一次触发或经过验证的同步依据，例如test_start。|
|time.offset|时间字符串|否|`"0s"`|给整个来源的时间加一个固定偏移。给该来源所有文件的分析时间加的偏移，可正可负。|校时得到的差值；原5秒加-2s得到共同3秒。|
|time.timezone|字符串|ASC absolute必填；CSV无时区日期需要时填写|不补时区|为绝对日期补充固定时区，例如UTC或+08:00。relative和numeric时间不填写。|采集地点/设备的时区设置；不能补造日期。|
|offsets|时间字符串数组|否|每个文件 `"0s"`|分别修正每个文件的时间起点。每个文件额外的分析时间偏移，数量须等于paths长度；实际加上time.offset和本项。|每份文件的起点差；与paths逐项对应，再叠加time.offset。|
|reader|对象|原始CSV必填；ASC可省略|ASC采用下方默认值|组织文本行格式或原始CSV列的解析规则。指定格式版本或CSV列和时间格式。|实际导出格式；不能照抄另一种日志的布局。|
|reader.decode_policy|字符串|否|strict|选择DBC解码时的异常处理方式。可填strict（默认）要求严格解码；partial允许部分解码；legacy采用已有解码策略。具体失败与缺值行为见[CAN解码策略](inputs.md#decode-policy)。|一般用strict；迁移明确需要时才选partial/legacy。|
|metadata|对象|否|`{}`|保存本来源的说明性备注。自由备注，不改变解码行为。|项目自定说明，例如记录仪型号；不影响解码。|

显式文件列表按给定顺序读取；目录或通配符取匹配文件并自然排序。默认来源可混合ASC/BLF；显式can_asc只选ASC。不会自动把回退时间改成下一天。比如第二个文件时间重新从0开始，而你知道它接在100秒处，就明确设置对应offset为100s。真实不连续试验应分开运行。

## ASC：常见格式直接读取

应用位置：以自己新建的分析文件为基础，在文件根级加入或替换`sources`，代码已包含父键。存在同名列表时按本例替换该列表，不把父键再嵌入列表项。 示例文件名是待替换的输入路径，须准备相应CSV/DBC/CAN数据；本块本身不是完整任务。

```yaml
sources:                 # 列出输入来源；每项规定数据位置、格式和时间解释方式
  - path: sample.asc     # 指定单个输入文件；相对路径从本配置文件所在目录计算
    dbc_by_channel:      # 为每个CAN通道指定解码用DBC文件；键是通道编号的字符串
      '1': sample.dbc    # 为这个通道指定DBC文件；路径相对当前配置文件，通道键须为字符串
```

下表位于`sources[].reader`；例如格式版本的完整路径为`sources[].reader.version`。

|ASC的reader字段|数据类型|必填|默认值|字段作用、可填内容与效果|取值依据|
|---|---|---|---|---|---|
|version|字符串|否|`"vector-asc-v1"`|选择ASC每行报文的排列规则。下面三种格式之一，根据文件中报文行的实际排列选择。|对照下面三种行示例和实际日志，不按文件名判断。|
|encoding|字符串|否|`"utf-8-sig"`|选择把文件字节解释成文字的编码。字符编码：utf-8、utf-8-sig、ascii、gbk、cp1252、iso8859-1及其标准别名。须与文件一致，不自动猜测。|导出软件的保存编码；未指定使用utf-8-sig。|

|reader.version|支持的文字排列及用途|
|---|---|
|vector-asc-v1（默认）|经典帧如`0.1 1 123 Rx d 1 FF`；FD如`0.1 CANFD 1 Rx 123 1 0 1 1 FF`|
|vector-asc-statistics-v1|上述经典帧允许严格匹配的`Length = … BitCount = … ID = …`统计尾部；末尾ID要与主字段一致|
|sclicer-asc-v1|FD排列如`0.1 CANFD 1 123 Rx 1 0 d 1 1 FF`；可混合经典帧|

ASC的time.unit默认s，通常不填写；显式填写也必须为s。reader还可设置encoding，默认utf-8-sig，不支持UTF-16/32。遇到不符合指定格式的行就失败，不依次尝试不同解析器直到某个成功。

ASC文字通道1在配置中填写1；ID后缀x表示扩展帧，不能只看ID数值大小猜扩展标志。FD的DLC码与实际字节数不同，例如DLC 10代表16字节、15代表64字节。FD零字节数据帧也不能自动当成远程请求帧。

ASC里有两个容易混淆的“绝对/相对时间”：

|出现位置|回答什么问题|
|---|---|
|文件头的 `timestamps absolute`|每行时间表示从日志块起点经过多久。例如0.1、0.2分别表示经过0.1秒、0.2秒。|
|文件头的 `timestamps relative`|每行时间表示距上一条又经过多久。程序需要逐条累加。|
|配置的 `time.time_type="absolute"`|分析时间是否对应具体年月日。程序会结合ASC头日期和你填写的时区计算。|

没有可靠采集日期时，配置采用relative，用共同起点后的秒数分析。不要用电脑今天的日期代替日志日期。

## 原始CSV：明确每一列代表什么

应用位置：以自己新建的分析文件为基础，在文件根级加入或替换`sources`，代码已包含父键。存在同名列表时按本例替换该列表，不把父键再嵌入列表项。 示例文件名是待替换的输入路径，须准备相应CSV/DBC/CAN数据；本块本身不是完整任务。

```yaml
sources:                        # 列出输入来源；每项规定数据位置、格式和时间解释方式
  - path: sample.csv            # 指定单个输入文件；相对路径从本配置文件所在目录计算
    source_type: raw_can_csv    # 选择数据格式；memory内存记录、signal_csv物理量表、can_blf/can_asc/raw_can_csv原始CAN
    dbc_by_channel:             # 为每个CAN通道指定解码用DBC文件；键是通道编号的字符串
      '1': sample.dbc           # 为这个通道指定DBC文件；路径相对当前配置文件，通道键须为字符串
    time:                       # 说明输入时间数值的类型、单位、共同起点和校准偏移
      unit: s                   # 声明输入时间数值的单位；根据文件说明填写s/ms/us/ns等受支持单位
    reader:                     # 设置当前来源的文本解析、列映射或解码行为；可用子字段取决于来源格式
      time_format: numeric      # 指定原始CSV时间文本格式；按文件的时间列格式填写
      id_base: 16               # 指定报文ID文本按几进制解释；从导出格式取得
      layout:                   # 说明原始CAN CSV如何组成每条报文
        fields:                 # 逐项指定报文时间、ID、数据字节及标志来自哪列或哪个固定值
          timestamp: time       # 指定报文时间如何从CSV取得；选择column读列或fixed固定值
          frame_id: id          # 指定报文ID如何从CSV取得；选择column读列或fixed固定值
          data: data            # 指定数据字节如何从CSV取得；选择column读列或fixed固定值
```

### reader：时间、ID和数据字节怎样读取

本节表中字段位于`sources[].reader`。其中`layout`还要再嵌套一层，不能把layout内的编码和分隔符平放在reader内。

报文里的数据字节也叫“载荷”，对应data字段。例如 `01 FF` 是两个字节；ID用来区分报文种类，不属于这些数据字节。

|字段|数据类型|必填|默认值|字段作用、可填内容与效果|取值依据|
|---|---|---|---|---|---|
|time_format|字符串|是|无|选择时间列的文字解析规则。numeric、clock、clock-ms-us-v1、iso8601四个值，逐值例子见下表。|对照下表四种真实文本形态选择。|
|layout|对象|是|无|组织CSV文件格式及报文字段到列的对应。表格的编码、分隔符和字段对应列；下方逐项说明。|CSV表头、分隔符、编码和设备导出说明。|
|id_base|字符串auto或整数10/16|否|auto|默认自动识别0x十六进制、0b二进制，无前缀按十进制。无前缀的十六进制日志须显式填16。固定整数不再按文字进制转换。|按原ID列格式；文字100默认为100，明确16时为256。|
|length_base|整数|否|10|选择长度或DLC文字的进制。10表示长度/DLC列按十进制读；16表示按十六进制读，如0x08。|长度列的实际写法，不随ID列进制自动变化。|
|channel_origin|整数|否|0|说明原始CSV数据列从0还是1编号。0表示原表第一路为0；1表示原表第一路为1。程序先转换为内部0基，配置的通道始终从1开始。|日志是否从0或1编号；填1时原表通道1匹配配置通道1；填0时原表通道0匹配配置通道1。|
|payload_style|字符串|否|`"spaced"`|选择字节之间有空白还是连续排列。`"spaced"`表示字节用空白分隔，如01 FF；`"contiguous"`表示连续偶数位十六进制，如01FF。|实际data单元格：01 FF选spaced，01FF选contiguous。|
|rollover_min_drop|时长字符串|否|不接受时间回退|设置把多大时间回退解释为跨到次日。仅clock或clock-ms-us-v1可填。大于0且小于86400秒；回退达到此阈值才认作跨到次日。例如12小时写 `"43200s"`，不是12h。|仅已知按日内时钟连续采集时，根据跨日规则填写；不能用来掩盖普通乱序。|

|time_format|输入例子|time设置与实际含义|
|---|---|---|
|numeric|`1500`|unit明确s/ms/us/ns；例如ms表示1.5秒，不按位数猜单位|
|clock|`14:05:40.1512`|time.time_type填 `"relative"`，time.unit填 `"s"`。从当天零点算起；小数部分为0.1512秒。|
|clock-ms-us-v1|`14:05:40.151.2`|time.time_type填 `"relative"`，time.unit填 `"s"`。末两段是151毫秒和2微秒，合计0.151002秒。|
|iso8601|`2026-10-23T14:05:40+08:00`|time.time_type填 `"absolute"`，time.unit填 `"ISO8601"`。文本已带北京时间偏移；若原文本没有时区，须另填time.timezone，例如+08:00。|

例如同一份连续记录从 `23:59:59` 跳到 `00:00:01`，时钟数字减少了接近24小时。明确设置 `rollover_min_drop="43200s"` 后，这种至少回退12小时的情况会按第二天处理，两个时刻实际相差2秒。未设置时会报时间回退错误；若只倒退了1秒，也不会因这个设置而被当作第二天。

### 最小列映射

常见表格只需对应时间、ID和数据列，不必给每列套column：

```yaml
sources:                        # 列出输入来源；每项规定数据位置、格式和时间解释方式
  - source_type: raw_can_csv    # 选择数据格式；memory内存记录、signal_csv物理量表、can_blf/can_asc/raw_can_csv原始CAN
    path: data/raw.csv          # 指定单个输入文件；相对路径从本配置文件所在目录计算
    dbc_by_channel:             # 为每个CAN通道指定解码用DBC文件；键是通道编号的字符串
      '1': network.dbc          # 为这个通道指定DBC文件；路径相对当前配置文件，通道键须为字符串
    time:                       # 说明输入时间数值的类型、单位、共同起点和校准偏移
      unit: s                   # 声明输入时间数值的单位；根据文件说明填写s/ms/us/ns等受支持单位
    reader:                     # 设置当前来源的文本解析、列映射或解码行为；可用子字段取决于来源格式
      time_format: numeric      # 指定原始CSV时间文本格式；按文件的时间列格式填写
      layout:                   # 说明原始CAN CSV如何组成每条报文
        fields:                 # 逐项指定报文时间、ID、数据字节及标志来自哪列或哪个固定值
          timestamp: time       # 指定报文时间如何从CSV取得；选择column读列或fixed固定值
          frame_id: id          # 指定报文ID如何从CSV取得；选择column读列或fixed固定值
          data: data            # 指定数据字节如何从CSV取得；选择column读列或fixed固定值
```

`timestamp: time`等同`timestamp: {column: time}`。整数字段简写如`timestamp: 1`表示第1列；常量必须写`{fixed: 值}`。唯一DBC通道自动补入；数据帧默认frame_kind=data，长度从实际字节数取得。方向省略保持未知，普通数值分析可以继续；要导出完整报文时必须提供真实方向。标准/扩展、CAN/FD标志只有在绑定与DBC足以唯一识别时才可省略。显式长度、帧种类或标志仍严格检查，不被默认值覆盖。

### layout：表头、编码和分隔符

本节字段位于`sources[].reader.layout`。原始报文CSV的编码与分隔符写为`sources[].reader.layout.encoding`和`sources[].reader.layout.delimiter`；已解码signal_csv则直接写在reader内，两种格式的布局不同。

|字段|数据类型|必填|默认值|字段作用、可填内容与效果|取值依据|
|---|---|---|---|---|---|
|fields|对象|是|无|逐一指定报文属性如何从列或固定值取得。每个报文字段对应一个取值对象，下一节逐字段列出。|对照下方报文字段表和原CSV列说明。|
|encoding|字符串|否|`"utf-8-sig"`|选择CSV字节到文字的编码。支持utf-8、utf-8-sig、ascii、gbk、cp1252、iso8859-1及其标准别名；按文件实际编码填写。|文件导出时使用的编码；不自动探测。|
|delimiter|字符串|否|`","`|指定分隔CSV列的单个字符。单字符分隔符；制表符写 `"\t"`。不能用换行、双引号或NUL作分隔符。|实际分隔字符；逗号或制表符等。|
|has_header|布尔值|否|`true`|控制是否把第一条未跳过记录当成列名。true表示第一条未跳过的记录是表头；false表示没有表头，column要填整数列号，不能填列名。|查看文件；有列名用true，没有表头用false并填写列号。|
|skip_rows|整数|否|0|控制从文件头跳过多少条CSV记录。从文件开头跳过多少条CSV记录，0～100000。例如文件头有两行说明文字，就填2；不会自动寻找表头。|数清真正数据/表头之前的说明记录数；0表示不跳过。|
|layout_version|字符串|否|`"raw-can-csv-layout-v1"`|声明列布局对象采用的结构版本。当前布局格式版本，填写这个值或省略即可。|当前固定raw-can-csv-layout-v1；来自本项目规定。|

本版没有可配置的quotechar或引号选项。标准CSV双引号由读取器处理；不能通过配置修改引号字符。

### fields：每个报文字段代表什么

字段完整路径为`sources[].reader.layout.fields.<报文字段>`，例如`frame_id: id`中frame_id是程序的报文字段，id是原CSV列名；不能把原表的id列改名为name。

下表的“读取后类型”是从列文字转换后应得到的类型。配置可直接填列名，也可用column/fixed对象；接收/发送、Rx/Tx可直接识别，特殊方向编码再用value_map。完整YAML例见本页下载配置。

|字段|读取后类型|是否需要配置|字段作用、可填内容与效果|取值依据|
|---|---|---|---|---|
|timestamp|字符串或整数|是|指定每条报文发生时间的取值方式。本行报文的时间；具体格式由time_format和time.unit决定。|时间列或有可靠依据的固定值；格式由time_format解释。|
|frame_id|字符串或整数|是|指定用于识别报文种类的CAN ID。CAN报文ID，文字按id_base解析。标准ID为0～2047，扩展ID为0～536870911。|ID列或该文件确定不变的ID；与DBC报文定义核对。|
|channel|字符串或整数|唯一DBC通道时可省略|指定报文来自哪个原始通道。原表的通道编号，按十进制读取，再减channel_origin；结果须非负。|日志通道列；确实只有一个固定通道时可用fixed。|
|is_rx|布尔值|普通分析可省略|true表示接收，false表示发送。Rx/Tx、接收/发送等常见文字自动识别；特殊编码用value_map。省略保持未知，不造出Rx。|完整原帧导出需要真实方向；缺少时提示补充。|
|is_extended|布尔值|可省略|指定报文使用标准还是扩展ID。false为标准帧，true为扩展帧。有列时采用原始信息；省略时通过本次绑定与DBC识别，无法唯一确定时要求补充。与信号定位统一使用is_extended。|日志真实标志；不是根据ID小于2048就认定标准帧。|
|is_fd|布尔值|可省略|指定报文是CAN FD还是经典CAN。true为CAN FD，false为经典CAN。有列时采用原始信息；省略时通过绑定与DBC识别，不能确定则要求补充。影响载荷长度和DLC解释。|日志真实帧型；不要按字节数或信号名猜。|
|frame_kind|字符串|否，默认data|指定数据帧、远程帧或错误帧。data为数据帧；remote为请求对端发送数据的远程帧；error为错误帧。各自长度要求见下文。|日志帧种类列及其编码表；恒定且已确认时可用fixed。|
|data|字符串|是|指定报文的数据字节文本。报文数据字节，例如 `"01 FF"` 或 `"01FF"`，格式由payload_style决定；空载荷用空字符串。|实际载荷列；不是解码后的电压、电流值。|
|payload_length|字符串或整数|数据帧可省略，按实际字节数取得|指定这条报文实际携带多少字节。实际数据字节数。经典帧0～8，FD最多64；若声明此项，必须等于data实际字节数。|实际长度列或经确认的固定长度；必须与data一致。|
|dlc_code|字符串或整数|数据帧可省略；remote必填|指定报文中的数据长度编码。数据长度编码。经典CAN为0～8；FD为0～15，9～15分别代表12、16、20、24、32、48、64字节。|原DLC列；FD编码9不等于9字节，具体对应见左侧说明。|
|bitrate_switch|布尔值|否，默认false|指定CAN FD的数据段是否切换速率。FD帧是否在数据段切换速率：true切换、false不切换。经典CAN填false。|日志BRS标志；按原编码转为true/false，不能由项目自行推断。|
|error_state_indicator|布尔值|否，默认false|指定CAN FD发送节点的错误状态标志。FD帧的错误状态标志：true表示错误被动状态，false表示错误主动状态。经典CAN填false；按日志实际标志映射。|日志ESI位；true被动、false主动，不是“本次分析是否出错”。|

省略类型列只适用于能够通过绑定与DBC取得唯一类型的分析入口。DBC标为FD仍可能对应实际经典CAN，不能仅凭DBC声明或短载荷断定；此时填写绑定的is_fd，或在原始布局中补充真实列／常量。独立原帧读取没有DBC信息时仍需提供类型；导出包含未绑定的报文，也必须具有其可靠类型信息。ASC和BLF自带的实际类型直接使用。

配置中的`frame_id`进制规则不改变ASC或CSV文件自己的ID格式：ASC无前缀文字可能表示十六进制，CSV仍按`id_base`解释。

数据帧的DLC与字节数须一致。remote必须是经典CAN，data为空，dlc_code明确给出请求长度；若另填payload_length，它为0，因为本帧没有数据字节。error必须data为空，DLC省略或为0。不能看到零字节就自动认作remote。

### 每个字段怎样取值：column、fixed、value_map、strip

这些字段位于一个列映射对象内部，例如`sources[].reader.layout.fields.is_rx.value_map`；不是直接放在layout或fields下。列名简写不需要对象，只有要配置这些额外取值规则时再展开。

|字段|数据类型|必填|默认值|字段作用、可填内容与效果|取值依据|
|---|---|---|---|---|---|
|column|字符串或整数|与fixed二选一|无|选择从哪一列取出字段内容。字符串是列名，如 `"方向"`；整数是1～4096的列号。整数1是第一列，字符串"1"是名为1的列。列名最多256字符。|复制实际表头，或按文件顺序填写从1开始的整数列号。|
|fixed|字符串、整数或布尔值|与column二选一|无|为每条记录提供相同的字段值。整份文件确定不变的值。例如确认全是接收帧时写 `{"fixed":true}`；不是用来掩盖未知标志的默认值。|仅从已确认恒定的采集条件取得，例如全部接收才填true；0、false、空文本是实际值。|
|value_map|对象或null|否|`null`，不映射|把取出的文本逐项转换为报文属性值。1～256项原文字到目标值的对应，如 `{"Rx":true,"Tx":false}`。原文字未列出时会报错。目标类型须符合上方字段，例如is_rx的目标是布尔值。|左侧取自文件实际文字，右侧取自上方属性允许值；例如Rx到true、Tx到false。|
|strip|布尔值|否|`true`|控制查表之前是否删除单元格两端空白。true去掉单元格两端空白后再映射；false保留两端空白。不会删掉载荷字节之间的空格。|默认true；只有边缘空白确实属于有意义编码时才选false。|

value_map的键和字符串目标最长256字符，fixed字符串最长16384字符；固定整数范围为−2⁶³到2⁶⁴−1，实际ID/长度等字段还有更小的范围限制。column与fixed不要同时填写。value_map也可用于固定文字，例如fixed="Rx"再映射为true，但直接写布尔固定值更清楚。

没用到的CSV列不参与解析，声明过的必需列缺失会报错。只计算所需报文、且无需完整原帧或全部来源时间时，原始CSV先看报文ID；不匹配的行跳过载荷和帧型，也通常跳过时间。若已启用跨午夜识别，仍会读取这些行的时间，以免漏掉换日、把下一天的报文归到前一天。目标行仍检查格式、时间和长度。需要完整原帧导出或全部来源时间时，则检查所有被读取的记录。错误会指出相关记录位置，修正输入后重新运行。

## 怎样选信号和查看来源

信号的field必填frame_id和signal，唯一DBC通道时可省略channel，帧型可以省略，逐项见[CAN信号定位](inputs.md#can-field)。不要只靠DBC信号名称定位；不同报文可以出现同名信号。输出来源信息的范围由所选分析和导出功能决定，不会为了说明来源额外保留未请求的记录。

有些报文会根据一个选择字段，在同一段字节里轮流传不同的信号。例如本帧传温度，下帧传电压，这称为DBC复用。若声明的温度字段在当前帧没有出现，程序会产生无效更新，不能继续把上一帧温度当作当前有效值。

其他有效记录仍受valid_for限制：超过有效期到下一次有效更新之间，数据是未知的。需要输出信号或原报文时，另配[两类导出](exports.md)；输入格式不决定输出格式。

底层读取器、逐字段参数、返回和异常见[ASCSpec/ASCRead](reference/chronaxis.sources.asc.md)、[CANCSVSpec/CANCSVRead](reference/chronaxis.sources.raw_csv.md)、[CANTextDecodeRead](reference/chronaxis.sources.text_can_decode.md)。通常使用AnalysisRunner即可，不必手工管理底层文件句柄。

## 无关报文的时间回退

默认`reader.input_check: auto`下，ASC只要求本次所需通道和报文ID的时间不回退。其他报文仍在同次读取中用于确定来源的最早/最晚观测时间，不因无关Tx帧的微秒回退中止分析，也不修改它的时间。`reader.input_check: full`或原帧导出需要完整顺序时，仍拒绝全来源回退。参与计算的报文和连续分卷之间的目标报文回退仍报错；程序不自动排序、钳平或清洗。

ASC头的relative表示每条记录的时间增量，读取时必须累加；这不同于分析配置time.time_type的relative时间基准。跨日期采用ASC明确日期/triggerblock，不把普通回退猜为跨日。原始CSV的时间布局和channel_origin仍按其文件声明解释。
