# 信号CSV导出与重采样

`outputs.signal_csv`导出指定原信号的更新记录；可另外设置等间隔线性插值。它不改变分析中的积分结果。共同范围、文件发布与当前环境限制见[输出配置](exports.md)。

## 完整最小例与网格扩展

[export-signal-minimal.yaml](examples/export-signal-minimal.yaml)从随附的quickstart.asc和teaching.dbc读取power，积分仍为38J，额外导出[0,6)内0、1、3、4秒的4条原更新。来源、信号及当前导出所需的设备标签都已定义。

[export-signal-grid.yaml](examples/export-signal-grid.yaml)增加500ms网格、max_gap=3s，输出12行网格点0～5.5秒。0.5秒线性估计为3W；4.5、5、5.5秒缺少范围内右端更新，保留missing而不外推。积分仍为38J。运行`chronaxis run 文件名.yaml --output 新目录`，通过exports.jsonl查找original.csv或resampled.csv。

## 原信号CSV导出

下段是根级outputs片段，前提是signals已绑定数值信号voltage，并满足[导出标签限制](exports.md)。若已有outputs，把signal_csv合入同一映射，不能重复outputs键。

应用位置：以[dual-grid.yaml](examples/dual-grid.yaml)为基础，找到根级outputs，仅加入或替换其中的`signal_csv`子项，保留outputs下其他子项；代码中的outputs只表示位置，不重复粘贴父键。保留未展示的其他根字段，不再添加第二个同名父键。

先运行最小配置；下方扩展配置增加可选控制。两段是替换关系，不同时重复写入同一个父键。

```yaml
outputs:                  # 选择额外导出的数据及格式；默认结果表由运行入口提供
  signal_csv:             # 配置额外的信号CSV导出；null表示不启用这项额外输出
    signals: [voltage]    # 选择要导出的分析信号名；来自前面的信号定义
```

### 扩展设置

仍以同一基础文件为起点，用下面的signal_csv子项替换上面同名子项，仍保留outputs下其他子项；新增字段的默认值、适用条件见后文。

```yaml
outputs:                       # 选择额外导出的数据及格式；默认结果表由运行入口提供
  signal_csv:                  # 配置额外的信号CSV导出；null表示不启用这项额外输出
    signals: [voltage]         # 选择要导出的分析信号名；来自前面的信号定义
    resampling:                # 设置独立信号输出网格；不修改分析时的信号历史和积分
      continuous: [voltage]    # 列出可线性插值的分析信号名；仅选择物理上允许中间值的连续量
      period: 250ms            # 指定信号导出网格间隔；依据输出采样需求填写
      max_gap: 2s              # 限制用于插值的相邻记录间隔；按允许缺测程度选择
```

下表字段相对于`outputs.signal_csv`，其中signals是要导出的信号名列表，不是根级signals定义列表。

