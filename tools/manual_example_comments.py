"""人工编写的示例字段职责；按完整配置路径匹配，未知字段拒绝生成注释。

只服务手册YAML示例。注释解释字段职责及取值依据，具体边界由对应功能参考说明。
同名字段在信号、规则、导出等不同结构中分别登记，不按短名称猜测用途。
"""
import re

COMMENTS = {}


def register(prefix, rows):
    """参数: 父路径和逐行键/说明。返回: None。异常: 重复路径拒绝。"""
    for line in rows.strip().splitlines():
        key, description = line.split('|', 1)
        path = prefix + key
        assert path not in COMMENTS, path
        COMMENTS[path] = description


register('', '''
config_version|声明分析配置结构版本；当前必须填写整数4
dataset|声明分析对象、会话身份和本次请求的时间范围
sources|列出输入来源；每项规定数据位置、格式和时间解释方式
signals|把输入字段定义为有名称、类型、单位和有效期的分析信号
derived|用已定义信号的表达式生成新信号；先定义再在后续功能中引用
rules|列出识别活动或瞬间变化的规则；每项产生有独立ID的事件
windows|围绕已定义规则的事件选取时间片段，供计算或导出使用
sequences|把请求事件与响应事件按允许等待时间配对
calculations|列出希望获得的统计或积分结果，每项独立选择范围和算法
transforms|声明有时刻、单位和有效性的网格输出或相邻变化率
lookups|声明表达式lookup可引用的标定表，每项列出输入点和对应输出值
aggregations|选取本分析已生成的具名结果，在各组内归约并保留总体计数
message_calculations|按每条目标CAN报文计算贡献再累计；与按实际时间积分分别配置
presets|选择预先组合好的规则与计算，并提供角色信号和业务参数
intervals|选择时间计算使用实际间隔还是指定周期；不修改原记录时间
execution|设置计算实现、资源上限和数据不全时的处理方式
diagnostics|选择是否额外记录定位信息、校验摘要以及保留临时数据
outputs|选择额外导出的数据及格式；默认结果表由运行入口提供
imports|先加载公共定义文件；列表项为相对当前配置文件的路径
metadata|保存说明性信息；字段不会自动校准数据或更改计算公式
batch_version|声明独立批量任务文件的结构版本；当前填写整数1
jobs|列出互相独立的分析任务，每项引用一份分析配置
process_count|限制分析工作进程数；填正整数，1表示一个工作进程依次执行
fail_fast|控制某任务失败后是否停止启动后续任务；true停止，false继续
backend|为批量任务指定计算实现；numpy用数组计算，reference用参考实现
reader_options|在CAN来源中设置解码处理选项；不是通用执行参数
reader_options.decode_policy|选择异常CAN帧的处理策略；不同读取路径的允许结果见输入指南的解码策略表
''')
register('dataset.', '''
id|为这一组输入取一个可追溯名称；自行命名，结果中保留
entity|填写被分析的设备、样品或对象编号；来自试验记录
session|填写本次连续采集或联合分析会话的名称；来自采集记录
domain|限定本次分析请求的起止时间；应与来源采用相同时间基准
domain.start|设置分析起点，包含该时刻；按希望分析的范围填写
domain.end|设置分析终点；连续时长不包含该端点，按希望分析的范围填写
''')
register('sources[].', '''
file_merge|选择文件记录组合顺序；concatenate按文件接续，time_order按共同时间稳定归并，不平移或去重
name|给本来源取计划内唯一名称；下方signals.source引用这个名称
source_type|选择数据格式；memory内存记录、signal_csv物理量表、can_blf/can_asc/raw_can_csv原始CAN
path|指定单个输入文件；相对路径从本配置文件所在目录计算
paths|指定文件、目录或通配符；同次记录分卷放在同一来源，ASC和BLF可混用
time_column|填写CSV时间列的实际表头，大小写和文件一致
time|说明输入时间数值的类型、单位、共同起点和校准偏移
time.time_type|选择时间类型；relative为距共同起点的时间，absolute为日期时间或UTC纪元时间
time.unit|声明输入时间数值的单位；根据文件说明填写s/ms/us/ns等受支持单位
time.origin|命名相对时间的共同起点；来自同步依据，同名不会自动校时
time.offset|给换算后的时间加固定偏移；依据时钟校准结果填写，不是数值偏移
rows|提供内存来源的记录列表；每条记录含时间及该时刻的字段值
rows[].time|填写本条合成记录的发生时间，按本来源的time声明解释
rows[].values|列出本条记录实际更新的原字段及值；字段名供signals.field选择
encoding|指定CSV文本编码；根据文件保存方式选择，如utf-8
sep|指定CSV列分隔符；填写文件实际使用的单字符，如逗号
missing_values|列出CSV中表示缺失的文本；遇到它们产生无效更新，不按零计算
dbc_by_channel|为每个CAN通道指定解码用DBC文件；键是通道编号的字符串
input_check|选择输入时间检查范围；auto按所请求功能决定，full检查完整来源时间
decode_scope|选择解码范围；requested解码任务需要的报文，all请求全量解码检查
legacy_profile|选择单BLF的读取规则；sclicer-functions-v1使用当前封装的单BLF路径
reader_options|设置本CAN来源的解码策略；不改变普通信号计算方法
reader_options.decode_policy|选择异常CAN帧的解码检查规则；legacy保留既有链对异常帧的处理
parser|说明CAN文本文件的解析格式及列布局，须与文件实际格式一致
parser.version|选择受支持的文本格式版本；ASC示例使用vector-asc-v1
parser.encoding|声明文本日志的字符编码；从文件导出设置取得
parser.channel_origin|声明文本通道编号从0还是1开始；从日志格式说明取得
parser.id_base|指定报文ID文本按几进制解释；从导出格式取得
parser.length_base|指定长度文本按几进制解释；从导出格式取得
parser.payload_style|指定数据字节文本的排列形式；须与实际列内容一致
parser.time_format|指定原始CSV时间文本格式；按文件的时间列格式填写
parser.layout|说明原始CAN CSV如何组成每条报文
parser.layout.fields|逐项指定报文时间、ID、数据字节及标志来自哪列或哪个固定值
''')
register('signals[].', '''
name|给分析信号取名称；后续表达式和计算通过此名称引用它
source|选择已定义的来源name；填写上方sources中的名称，不是文件路径
field|指定来源中的原始字段；CSV填表头，CAN填写通道/报文ID/DBC信号名
field.channel|选择信号所在的CAN通道；从日志通道记录取得
field.frame_id|选择包含信号的报文ID；从对应DBC取得，可写整数或支持的进制文本
field.signal|填写DBC中的信号名称，大小写须一致
dtype|选择分析值类型；float64小数、int64有符号整数、uint64非负整数、bool真假、enum状态名称
unit|声明分析值的单位；按物理含义填写，无量纲用字符串"1"；按已登记的兼容单位换算数值
input_unit|声明CSV解析或DBC解码后、额外换算前的单位；查列说明或DBC物理单位
scale|设置额外数值乘数；按输入与目标单位的合法换算倍率填写，避免重复DBC换算
offset|设置乘法换算后再加的数值；已知单位换算要求0，不是时间偏移
valid_for|设置一次有效更新最多沿用多久；依据采样周期和允许数据陈旧程度填写
valid_range|检查换算后的值是否在含两端的上下限内；按传感器或业务允许范围填写
invalid_values|列出解析/解码后、额外换算前表示无效的值；按数据规范匹配实际类型和值
choices|把输入状态代码转成分析值；每项是[输入代码,结果值]，代码查设备规范
same_time_policy|处理同信号同刻更新的冲突；error拒绝不一致内容，last_by_sequence保留最后稳定序号
sign_convention|声明正负值的业务含义；positive_is_charge表示正电流为充电，不执行取反
measurement_location|声明实际测点；pack_terminal表示电池包端，须依据接线和设备定义
semantic_id|声明信号的业务用途；自动选预设角色时按角色表填写，普通计算可省略
semantic_contract_version|声明业务用途采用的约定版本；预设自动查找填字符串"1"并同时提供semantic_id
period|声明本信号正常更新周期；从设备/采集规范取得，省略valid_for时按其3倍确定有效期
''')
register('rules[].', '''
id|为规则取唯一名称；窗口rule和计算scope通过此名选择它的事件
rule_type|选择如何识别持续活动或瞬间变化；具体行为由所选算法决定
condition|填写由已定义信号组成的真假条件；按要检测的业务情况设置
minimum_duration|设置条件连续成立多久才确认活动；时长阈值由业务要求决定
duration_comparison|选择持续时长比较；>=包含相等边界，>为严格超过且不含相等边界
selection_origin|选择活动计算起点；onset包含确认前等待，confirmed从确认时刻起算
emit_initial|控制初始已为真时是否发出初始事件；true发出，false等待实际变化
start_condition|设置开始活动的条件；引用上方定义的信号
end_condition|设置结束活动的条件；引用上方定义的信号
enter_condition|设置进入活动的条件；与退出条件分别判断
exit_condition|设置退出活动的条件；按恢复要求填写
enter_delay|设置进入条件需连续成立的等待时间；0s表示不额外等待
exit_delay|设置退出条件需连续成立的等待时间；0s表示不额外等待
timeout|限制一次活动的最长等待/持续时间；达到上限按规则结束
retrigger|选择变化量条件再次成立时是否触发；edge每次由不满足变满足触发，once每会话最多一次
signal|选择用于变化量判断的分析信号；填写上方signals中的名称
window|设置向前比较变化量的时间窗口长度；依据业务变化尺度填写
threshold|设置触发变化的幅度门槛；数值单位与所选信号一致
direction|选择变化方向；rise检测上升，fall检测下降，any检测任一方向的幅度
monotonic|控制窗口内是否要求持续同向变化；true检查，false仅检查规定的变化幅度
coverage_policy|设置变化窗口的观测要求；当前只能填full，窗口整个时段须有有效数据
window_duration|设置start_only一次触发后抑制新触发的时长；配套窗口post必须与此值相等
''')
register('windows[].', '''
exit_delay|设置活动结束后继续等待下一活动的时长；仅merge=exit_delay使用，且post须为0s
id|为窗口定义取唯一名称；计算或导出通过此名选择产生的片段
event|选择产生片段的规则；填写前面rules的name
anchor|选择以事件点还是活动区间为基础；point围绕点，activity围绕活动
pre|设置起点之前保留多久上下文；0s表示不提前
post|设置结束点之后保留多久上下文；0s表示不延长
merge|选择片段合并规则；none分别输出，overlap合并重叠，overlap_and_adjacent也合并相邻，exit_delay等待下一活动
''')
register('sequences[].', '''
id|为请求响应配对取唯一名称；结果通过此名区分配对任务
start|选择请求事件规则；填写前面rules的name
response|选择响应事件规则；填写前面rules的name
min_delay|设置响应的最小允许延迟；依据协议或业务要求填写，包含边界
max_delay|设置响应的最大允许延迟；依据协议或业务要求填写，不能小于min_delay
max_pending|限制同时等待响应的请求数量；按峰值并发请求和资源能力选择
''')
register('calculations[].', '''
id|为这项计算结果取唯一名称；结果表用它区分计算项
scope|选择计算范围；session整段会话，{rule: 名称}逐事件，{window: 名称}逐片段
operation|选择统计或积分方法；按希望输出的物理量/统计量填写
signal|选择被计算的信号；填写已定义的signals或derived名称
condition|限定参与计算的时间或样本；使用已有信号写真假表达式
method|选择积分使用的区间取值方法；zoh沿用前值，其他支持值见积分表
unit|选择结果单位；从该运算和输入单位支持的输出单位中选择
minimum_coverage|设置要求的最低有效数据比例；0到1，按可信性要求选择
rule|填写产生待计点事件或活动的规则名称
window|填写产生最终片段的窗口名称，合并后再计数
ddof|方差或标准差的分母修正；样本可选0或1，时间总体只能为0
q|给出0到1之间的有限概率，按有效真实样本精确求分位数
partial_policy|决定数据不全时是否保留可核实数值；report保留并标记，strict返回空值
''')
register('transforms[].', '''
name|命名这一条时序结果，后续表达式按此名称引用
operation|指定内置或宿主已注册的时序操作
expr|指定数值输入表达式
window|设置按所选口径回看的窗口宽度
step|设置实际时间轴上的输出网格间隔
origin|指定实际时间网格的起点
max_gap|限定相邻真实样本允许的最大实际时间距离
partial_policy|指定窗口不完整时是否允许部分估值
minimum_coverage|限制网格窗口所需的最低有效覆盖比例
unit|给时序输出选择已知兼容的目标单位
interval|选择权重和变化率分母所用的实际/固定/DBC口径
interval.mode|指定实际、固定或DBC周期
interval.driver|指定可核实的原记录时钟
interval.value|填写固定周期时长
''')

