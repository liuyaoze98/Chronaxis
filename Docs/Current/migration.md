# 旧INI导入

将现有业务INI转换成当前分析配置时，需要额外提供信号绑定、单位和模式含义。入口为`chronaxis legacy import`；常规分析命令见[命令行参考](cli.md)，当前消息累计功能见[逐消息累计](message-calculations.md)。

<a id="import-mapping"></a>
## 用mapping文件说明旧变量对应什么新信号

这是迁移映射文件，和生成后的普通分析配置不同：mapping_version、analysis、sections在映射根级；段内字段位于`sections.<旧INI段名>`，例如`sections.TRIGGER_1.name`。analysis内部才使用普通配置的dataset、sources、signals等结构。

```powershell
python -m chronaxis legacy import old.ini --mode legacy_sum --mapping mapping.yaml --output converted.json
```

导入器目前将生成计划写为JSON文件，--output须使用.json扩展名；这是该导入命令的输出限制，普通分析和mapping输入支持YAML。若需继续手写YAML，可执行`chronaxis config convert converted.json --output converted.yaml`，再运行converted.yaml。输出文件必须尚不存在。

mapping说明旧配置里的变量究竟对应哪个输入、哪个信号，以及转换后各条规则叫什么。仅mapping_version和analysis必填；其他字段按下表需要填写：

|字段|数据类型|填写内容及含义|
|---|---|---|
|mapping_version|整数|声明映射文件的字段结构版本；当前填写整数`1`，由本版本格式约定取得。|
|path_base|字符串|选择相对路径的解释基准；省略采用`"mapping_directory"`，这也是唯一支持值：analysis中的相对输入路径以mapping.yaml所在目录为起点；生成计划时会转成绝对路径。|
|io_policy|字符串|选择转换后的输入输出设置来自哪里；省略采用`"explicit_mapping"`，这也是唯一支持值：使用analysis里明确写出的输入和输出设置，旧INI里的INPUT/OUTPUT路径保留在报告中，不直接沿用。|
|analysis|对象|提供转换后的基础[分析配置](configuration.md)，写好dataset、sources、signals等字段。rules、windows、message_calculations、presets省略或填空数组，由转换器生成；不能预先放入其他规则。|
|aliases|对象|把旧表达式变量绑定到新信号。键从旧INI表达式取得，值是analysis.signals中的新信号名。例如`{"BMS_BatCurr":"current"}`。两端都是字符串；不同旧名字可以指向同一新信号。可省略：旧变量名与一个信号的原字段名唯一对应时自动映射；多个来源含同名字段时必须显式选择，不能猜测。|
|sections|对象|为每个旧分析段指定新节点和转换规则。键从旧INI的段标题取得，值是该段的转换设置。例如`"TRIGGER_1":{"name":"working","window":"context"}`。显式填写时必须逐段对应，不能漏段或增加不存在的段。single、start_only、start_end可整个省略，程序按INI顺序生成trigger_1/window_1等名称。legacy_sum和slope仍需提供计算单位或模式参数。|

显式提供sections时按所选模式填写对应一行的字段，不混用其他模式。省略start_end的sections时，采用已经确定的start_end_timeout-v1及emit_initial=false；仍由--mode明确选择起止转换。

|mode|每段需要的字段|
|---|---|
|sclicer_single、sclicer_start_only|name、window|
|sclicer_start_end|name、window、semantics、emit_initial|
|sclicer_slope|name、window、coverage_policy、emit_initial、retrigger|
|legacy_sum|name、source、unit、message_policy、update_message、parameter_units|

|段内字段|数据类型|填写内容及含义|
|---|---|---|
|name|字符串|命名生成的规则或指标；自行取唯一名字，例如`working`。须符合[名称格式](configuration.md)，且生成的节点不能重名。|
|window|字符串|命名生成的窗口；自行取唯一名字，例如`context`；与规则的name不同。|
|semantics|字符串|选择起止规则转换后的时间语义。目前仅支持`"start_end_timeout-v1"`：采用“start成立后开始记录，end成立后结束，时限从start起算”的新行为；与旧模式的差异见下方说明。|
|emit_initial|布尔值|控制初次观测已经满足条件时是否触发事件。`false`：首次看到的状态已经满足开始条件时，不因此触发；`true`：把首次满足也作为触发。slope中它作用于第一次能完整计算的窗口。|
|coverage_policy|字符串|选择变化量窗口的数据覆盖要求。目前仅支持`"full"`：要求整个回看窗口都有可用信号；旧版仅有两个点就计算的方式尚不支持。|
|retrigger|字符串|控制变化条件再次成立时是否允许再次触发。`"edge"`：满足变化条件后触发，条件先变为不满足、再满足时可再次触发；`"once"`：本次分析最多触发一次。|
|source|字符串|选择逐消息分析的原始报文来源；填写analysis.sources中已声明的name，例如`bus`。|
|unit|字符串|声明旧公式累计结果的单位；根据公式与参数单位推导，例如`J`；必须与实际表达式计算出来的单位一致。|
|message_policy|字符串|选择每条目标消息使用的数据范围。目前仅支持`"current_message-v1"`：每条目标消息只使用它自身携带的解码值，不沿用上一条消息的值。|
|update_message|对象|选择触发一次计算的报文；frame_id必填；channel省略时沿用所选来源通道，is_extended和is_fd可省略，见[逐消息累计](message-calculations.md)。|
|parameter_units|对象|声明旧公式中固定参数的物理单位，供转换后的表达式检查单位关系。为旧period、factor、global中每个参数分别写单位，键与原参数名完全对应，值为字符串。例如`{"period":"s","factor":"1"}`。不能漏项或多填。|

