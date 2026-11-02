# CAN报文导出与重采样

`outputs.can_frames`从一个CAN来源导出原帧，或按明确的连续字段重建目标时刻的帧。共同范围、文件发布与当前环境限制见[输出配置](exports.md)。

## 完整最小例与网格扩展

[export-can-minimal.yaml](examples/export-can-minimal.yaml)包含joint.asc和joint.dbc的来源、voltage绑定及导出配置；[0,3)导出0、1、2秒的3条原帧，电压积分13V*s。

[export-can-grid.yaml](examples/export-can-grid.yaml)只增加500ms报文网格，重建DBC字段Voltage，其他位取基础帧。6个目标位置中，0、0.5、1、1.5、2秒可写出共5帧，2.5秒因范围内没有右端帧而跳过；积分仍为13V*s。

[export-can-all-windows.yaml](examples/export-can-all-windows.yaml)先定义电压大于5V的活动[1,2)，再定义活动窗口和向前1秒的窗口；can_frames使用scope: {windows: all}，分别导出两个窗口的片段。运行命令为`chronaxis run 文件名.yaml --output 新目录`，在exports.jsonl中按窗口/片段身份核对。

## 原CAN报文导出

下段是根级outputs片段；本例只有一个已配置DBC的CAN来源，无需再写source，报文ID及字段必须与实际DBC相符。当前还需满足[导出标签限制](exports.md)。若已有outputs，把can_frames合入同一映射，不能重复outputs键。

应用位置：以[dual-grid.yaml](examples/dual-grid.yaml)为基础，找到根级outputs，仅加入或替换其中的`can_frames`子项，保留outputs下其他子项；代码中的outputs只表示位置，不重复粘贴父键。保留未展示的其他根字段，不再添加第二个同名父键。

先运行最小配置；下方扩展配置增加可选控制。两段是替换关系，不同时重复写入同一个父键。

```yaml
outputs:           # 选择额外导出的数据及格式；默认结果表由运行入口提供
  can_frames:      # 配置原始或重建CAN帧的额外导出；与信号CSV分别设置
    format: asc    # 选择输出报文文件格式；asc为文本，blf为二进制
```

### 扩展设置

仍以同一基础文件为起点，用下面的can_frames子项替换上面同名子项，仍保留outputs下其他子项；新增字段的默认值、适用条件见后文。

```yaml
outputs:                           # 选择额外导出的数据及格式；默认结果表由运行入口提供
  can_frames:                      # 配置原始或重建CAN帧的额外导出；与信号CSV分别设置
    format: asc                    # 选择输出报文文件格式；asc为文本，blf为二进制
    resampling:                    # 设置重建CAN帧网格；根据DBC重写选定信号，其他位取基础帧
      period: 500ms                # 指定重建CAN帧的网格周期；与信号CSV网格独立
      max_gap: 2s                  # 限制重建帧使用的记录间隔；超过上限不伪造连续数据
      messages:                    # 逐报文列出要重建的连续信号和保留字段
        - frame_id: 0x100          # 选择要重建的报文ID；从DBC取得
          continuous: [Voltage]    # 填写允许线性插值的DBC信号名；不是signals中的分析别名
```

下表字段相对于`outputs.can_frames`；例如format完整写作`outputs.can_frames.format`。