register('lookups[].', '''
name|为标定表取唯一名称，表达式lookup按它选择表
input_unit|标注标定点第一列的物理单位，输入先换算到这个尺度
unit|标注标定点第二列及查表结果的物理单位
points|按输入严格递增列出每对输入和输出，两个端点均属于表内
''')
register('aggregations[].', '''
name|命名组统计，聚合结果表按此名称定位
source|选择提供候选行的一个已定义计算、配对、规则或窗口
source.calculation|引用产生标量结果行的计算名称
source.sequence|引用产生请求配对结果的序列名称
source.rule|引用产生待计事件的规则名称
source.window|引用产生待计片段的窗口名称
operation|指定对候选结果行所求的计数、和、均值、方差、分位数或中位数
field|指标使用value，配对延迟使用delay_ns，计对象行时省略
unit|为聚合结果选择兼容的单位；例如延迟可输出为毫秒
ddof|设置候选数值的方差分母为N或N减1，只用于variance
q|设置quantile所需的有限概率，范围为0到1；median省略
group_by|用来源允许的身份字段分组；空列表将本分析的候选合为一组
include_partial|仅数值指标可设为true，纳入可用的部分值并传递部分状态
partial_policy|设置总体不完整时是否保留可计算的数值，默认继承执行设置
''')
register('intervals.', '''
default|设置未单独覆盖的计算节点采用的时间间隔依据
default.mode|选择actual实际时间差、fixed固定周期或dbc报文周期
default.value|给fixed模式提供固定周期；从采集设置或业务规则取得
default.driver|选择提供周期和更新计数的信号；填写已有signals名称
overrides|按规则/配对/计算节点ID覆盖默认的间隔选择
''')
register('execution.', '''
process_count|设置会话工作进程上限；普通分析并行读取解码，fast还求同帧贡献；默认1，不含主进程
backend|选择计算实现；numpy使用数组，reference使用独立参考计算
batch_rows|限制一次交给分析层的记录数；按内存和处理开销选择，不是采样周期
memory_budget_bytes|限制新分析层管理的内存字节数；按可用内存留出其他进程开销
result_buffer_rows|限制结果写入前在内存积累的行数；按结果大小和内存选择
spool_quota_bytes|限制本次分析临时数据的磁盘字节数；按可用磁盘空间选择
partial_policy|设置默认的数据不全处理；report保留已知部分，strict不给不完整数值
on_budget_exceeded|选择资源超限处理；当前填error，中止并报告，不丢数据继续
''')
register('diagnostics.', '''
trace|控制是否记录详细定位信息；true增加追溯记录，false使用默认简要信息
integrity|控制是否生成额外完整性校验信息；true启用，false不增加这项工作
retain_work|控制关闭后是否保留本次临时数据；true保留，false按默认清理自有暂存
''')
register('presets[].', '''
id|给本次预设实例取唯一名称；展开的规则/计算名称使用此前缀
preset_type|选择业务任务；charge_session充电、fault_context报警上下文、command_response配对、threshold_excursion阈值
version|选择预设定义版本；当前填写字符串"1"，与分析配置结构版本相互独立
role_bindings|明确指定哪条已有信号担任每个角色；角色名由预设定义
parameters|提供本预设的业务参数；各预设支持的字段不同，不能互相套用
parameters.mode_value|指定表示充电的模式代码；从设备状态编码表取得
parameters.current_min|设置充电判断的电流下限；按业务目标填写，单位A
parameters.minimum_duration|设置充电条件连续成立多久才确认；按业务要求填写
parameters.compute_energy|选择是否计算充电能量；true需要电压角色，false不生成能量项
parameters.compute_charge|选择是否计算电荷量；true生成电流积分并输出Ah，false不生成
parameters.pre|设置故障点之前保留的时长；按需要观察的故障前过程填写
parameters.post|设置故障点之后保留的时长；与pre至少一项大于0
parameters.emit_initial|控制初始观测为真是否记作新事件；true记录，false等待后续上升沿
parameters.min_delay|设置请求到响应的最小允许延迟；按协议要求填写
parameters.max_delay|设置请求到响应的最大允许延迟；必须不小于最小延迟
parameters.max_pending|设置同时等待响应的请求上限；按业务并发规模选择
parameters.unit|声明阈值数值的单位；须与所选信号的单位要求一致
parameters.enter_threshold|设置进入报警的高阈值；必须大于恢复阈值
parameters.exit_threshold|设置恢复的低阈值；按业务允许恢复范围填写
parameters.enter_delay|设置超过进入阈值后等待确认多久；0s为立即确认
parameters.exit_delay|设置达到恢复阈值后等待确认多久；0s为立即恢复
''')
register('message_calculations[].', '''
disjunction|按同一报文中的方向信号分组累计；省略时不区分方向
disjunction.signal|选择用于判断方向的原信号名；必须已绑定到同一目标报文
disjunction.bucket|选择方向组；positive只接收方向原值大于0，negative只接收小于0
disjunction.value_policy|选择方向值的处理阶段；raw_decoded-v1使用DBC解码后的原值，不再额外换算
id|为逐消息累计结果取唯一名称；用于识别对应结果行
source|选择原始CAN来源；填写前面sources的名称
operation|选择逐消息算法；legacy_sum对各目标消息的表达式结果求和
update_message|指定触发一次求值的目标报文；通道和ID从日志/DBC取得
update_message.channel|指定目标报文的通道；须与来源的通道编号一致
update_message.frame_id|指定每到一条便求值的报文ID；从DBC取得
expr|定义单条目标消息的贡献；使用该报文信号和parameters常量
unit|声明累计结果的单位；须与表达式量纲相符
parameters|定义逐消息公式使用的固定参数；名称由公式引用，值来自采集/业务规范
parameters.period|提供名为period的公式参数；在本例表示每条消息计入的时间
parameters.period.value|填写每条消息代表的时间数值；从消息周期或业务规则取得
parameters.period.unit|声明该公式参数的单位；本例s表示秒
profile|选择逐消息求值所使用的CAN读取规则；必须与来源读取路径相符
message_policy|选择每条目标报文使用哪些值；current_message-v1仅使用本条携带的值
''')
register('outputs.', '''
tables|选择结果表文件格式；csv为表格，jsonl为每行一个JSON对象
contributions|选择是否导出每次贡献明细；用于检查逐消息求值及跳过原因
signal_csv|配置额外的信号CSV导出；null表示不启用这项额外输出
signal_csv.signals|选择要导出的分析信号名；来自前面的信号定义
signal_csv.scope|选择导出的时间范围；session整段会话，{window: 名称}指定窗口片段
signal_csv.resampling|设置独立信号输出网格；不修改分析时的信号历史和积分
signal_csv.resampling.period|指定信号导出网格间隔；依据输出采样需求填写
signal_csv.resampling.origin|设置信号网格的起点基准；后续按period等距排列
signal_csv.resampling.max_gap|限制用于插值的相邻记录间隔；按允许缺测程度选择
signal_csv.resampling.continuous|列出可线性插值的分析信号名；仅选择物理上允许中间值的连续量
can_frames|配置原始或重建CAN帧的额外导出；与信号CSV分别设置
can_frames.source|选择要导出的CAN来源name；不得填写分析信号名
can_frames.format|选择输出报文文件格式；asc为文本，blf为二进制
can_frames.scope|选择导出的时间范围；session整段会话、{window: 名称}单窗口、{windows: all}全部窗口
can_frames.capture_date|提供实际采集日期；用于输出文件的日期信息，相对时间输出BLF时需配合timezone及output_offset
can_frames.timezone_offset_minutes|声明采集日期的时区偏移分钟数；从采集地点时区取得
can_frames.source_time_reference|声明原始时间是相对还是绝对；按日志记录方式填写
can_frames.output_offset|给导出时间增加固定偏移；按目标文件的时间基准填写
can_frames.resampling|设置重建CAN帧网格；根据DBC重写选定信号，其他位取基础帧
can_frames.resampling.period|指定重建CAN帧的网格周期；与信号CSV网格独立
can_frames.resampling.origin|设置重建CAN帧网格的起点基准
can_frames.resampling.max_gap|限制重建帧使用的记录间隔；超过上限不伪造连续数据
can_frames.resampling.unknown_policy|选择未列入messages的报文如何导出；passthrough保留原时间原帧，nearest在网格点选最近整帧
can_frames.resampling.messages|逐报文列出要重建的连续信号和保留字段
can_frames.resampling.messages[].channel|选择要重建的CAN通道；从日志取得
can_frames.resampling.messages[].frame_id|选择要重建的报文ID；从DBC取得
can_frames.resampling.messages[].continuous|填写允许线性插值的DBC信号名；不是signals中的分析别名
can_frames.resampling.messages[].protected|填写禁止重算的DBC字段名，如计数器/校验码；这些位保留基础帧值
can_frames.resampling.messages[].same_time_policy|选择冲突同刻帧能否参与插值；error不据冲突帧插值，last_by_sequence采用读取顺序最后一帧
''')
register('jobs[].', '''
id|为独立任务取唯一名称；批量报告用它识别任务
plan|指定该任务的分析配置文件；相对于批量配置文件所在目录
''')