|signal_csv字段|数据类型|必填|默认值|含义与填写方法|
|---|---|---|---|---|
|signals|字符串数组|是|无|选择导出哪些原信号；从signals[].name取得。1～4096个不重复的原信号别名，例如 `["voltage","current"]`；来自signals，不直接选择derived派生信号。|
|scope|字符串或对象|否|`session`|选择要导出的时间范围。整会话用session；单窗口用`{window: context}`。窗口名称来自windows[].name，见[共同范围](exports.md#export-scope)。|
|resampling|对象或null|否|`null`|控制是否另排等间隔时间点并估计连续信号值。null或省略表示保留原记录；填写对象则开启下方等间隔导出。|

不设置resampling时，original.csv逐条保存原信号更新，是“一个时间、一条信号”一行的长表；不会把不同信号强行拼成相同采样频率。无效值在value列留空，quality记录原因；同刻不同更新仍分别保留。公开执行路径的表头是`time_ns,signal,value,unit,quality`，不含valid、status或来源引用列。

设置resampling后，明确列入continuous的信号写入resampled.csv；其余信号按原更新写入original.csv。continuous必须是signals的子集，且是数值信号；bool、枚举、状态和计数不应当作连续物理量插值。其全部配置如下：

下表字段相对于`outputs.signal_csv.resampling`，例如max_gap完整写作`outputs.signal_csv.resampling.max_gap`。

|signal_csv.resampling字段|数据类型|必填|默认值|含义与例子|
|---|---|---|---|---|
|continuous|字符串数组|是|无|指定允许插值的信号；按物理上是否可以线性估计选择，不仅看数据是否为数字。本次可插值的原信号别名，须是signals的非空子集，且不重复。填 `["voltage"]` 表示电压可按两端记录作直线估计。|
|period|正时长字符串或映射|是|无|规定网格点间隔；按输出采样需求填写固定时长，或选择DBC周期。固定周期例如`250ms`；读取DBC周期时填写`{mode: dbc}`，可加driver指定continuous中的驱动信号。驱动信号须能定位到具有有效周期的DBC报文。|
|start|时间字符串|否|`"0s"`|设置网格对齐的参考时刻；根据需要对齐的统一起点填写。等间隔时间的参考起点。例如start=50ms、period=100ms，位置是50、150、250ms等；不随文件或分批重新计时。|
|max_gap|时长字符串|是|无|限制插值可跨越的实际记录间隔；按可接受缺测长度填写。大于0；用于插值的前后两条实际记录最多能相隔多久。例如2秒时，两端相隔2秒可以估计，相隔3秒则留空。|

`period`若采用映射，字段填写如下。它和根级intervals独立，不能互相替代。

| 完整路径 | 控制作用与填写依据 | 允许值及省略行为 |
|---|---|---|
| outputs.signal_csv.resampling.period.mode | 选择网格周期从哪里取得；希望沿用报文周期时使用此对象 | 仅允许dbc；固定周期直接将period写为250ms，不使用mode: fixed |
| outputs.signal_csv.resampling.period.driver | 指定网格采用哪条原信号所在报文的周期；从continuous列表中选择信号名 | continuous都须来自原始CAN来源；只有一个物理报文候选可省略，多个候选须明确填写。显式null、派生信号或不在continuous中的名称不合法 |

程序按start和period排出要导出的时间点，这组时间点称为“时间网格”。每个时间点的结果分为三种：

|status|怎样得到这个值|
|---|---|
|observed|该时刻恰好有一条有效的实际记录，直接采用记录值。|
|estimated|该时刻没有记录，但前后记录有效、间隔没有超过max_gap；按两点之间的直线估算。|
|missing|缺少前端或后端记录、记录无效、同刻记录冲突，或前后间隔过大。value留空，reason说明原因。|

例如每100ms导出一次，只有第10ms和第120ms的有效记录，那么第100ms的值可以估算，第0ms缺少前端记录则不能估算。

同一信号同一时刻存在不同的记录时：若仅用于信号导出网格，error策略将冲突点及受影响的插值标记为missing，reason为same_time_conflict；若同一信号还参与普通计算或规则，分析状态在error策略下拒绝冲突并使任务失败。本页dual-grid.yaml还对voltage积分，因此属于后一种情形。显式选择 `same_time_policy="last_by_sequence"` 才按稳定来源序号选择最后一条，不按数值大小或线程处理先后选择。该选项填写在`signals[].same_time_policy`。公开重采样文件的表头是`time_ns,signal,value,unit,status,reason,quality`；不输出左右端点时间或来源引用。

## 使用DBC周期的完整导出例

下载[完整配置](examples/dbc-grid/analysis.yaml)、[grid.asc](examples/dbc-grid/grid.asc)和[grid.dbc](examples/dbc-grid/grid.dbc)，三者放在同一目录，运行`chronaxis run analysis.yaml --output grid-result`。

本例同时导出power和voltage。DBC分别声明Power报文1000ms、Voltage报文500ms，输入在0、1、2秒更新。信号CSV只有一套网格，period.mode=dbc且driver=power明确选择1000ms；连续量涉及两个物理报文，删除driver会因多个候选而报错，不会任选一个周期。

CAN导出使用每条报文自己的DBC周期，因此period只写mode=dbc，不填driver：Power按1秒、Voltage按0.5秒生成。两类输出分别配置，选择信号网格驱动不会改变CAN各报文周期。观测范围为[0,2)，范围末端及缺右侧有效样本时的处理沿各导出规则；应同时查看导出数据和manifest中的生成/跳过计数。

本例[信号CSV](examples/dbc-grid/results/resampled.csv)在0、1秒分别输出power=10/20W、voltage=20/30V，共4行。[重建ASC](examples/dbc-grid/results/frames.asc)共5帧：Power在0、1秒，Voltage在0、0.5、1秒（20、25、30V）。Voltage的1.5秒网格点需要右侧2秒样本，但2秒是请求范围的排除端点，不能从范围外借该样本，因此跳过1点。两类输出行数不同是各自网格规则的结果。