|can_frames字段|数据类型|必填|默认值|可填写的值与含义|
|---|---|---|---|---|
|source|字符串|多个CAN来源时必填|唯一CAN来源自动采用|选择要导出的原始CAN来源；从sources[].name取得。已有asc_or_blf、can_blf、can_asc或raw_can_csv来源名，例如 `"bus"`。|
|format|字符串|是|无|选择输出文件格式；按后续读取工具的支持情况选择。`"asc"`输出文本CAN日志；`"blf"`输出二进制BLF日志。|
|scope|字符串或对象|否|`session`|选择要导出的时间范围。整会话用session；单窗口用`{window: context}`；全部窗口用`{windows: all}`。窗口名称来自windows[].name，见[共同范围](exports.md#export-scope)。|
|resampling|对象或null|否|`null`|控制保留原帧还是生成等间隔重建帧。省略或null保留原帧；填写对象则按下面的报文规则重新生成等间隔帧。|
|output_offset|时间字符串|否|`"0s"`|平移输出报文时间；根据原采集时间与目标时间的已知关系填写。给导出的原报文时间另加偏移，可正可负。它不修改分析时间；例如相对采集时间要加8小时，写 `"28800s"`。|
|source_time_reference|字符串|否|绝对时间来源为epoch，相对时间来源为relative|声明原始报文时间的基准；从采集记录或日志格式说明取得。`"relative"`表示原时间是相对某个起点的秒数；`"epoch"`表示原时间已从1970-01-01 UTC起算。根据原数据含义填写，不按数字大小猜测。|
|capture_date|字符串或null|相对时间输出BLF时必填|`null`|提供相对时间转日历时间所需日期；从实际试验记录取得。实际采集日期，格式 `"YYYY-MM-DD"`，例如 `"2026-10-23"`。须与timezone一起填写；epoch时不填。|
|timezone|字符串或null|填写capture_date时必填|`null`|声明capture_date所用的采集地固定时区，例如`+08:00`或`UTC`，与来源time.timezone使用相同写法；不按当前电脑地区猜测。|

不设置resampling就保存范围内原报文，包括DBC未定义的ID和同刻的不同帧。公开执行路径输出`frames.asc`或`frames.blf`及该导出的`manifest.json`，不生成`frames.jsonl`原帧副本。配置了重采样后，只对messages中明确列出的报文及其continuous字段重新取值；这里的Voltage是**DBC字段名**，不是分析别名voltage。

下表字段相对于`outputs.can_frames.resampling`。

|can_frames.resampling字段|数据类型|必填|默认值|可填写的值与含义|
|---|---|---|---|---|
|period|正时长字符串或映射|是|无|规定重建帧时间网格的周期；按输出要求选择固定时长，或按每条报文DBC周期。固定周期例如`500ms`；`{mode: dbc}`按各目标报文的DBC周期生成网格，不接受driver。可以与信号导出周期不同。|
|start|时间字符串|否|`"0s"`|设置CAN网格的共同参考起点；按输出对齐目标填写。报文网格参考起点，计算方式与信号网格相同，但独立设置。|
|max_gap|时长字符串|是|无|限制连续信号插值跨越的原始帧间隔；按允许缺测时长填写。大于0；为已配置连续字段作插值时，两端实际帧最多相隔多久。|
|messages|对象数组|是|无|组织允许重建的报文及可修改字段；从DBC和业务重建需求取得。最多4096项，每项指定一类报文及可改动信号，逐字段见下一表；同一报文身份不能重复。只有unknown_policy为nearest时可以为空数组。|
|unknown_policy|字符串|否|`"passthrough"`|控制未列入messages的报文怎样输出。`"passthrough"`：没有列入messages的报文按原时间原样保存；`"nearest"`：在每个网格点挑一条最近的原帧整帧保存，不插值它的字段。|
|max_distance|时长字符串|nearest时必填；passthrough可省略|未设置|限制nearest选帧能距离目标时刻多远；按时间误差容忍度填写。大于或等于0；最近帧离目标网格点最多多远，超出就不生成。0表示必须恰好同刻。passthrough不使用这一距离；nearest没有默认距离，必须明确填写。|

当period填写对象时，仅允许`period: {mode: dbc}`；它为messages中每类报文分别读取自己的DBC周期，不接受driver键。不能把信号CSV的period.driver照搬到CAN导出。DBC缺少有效周期时运行初始化失败，不自动改用固定周期。

### messages每一项的七个字段

这些字段写在`outputs.can_frames.resampling.messages[]`，即上例messages数组的每一项。报文身份的含义与[CAN信号定位](inputs.md#can-field)相同，但这里不填写signal；要重算的DBC信号放进continuous。

|字段|数据类型|必填|默认值|含义与例子|
|---|---|---|---|---|
|channel|正整数|否|沿用所选来源通道|定位重建报文所在通道；从采集通道和DBC对应关系取得。从1开始的用户通道编号，须与来源DBC通道相同，例如1；底层原帧编号由程序转换。|
|frame_id|整数或字符串|是|无|定位要重建的报文；从DBC取得ID。支持十进制、0x十六进制和0b二进制；JSON带前缀时使用字符串。标准ID最多2047，扩展ID最多536870911。|
|is_extended|布尔值|否|自动识别|限定标准ID或扩展ID；按实际帧型填写。false限定标准帧，true限定扩展帧；省略时从DBC及实际报文识别，显式null无效。|
|is_fd|布尔值|否|自动识别|限定经典CAN或CAN FD；按实际帧型填写。false限定经典CAN，true限定CAN FD；省略时保留实际帧型，显式null无效。|
|continuous|字符串数组|是|无|选择允许线性插值的DBC字段；查DBC信号定义和设备物理含义。1～4096个可插值的DBC信号名，不是分析别名。例如 `["Voltage"]` 表示只重新计算Voltage所占的位。|
|protected|字符串数组|否|`[]`|列出禁止插值的DBC字段；按状态、计数器和校验码定义填写。明确禁止插值的DBC信号名，例如 `["Counter","Checksum"]`。这些名称须在DBC中存在，也不能出现在continuous中。|
|same_time_policy|字符串|否|`"error"`|控制同一时刻的冲突原帧是否允许作为插值依据；根据冲突处理要求选择。`"error"`：同一时刻有冲突帧时不据此插值；`"last_by_sequence"`：依据原读取顺序采用最后一条。冲突不能被默认当作“更准确”的新值。|

**protected的用途：** 它是一份明确的禁止改动清单，防止误把计数器或校验码同时选进continuous。即使protected为空，未列入continuous的位也会保留基础帧原值；不是“未写protected就会被全部插值”。上例只重建Voltage，省略protected即使用空数组；Counter、Checksum只是名称示意，实际填写时须换成你的DBC中确实存在的字段。

生成一条新报文时，程序按以下步骤处理：

1. 找到离目标时间最近的一条原报文；前后一样近时选较早的一条。它作为新报文的基础。
2. 按前后记录估算continuous中指定的连续量，只替换这些信号占用的位。
3. 其余位都保留同一条基础报文的原值，包括状态、计数器、校验码和DBC没有定义的位。

例如目标时间为100ms，原报文在80ms和120ms各有一条，两者一样近，就以80ms报文为基础。电压可以重新估算，但计数器和状态仍取80ms那一条。

布尔值、枚举以及决定复用分支的选择字段不能放进continuous。若前后报文使用不同的复用分支，或缺少可靠记录、间隔超过max_gap，也不能在两帧之间插值。

整数DBC字段按nearest_even-v1取整，即恰好半格时取偶数；例如码值2.5取2、3.5取4。超出码值范围会拒绝，不截断成合法值。生成帧保留原校验码而不重算，因此**不能据此保证可直接回放到真实设备**。清单记录observed、estimated以及未生成的原因。

同一自动规则若匹配到两种实际帧型，会提示补充相应类型选项；不会把标准帧重建成扩展帧，也不会因为DBC标为FD而把经典CAN改成FD。报文名称由已加载的DBC取得，不再填写`message`。

## 无日期数据输出BLF

BLF需要日历时间。假设确知试验在2026年10月23日北京时间08:00开始，原报文从0秒计时，可以这样填写：

应用位置：以[dual-grid.yaml](examples/dual-grid.yaml)为基础，找到根级outputs，仅加入或替换其中的`can_frames`子项，保留outputs下其他子项；代码中的outputs只表示位置，不重复粘贴父键。保留未展示的其他根字段，不再添加第二个同名父键。

```yaml
outputs:                          # 选择额外导出的数据及格式；默认结果表由运行入口提供
  can_frames:                     # 配置原始或重建CAN帧的额外导出；与信号CSV分别设置
    format: blf                   # 选择输出报文文件格式；asc为文本，blf为二进制
    capture_date: '2026-10-23'    # 提供相对时间输出BLF的采集日期；与timezone及output_offset共同定位日历时间
    output_offset: 28800s         # 给导出时间增加固定偏移；按目标文件的时间基准填写
    timezone: +08:00              # 声明采集日期的时区偏移；按采集记录填写如+08:00
```

这里日期先定位到当天零点，再加28800秒，得到08:00。这个日期仅展示格式，实际填写采集日期。若原时间已经是从1970-01-01 UTC起算的绝对时间，则选择epoch，并省略capture_date及timezone。

如果原始日内时间已经是14:05:40，不能再加一次14小时；如果原始时间从试验开始计0，才按真实开始时刻补偏移。分析用time.offset解决来源间对齐，不自动改原报文的导出时刻。这些字段的类型与组合检查见[FrameExportSpec](reference/chronaxis.results.frame_exports.md#api-FrameExportSpec)。

## 使用DBC周期的完整导出例

下载[完整配置](examples/dbc-grid/analysis.yaml)、[grid.asc](examples/dbc-grid/grid.asc)和[grid.dbc](examples/dbc-grid/grid.dbc)，三者放在同一目录，运行`chronaxis run analysis.yaml --output grid-result`。

本例同时导出power和voltage。DBC分别声明Power报文1000ms、Voltage报文500ms，输入在0、1、2秒更新。信号CSV只有一套网格，period.mode=dbc且driver=power明确选择1000ms；连续量涉及两个物理报文，删除driver会因多个候选而报错，不会任选一个周期。

CAN导出使用每条报文自己的DBC周期，因此period只写mode=dbc，不填driver：Power按1秒、Voltage按0.5秒生成。两类输出分别配置，选择信号网格驱动不会改变CAN各报文周期。观测范围为[0,2)，范围末端及缺右侧有效样本时的处理沿各导出规则；应同时查看导出数据和manifest中的生成/跳过计数。

本例[信号CSV](examples/dbc-grid/results/resampled.csv)在0、1秒分别输出power=10/20W、voltage=20/30V，共4行。[重建ASC](examples/dbc-grid/results/frames.asc)共5帧：Power在0、1秒，Voltage在0、0.5、1秒（20、25、30V）。Voltage的1.5秒网格点需要右侧2秒样本，但2秒是请求范围的排除端点，不能从范围外借该样本，因此跳过1点。两类输出行数不同是各自网格规则的结果。