def example_comment(path, value, parent):
    """结合具体取值及同级配置说明本例选择；未知算法拒绝生成误导注释。

    参数为完整字段路径、实际值及其父映射；返回一行用途和本例行为。
    其他字段沿用完整路径职责词典，不把某种输出格式的解释套到另一种格式。
    """
    normalized = re.sub(r'\[\d+\]', '[]', path).removeprefix('analysis.')
    if normalized == 'rules[].rule_type':
        if value == 'debounce' and 'enter_delay' not in parent and 'exit_delay' not in parent:
            return '选择进入/退出状态的稳定等待规则；本例省略两项等待，默认均为0s，不增加额外确认等待'
        behavior = {
            'condition_duration': '条件连续成立达到minimum_duration后确认活动',
            'rising_edge': 'condition由false变为true时产生瞬时事件',
            'falling_edge': 'condition由true变为false时产生瞬时事件',
            'start_only': '开始条件触发后，在window_duration内抑制重复触发',
            'start_end': 'start_condition开始活动，end_condition或timeout结束活动',
            'hysteresis': '分别用进入和退出条件判断活动，避免一个阈值附近反复切换',
            'debounce': '进入和退出条件各需保持指定时长才确认状态变化',
            'window_delta': '检查向前窗口内的变化幅度、方向及配置的单调性要求',
        }[value]
        return '选择活动或变化识别算法；本例'+behavior
    if normalized == 'calculations[].operation':
        behavior = {
            'integral': '将有效数值乘持续时间后累计，例如功率乘秒得到能量',
            'sample_mean': '对范围内有效真实样本等权求平均，每个样本计一次',
            'sample_minimum': '取范围内有效真实样本的最小值',
            'sample_maximum': '取范围内有效真实样本的最大值',
            'sample_count': '每个选中的有效真实更新计一次',
            'point_event_count': '计数所引用规则产生的点事件',
            'activity_count': '计数所引用规则发现的活动，每个活动只计一次',
            'segment_count': '计数所引用窗口最终产生的片段',
            'sample_variance': '各有效真实读数等权，以N减ddof为分母求方差',
            'sample_stddev': '对等权真实读数的方差取平方根',
            'sample_rms': '对等权有效真实读数求均方根',
            'time_variance': '按选中的有效保持时长加权求总体方差',
            'time_stddev': '对时间加权总体方差取平方根',
            'time_rms': '按选中的有效保持时长加权求均方根',
            'sample_quantile': '将所选读数按值排序并在指定概率处精确线性插值',
            'sample_median': '取所选有效读数的中位数，概率固定为0.5',
            'time_weighted_mean': '按有效值持续时长加权求平均',
            'min_time': '取有正持续时间的有效值中的最小值，不返回发生时间',
            'max_time': '取有正持续时间的有效值中的最大值，不返回发生时间',
            'duration': '累计条件已知为true的秒数',
            'select': '逐行保留范围内被选择的样本，不生成汇总数值',
        }.get(value, '执行宿主显式注册的样本归约')
        return '选择计算方法；本例'+behavior
    if normalized == 'message_calculations[].profile':
        behavior = {'can-text-v1': '使用文本CAN适配层解码的当前报文值；本例来源须采用该路径',
                    'sclicer-functions-v1': '使用单BLF读取路径的当前报文值'}[value]
        return '选择逐消息求值规则；本例'+behavior
    if normalized == 'outputs.can_frames.capture_date':
        if parent.get('format') == 'blf':
            return '提供相对时间输出BLF的采集日期；与timezone及output_offset共同定位日历时间'
        if parent.get('format') == 'asc':
            return '提供ASC文件头的采集日期；按实际采集记录填写并配套timezone'
    return comment(path)


