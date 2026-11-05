# 时序变换

根级`transforms`把已绑定的数值信号或表达式变成新的时序信号。新名称可以被规则、计算或后续变换引用。它支持滚动统计和变化率，输入可以来自CAN日志、信号CSV或内存；不局限于电流。

## 先运行一个滚动均值

下载[最小配置](examples/temporal/rolling-actual.yaml)、[meter.asc](examples/temporal/meter.asc)和[meter.dbc](examples/temporal/meter.dbc)，放在同一目录。这里是合成数据：0秒10A、0.12秒20A、0.30秒40A，后续还有0.42秒和0.60秒的5A。配置只选择一个rolling_time_mean和一项select，使用默认actual时间；省略有效期时采用DBC周期100ms的3倍。

```powershell
chronaxis validate rolling-actual.yaml
chronaxis run rolling-actual.yaml --output rolling-result
```

在本轮manifest列出的选择结果表中，`average_rows`在0.20秒应为18A：窗口[0.10,0.20)内，10A持续0.02秒、20A持续0.08秒，均值为(10×0.02+20×0.08)/0.1。起始窗口缺少历史时按默认strict不提供数值。完整配置如下：

```yaml
config_version: 4                   # 使用当前分析配置格式
dataset:                            # 命名本次分析
  name: rolling_actual              # 结果中的数据集名称
sources:                            # 读取配套合成报文
  - paths: meter.asc                # 文件路径相对本配置
    dbc_by_channel:                 # CAN通道到DBC的对应关系
      '1': meter.dbc                # 用户通道1对应这份DBC
signals:                            # 定义后续计算引用的信号
  - name: current                   # 分析中的电流名称
    field:                          # 按DBC定位信号
      frame_id: 0x100               # 包含电流的报文ID
      signal: Current               # DBC信号名称
transforms:                         # 从已有信号生成新的时序信号
  - name: average                   # 滚动均值序列名称
    operation: rolling_time_mean    # 按有效时长加权求窗口均值
    expr: current                   # 使用上面绑定的电流
    window: 0.1s                    # 回看实际时间0.1秒
    step: 0.1s                      # 每隔实际时间0.1秒计算一次
calculations:                       # 选择要返回的结果
  - name: average_rows              # 选择记录的计算名称
    operation: select               # 输出每次均值的时刻、值和质量
    expr: average                   # 读取新时序信号
```

## 字段参考与操作选择

字段位于`transforms[]`。一个计划最多64项；name与原始信号、派生信号及其他变换名称不得重复，引用不得形成循环。未被任何请求结果依赖的变换不会计算。

|字段|类型、要求与默认|作用|
|---|---|---|
|name|必填合法名称|新时序信号名称，供后续expr或condition引用|
|operation|必填字符串|从下表选择，或使用宿主注册的时序算子|
|expr|必填数值表达式|输入必须为float64/int64/uint64，不能直接用bool或enum|
|window|网格操作必填正时长|回看宽度，按interval选择的时间依据计量|
|step|网格操作必填正时长|实际时间轴上相邻输出时刻的间隔|
|origin|网格操作可选时间坐标，默认时基零点|输出时刻为origin+n×step；绝对来源按对应日期时间填写|
|max_gap|adjacent_rate必填正时长|相邻实测点允许的最大实际时间间隔|
|unit|可选兼容单位|选择新信号的数值单位；默认由运算推导|
|partial_policy|网格操作可选，默认strict|strict要求完整数据；report允许有依据的部分值并保留质量|
|minimum_coverage|网格操作可选有限数，默认0|0～1；要求的有效数据比例，不能补造缺失值|
|interval|可选对象，继承intervals.default，默认actual|actual使用实际间隔；fixed/dbc随选定driver更新推进，见[时间依据](intervals.md)|

|operation|window、step|origin／partial_policy／minimum_coverage|max_gap|结果|
|---|---|---|---|---|
|rolling_time_mean|必填|可选|禁止|回看窗内按有效时长加权的均值|
|rolling_minimum、rolling_maximum|必填|可选|禁止|有正持续时间的保持值最小／最大值|
|rolling_integral|必填|可选|禁止|窗口内有效保持值的积分|
|adjacent_rate|禁止|全部禁止|必填|当前与上一次有效实测值之差／对应间隔，在右侧实测时刻输出|
|window_rate|必填|可选|禁止|窗口两边界的有效值之差／窗口宽度|
|sample_fit_slope|必填|可选|禁止|窗口内真实更新点等权直线拟合斜率，至少两个不同位置|

滚动均值、积分和变化率输出float64；滚动极值在换算允许时保留输入数值类型。摄氏绝对温度积分须先显式换成K；温度变化率采用温差／时间单位。原始时间和valid_for始终按实际时间判断，固定周期不会使过期样本复活。

## 扩展示例：七种变换与DBC周期

下例使用同一组报文，新增七种变换、按DBC周期计量，以及逐项输出；小批次设置仅用于演示执行资源选项，最小任务不需要照抄。