完整输入示例见[INI导入模板](examples.md)。analysis支持与普通分析相同的组式signals。原始CAN缺省dtype、unit、通道等可从指定DBC唯一确定时自动补全，valid_for沿用周期的三倍默认规则；这时会读取DBC元数据。完整显式声明不新增DBC读取。已解析表缺少DBC，仍须提供dtype和unit。无法唯一确定的来源、别名、计算单位和slope参数会报错，不能凭变量名字猜测。

## 逐消息能量迁移的完整示例

下载[旧INI](examples/migration-sum/energy.ini)和[映射配置](examples/migration-sum/mapping.yaml)，保留随册examples目录结构；输入是[data/message-clean.asc](examples/data/message-clean.asc)与[data/power.dbc](examples/data/power.dbc)。旧文件中的旧路径只保留作来源记录，explicit_mapping明确采用映射文件中的新路径。

|旧INI字段|业务含义与单位来源|映射/转换后对应项|
|---|---|---|
|signal_P=Power|从DBC取得功率信号名，单位W|aliases.signal_P=power，analysis.signals定义power绑定|
|period=0.1|旧公式约定每条报文代表100ms，即0.1s；来自采集和业务约定|parameter_units.period填s；生成parameters.period.value=0.1、unit=s|
|expr=signal_P * period|单次功率乘固定时长得到能量|生成expr为power * period；结果unit填J|

parameter_units只声明单位，不换算旧数值。若旧INI实际写period=100且单位为ms，应填写ms，不能填s。这里的period常量不会自动读取signals.period，也不采用两条报文的实际时间差。

在仓库根执行（sum-import.json及其同名前缀产物和sum-result目录须不存在）：

```powershell
chronaxis legacy import Docs/Current/examples/migration-sum/energy.ini --mode legacy_sum --mapping Docs/Current/examples/migration-sum/mapping.yaml --output sum-import.json
chronaxis run sum-import.json --output sum-result
```

实际输出：[计算表](examples/migration-sum/results/会话结果.csv)。

每条4000W报文贡献4000×0.1=400J；本例两条4000W记录虽同在0秒，仍各贡献400J，最后一条0W贡献0，总计800J。检查生成配置的message_calculations、会话结果.csv中的energy（J）=800及状态“完整”，不用日志时间差替换固定常量。

漏写period的单位、增加INI里不存在的参数单位、把结果单位填成与公式不符的A，都应使导入失败；查看报告中的段名、字段路径和错误说明，修正后重新转换。不能用改变结果单位掩盖公式量纲错误。

<a id="import-modes"></a>
## 选择导入模式

|mode|本版会生成什么|使用时需要注意|
|---|---|---|
|legacy_sum|逐条目标消息求值并累计；也可按方向分别统计。|每次只使用当条消息的值。旧程序跨消息保留前值的缓存行为没有一起迁移。|
|sclicer_single|记录每次活动，并按pre向前取数据、按退出等待时间向后取数据。|到指定结束时刻就结束片段，不等下一条报文；两次活动仍分别记录。|
|sclicer_start_only|条件从假变真时记一个点，再取固定时长的窗口。|窗口到期后，条件如果一直为真，不会自动再触发。|

另外支持sclicer_start_end和sclicer_slope，差异见下文。遇到不支持的表达式或缓存用法时，整个转换失败；报告指出哪一段、哪个键需要修改，不输出一份仅转换部分内容却标为成功的计划。

转换成功后，仍需运行validate、explain和run，检查新配置是否适合实际输入。

### 起止与变化量转换模式

|mode|必须明确的含义|输出及差异|
|---|---|---|
|sclicer_start_end|显式sections时填写`semantics="start_end_timeout-v1"`和布尔emit_initial；整个省略sections采用该含义且emit_initial=false|start启动、end结束；旧实现是start准备、end才开始切片，两者的起止含义不同，使用sclicer_start_end即采用已确定的新含义；旧正duration_sec变timeout，非正变无限等待；pre保留，旧未使用的post不加上|
|sclicer_slope|逐段明确name、window、coverage_policy=full、emit_initial、retrigger|`_slope_`变单调window_delta，`_slope2_`不要求单调；按完整窗口计算，与旧“至少两点”不同|

例如 `_slope_rise_4s_BMS_SOC_raw_5` 中，BMS_SOC_raw是完整信号名。转换器会在aliases中查找这个名字，不会把它错误拆成BMS、SOC、raw三部分。无法解释的多余尾部会使转换失败。

变化量转换采用完整4秒窗口；旧版“窗口里只要有两点就计算”的legacy_samples方式仍未支持。五种模式都使用legacy import命令，每次通过--mode明确选择一种。完整mapping与例子见[示例与模板](examples.md)。

Python对应入口为[import_legacy_ini/load_legacy_ini](reference/chronaxis.migration.api.md)和[write_legacy_import](reference/chronaxis.migration.publication.md)。原INI字节、报告和成功计划分别保存。

## 导入报告的设备来源标签

CLI从环境变量`CHRONAXIS_DEVICE_LABEL`取得导入报告的设备标签，去掉两端空白；未设置或为空时使用pending。这个标签由执行环境的使用者提供，只用于追溯，不会更改analysis.metadata，也不证明真实数据已验证。PowerShell中可先执行`$env:CHRONAXIS_DEVICE_LABEL = 'home'`，前提是home确实代表当前设备。Python的load_legacy_ini通过device_label参数显式接收该值，不自动继承CLI环境处理。