def comment(path):
    """参数: 完整路径。返回: 已审写的职责注释。异常: 未登记路径抛KeyError，禁止自动套短名。"""
    path = re.sub(r'\[\d+\]', '[]', path)
    # 当前公开结构先精确解释；只在已知同义路径复用职责，未知键仍拒绝。
    current = {
        'dataset.name':'命名本次分析数据集；名称写入结果身份字段',
        'dataset':'设置本次分析名称及可选的对象、会话和时间范围',
        'sources[].paths':'选择输入文件、连续分卷列表或目录；相对路径基于本配置，目录按自然序读取',
        'sources[].reader':'设置当前来源的文本解析、列映射或解码行为；可用子字段取决于来源格式',
        'reader':'设置来源的读取选项；本片段放在对应sources列表项内',
        'reader.decode_policy':'选择已选CAN帧长度检查和解码失败处理；按输入章节的路径对照表选择',
        'sources[].reader.decode_policy':'选择已选CAN帧长度检查和解码失败处理；strict完整长度，partial允许短帧，legacy按路径表',
        'signals[].conversion':'设置读取后额外的单位换算；不重复DBC已执行的缩放和偏移',
        'signals[].frame_id':'选择本组所属报文；从DBC取得ID，所有子信号须属于该报文',
        'signals[].signals':'列出本报文需要的子信号；继承组级定位，可覆盖周期、有效期和同刻策略',
        'signals[].signals[].signal':'填写本组报文内的DBC信号名称；大小写须一致',
        'calculations[].expr':'指定参与计算的数值或信号表达式；引用前面已定义的信号',
        'calculations[].scope.rule':'按指定规则的每次事件分别计算；填写前面rules中的name',
        'calculations[].scope.window':'按指定窗口的每个片段分别计算；填写前面windows中的name',
        'outputs.can_frames.scope.windows':'选择导出全部已定义窗口的片段；当前填写all',
        'outputs.can_frames.timezone':'声明采集日期的时区偏移；按采集记录填写如+08:00',
        'outputs.signal_csv.resampling.period.mode':'选择信号网格周期的来源；dbc从所选物理报文的DBC周期取得',
        'outputs.signal_csv.resampling.period.driver':'选择提供整个信号网格周期的分析信号；多个候选报文时必填',
        'outputs.can_frames.resampling.period.mode':'选择每条重建报文自己的DBC周期；当前填dbc，不使用信号网格driver',
        'windows[].rule':'选择生成窗口的事件规则；填写前面rules中的name',
        'template':'指定批量任务重复使用的分析配置路径；每个输入独立执行该配置',
        'inputs':'选择批量处理的文件、目录或通配符；每个文件是独立任务',
        'process_count':'限制分析工作进程数；正整数，1表示一个工作进程依次执行',
        'overrides':'明确覆盖导入的公共定义；仅在需要改动已导入设置时填写',
        'overrides.signals':'按已导入信号的名称指定允许覆盖的设置',
    }
    if path in current:return current[path]
    if path.endswith('.time.clock'):return '命名相对时间的共同起点；来自同步依据，同名不会自动校时'
    if path.startswith('signals[].signals[].'):
        return comment('signals[].'+path[len('signals[].signals[].'):])
    if path.startswith('signals[].conversion.'):
        return comment('signals[].'+path[len('signals[].conversion.'):])
    if re.fullmatch(r'(calculations|rules|windows|presets|sequences|message_calculations|jobs)\[\]\.name',path):
        return comment(path[:-4]+'id')
    if re.match(r'(calculations|rules|windows|sequences)\[\]\.interval($|\.)',path):
        suffix=path.split('.interval',1)[1]
        return '为本节点单独选择计算间隔；覆盖全局默认，不修改原记录时间' if not suffix else comment('intervals.default'+suffix)
    if path.startswith('message_calculations[].split_by_sign'):
        return comment(path.replace('.split_by_sign','.disjunction',1))
    if path.startswith('overrides.signals.'):
        rest=path[len('overrides.signals.'):].split('.',1)
        return '修改名为'+rest[0]+'的已导入信号；其他字段保持原定义' if len(rest)==1 else comment('signals[].'+rest[1])
    if path.startswith('sources[].reader.'):
        tail=path[len('sources[].reader.'):]
        if tail in ('encoding','delimiter','missing_values','decode_scope','input_check'):
            return comment('sources[].'+('sep' if tail=='delimiter' else tail))
        return comment('sources[].parser.'+tail.replace('fields.frame_id','fields.arbitration_id').replace('fields.is_extended','fields.is_extended_id'))
    if path.startswith(('CAN来源的time', 'CSV来源的time')):
        path = re.sub(r'^[^.]+', 'sources[].time', path)
        return comment(path)
    if path in COMMENTS:
        return COMMENTS[path]
    if path.startswith('sources[].rows[].values.'):
        return '本时刻原字段'+path.rsplit('.',1)[1]+'的合成输入值；其类型和单位由下方信号定义说明'
    if path.startswith('sources[].dbc_by_channel.'):
        return '为这个通道指定DBC文件；路径相对当前配置文件，通道键须为字符串'
    if re.fullmatch(r'derived\.[^.]+', path):
        return '定义名为'+path.split('.')[1]+'的派生信号，后面的计算通过此名称引用'
    if re.fullmatch(r'derived\.[^.]+\.expr', path):
        return '规定派生值如何由已有信号计算；名称必须先在signals或前面的derived中定义'
    if re.fullmatch(r'derived\.[^.]+\.unit', path):
        return '声明表达式计算结果的单位；依据公式与输入单位取得'
    if path.startswith('presets[].role_bindings.'):
        return '为'+path.rsplit('.',1)[1]+'角色选择上方已定义的分析信号名；仍须符合该角色要求'
    if path.startswith('metadata.'):
        return {'metadata.device_label':'记录产出设备标签；当前独立导出仅接受home/work，普通分析与批量报告规则见对应说明',
                'metadata.data_kind':'记录数据来源性质；synthetic表示人工构造的测试输入',
                'metadata.purpose':'记录这份配置的用途；不参与条件判断或数值计算'}[path]
    if path.startswith('intervals.overrides.'):
        suffix=path.split('.')[3:]
        return comment('intervals.default.'+'.'.join(suffix)) if suffix else '为该ID的计算节点单独选择间隔依据；ID来自规则/配对/计算声明'
    if path.startswith('sources[].parser.layout.fields.'):
        field=path.split('.')[4]; suffix=path.split('.')[5:]
        fields={'timestamp':'报文时间','arbitration_id':'报文ID','data':'数据字节','payload_length':'实际数据长度','dlc_code':'数据长度编码',
                'channel':'通道编号','frame_kind':'帧种类','is_extended_id':'扩展ID标志','is_fd':'CAN FD标志','is_rx':'接收方向标志',
                'bitrate_switch':'FD速率切换标志','error_state_indicator':'FD错误状态标志'}
        if not suffix: return '指定'+fields[field]+'如何从CSV取得；选择column读列或fixed固定值'
        if suffix[0]=='value_map':
            return ('把CSV原文字转换为'+fields[field]+'需要的值；左侧来自原表，右侧按字段类型填写' if len(suffix)==1
                    else '输入文字'+'.'.join(suffix[1:])+'对应右侧目标值'+('；true表示接收、false表示发送' if field=='is_rx' else '；目标类型和含义按本报文字段的定义填写'))
        return {'column':'填写提供'+fields[field]+'的实际CSV表头或支持的列索引',
                'fixed':'为每一条报文固定填写'+fields[field]+'；仅当该文件这一属性确实恒定时使用',
                'strip':'选择查表前是否去掉单元格两端空白；true去除，false保留'}[suffix[0]]
    raise KeyError(path)