这份 ASC 在 0.00、0.12、0.30、0.42、0.60 秒依次记录 10、20、40、5、5 A。DBC 声明这条报文的周期为 100 ms。在 0.20 秒虽然没有新帧，仍可询问“最近一个报文周期内，平均电流是多少”。示例按同一配置输出四个滚动值和三种变化率。下载[完整配置](examples/temporal/analysis.yaml)、[原始 ASC](examples/temporal/meter.asc) 和 [DBC](examples/temporal/meter.dbc)，保持三份文件在同一目录。

## 先运行再核对

从该目录运行以下命令。两次运行可分别用 `--backend reference` 与 `--backend numpy`，并指定不同的结果目录。

```powershell
python -m chronaxis validate analysis.yaml
python -m chronaxis run analysis.yaml --backend numpy --work-dir work-grid --output result-grid
```

比较 reference 后端时，改用 `--backend reference --work-dir work-grid-reference`。工作目录须与前次分开；输出目录可复用，每次生成带时间后缀的新结果。

`signals` 将通道 1、标准帧 0x100 中的 Current 绑定为 `current`。`transforms` 的每个 `name` 是一条新的有单位序列，可直接写进规则条件、后续变换或 `calculations.expr`。本例使用 `select`，所以要按**选择行上的实际时刻**核对。

|选择行名称|实际时刻|参考结果|代表什么|
|---|---:|---:|---|
|average_rows|0.20 s|130/9 ≈ 14.444444 A|前一个周期的时间加权平均|
|low_rows / high_rows|0.20 s|10 / 20 A|窗口内有正时长的保持值极值|
|charge_rows|0.20 s|13/9 ≈ 1.444444 A·s|有效电流面积，结果单位文本为 `A*s`|
|adjacent_rows|0.30 s|200 A/s|当前和上一实测值的差除以一个周期|
|endpoint_rows / fit_rows|0.30 s|150 / 150 A/s|两个周期的端点变化率，以及窗内真实点的等权拟合|

## 实际时刻和所选周期各做什么

`origin + n × step` 给出实际输出时刻，默认 origin 是分析时基的零点。`window` 给出回看宽度。`interval` 选择宽度和差分分母按实际时间、固定周期还是驱动报文 DBC 周期计算。固定模式写成 `{mode: fixed, value: 0.1s, driver: current}`；DBC 模式针对能核实周期的原始报文驱动。把 `intervals.default` 改成 `{mode: actual}`，0.20 秒时窗口为实际的 [0.10,0.20)，均值为 (0.02×10+0.08×20)/0.1 = **18 A**。

在本例 DBC 模式中，0.12 到 0.30 秒共一个周期，0.20 秒只走完 4/9 周期。回看一个周期，10 A 占 5/9，20 A 占 4/9，均值即 130/9 A。需要读到 0.30 秒才能知道这段实际长度，结果仍记在 0.20 秒。最后一条驱动后缺少后帧时，不猜未结束周期里已经走了多远。

## 选对变化率

- `adjacent_rate` 在右侧真实数值更新时间给出结果，`max_gap` 与源信号 `valid_for` 都按**实际时间**检查。两个真实点之间若存在未知或过期间隙，重新取得有效点后要等下一对连续点。驱动与输入可以不同。驱动在 0、0.12 秒更新，电流在 0.03、0.09 秒分别为 1、7 A，固定周期 0.1 秒，折算间隔是 0.05 秒。读到 0.12 秒后，在 **0.09 秒**得到 120 A/s。
- `window_rate` 在网格上取两个边界的有效保持值并作差，再除以所选窗口宽度。右边界若恰有新实测，取更新后的值。滚动积分与均值采用左闭右开窗口，右端新值不会倒算进此前的面积。
- `sample_fit_slope` 在网格窗口内对实际更新点等权拟合，边界上的实点可参加，至少需要两个不同位置。它不把窗口裁剪点或一次保持刷新造为新测量。温度为 0 秒 20℃、1 秒 21℃、3 秒 26℃，按 actual 计算，3 秒处的相邻、3 秒端点和拟合斜率分别为 2.5、2、约 2.071429，单位是 `delta_K/s`。[窗口变化量事件规则 `window_delta`](rules.md#rule-window-delta)检测窗口两端的值之差是否满足阈值；它不把差值除以时长，与这里计算变化率的操作不同。

## 窗口历史不足与不完整数据

默认 `partial_policy: strict` 要求窗口完整。提前的网格点、前值已超过valid_for而下一有效样本尚未到达的缺口或不足两个拟合点都可能给出未知。对允许部分计算的窗口可显式选 `report` 和 `minimum_coverage`；均值只以实际有效权重作分母，积分只累加已知面积。下游 `select` 会为可用的部分估值保留 `ESTIMATED` 质量，统计结果的 `status` 与质量应一起读取。端点差分仍需要两个可判定的边界。输出在确认的观察范围内保持到下一次更新或真实终点。缩短 `step` 会增加离散采样，短于步长的越界仍可能漏检。

即使此前窗口已经完整覆盖，只要端点变化率或拟合斜率实际用到一个估算读数，`report` 就保留计算值并标为估算，`strict` 则不提供数值。
