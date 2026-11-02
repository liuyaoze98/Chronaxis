# 连续满足条件后，对整个区间积分

本例完成一个明确任务：状态为`0x2`、电流`>=10A`，两个条件连续成立**超过60秒**后，对整个合格区间的`电流×电压`积分，单位为kWh。先筛选完整区间，再计算该区间的能量；最初60秒也计入。

这里使用随册合成ASC和DBC，不代表任何真实车辆的状态定义、电流方向或能量结果。配置只声明本次条件和积分需要的内容。

## 下载、安装和运行位置

保留以下相对目录，或复制整份`examples`目录：

| 文件 | 用途 |
|---|---|
| [conditional-energy.yaml](examples/conditional-energy.yaml) | 完整配置，可直接运行。|
| [part-1.asc](examples/data/can/conditional-energy/part-1.asc) | 第1卷，0～89秒。|
| [part-2.asc](examples/data/can/conditional-energy/part-2.asc) | 第2卷，90～123秒；延续上一卷的条件状态。|
| [signals.dbc](examples/data/can/conditional-energy/signals.dbc) | 合成报文0x100的状态、电流、电压及1000ms周期。|

在Windows PowerShell中，从包含wheel和`examples`的工作目录执行；把wheel文件名替换为实际收到的版本。普通安装会自动安装这个发布包声明的CAN依赖，无需额外指定依赖组；不要随意更换cantools版本。离线机器需要事先准备这些依赖的wheel，见[安装](installation.md)。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install ".\chronaxis-0.1.0.dev0-py3-none-any.whl"
.\.venv\Scripts\python.exe -m chronaxis validate examples/conditional-energy.yaml --format json
.\.venv\Scripts\python.exe -m chronaxis explain examples/conditional-energy.yaml --format json
.\.venv\Scripts\python.exe -m chronaxis run examples/conditional-energy.yaml --output result-conditional-energy
```

命令里的配置和输出路径相对**命令运行目录**。配置内部的ASC和DBC路径相对**配置文件所在目录**，因此不必把工作目录切换到数据目录。输出目录必须是新的；再次运行时换一个目录名，避免覆盖已生成的结果。

两卷在同一个来源的`paths`中，按所列顺序连续读取，信号保持和条件计时会跨卷延续。不能把这两卷当成两个独立批量任务；那样90秒处会重新开始状态。不同试验的文件则应使用[独立批量任务](batch.md)。

## 完整配置与可省略内容

下方是可下载配置的原文。`sources`、`signals`、`rules`、`calculations`是并列的根级字段；短横线表示列表项，缩进表示父子关系。例如`scope`下缩进的`rule`写在同一个计算项内，不是一个名为`scope.rule`的字面键。基础语法见[配置写法](configuration-language.md)。

```yaml
# 合成教学示例：两个条件连续超过60秒，再对整个合格区间积分。
config_version: 3                                     # 当前配置结构版本
dataset:                                              # 本次分析
  name: conditional_energy                            # 结果使用这个任务名称
sources:                                              # 两卷连续文件组成一个来源
  - paths:                                            # 按下面的先后顺序读取，跨文件保持状态
      - data/can/conditional-energy/part-1.asc        # 0～89秒
      - data/can/conditional-energy/part-2.asc        # 90～123秒
    dbc_by_channel:                                   # 用户通道从1开始；内部编号自动匹配
      '1': data/can/conditional-energy/signals.dbc    # 相对本配置文件的位置
signals:                                              # 唯一来源和通道可省略；类型、单位和周期由DBC取得
  - name: state                                       # 用整数状态直接比较，无需映射成布尔或枚举
    field:                                            # DBC中的报文与信号
      frame_id: '0x100'                               # 十六进制报文ID
      signal: State                                   # DBC中的状态信号
  - name: current                                     # 电流，DBC单位A
    field:                                            # 与状态在同一报文中
      frame_id: '0x100'                               # 相同ID
      signal: Current                                 # DBC中的电流信号
  - name: voltage                                     # 电压，DBC单位V
    field:                                            # 与状态在同一报文中
      frame_id: '0x100'                               # 相同ID
      signal: Voltage                                 # DBC中的电压信号
rules:                                                # 先找合格区间
  - name: eligible                                    # 积分通过这个名称选择区间
    rule_type: condition_duration                     # 要求条件连续成立
    condition: state == 0x2 and current >= 10         # 状态为2且电流至少10A
    minimum_duration: 60s                             # 持续时长门槛
    duration_comparison: ">"                          # 严格超过；恰好60秒不合格
calculations:                                         # 只请求所需的能量结果
  - name: energy_kwh                                  # 结果表中的计算项名称
    operation: integral                               # 按实际时间积分
    expr: current * voltage                           # A×V得到W，乘时间后转为kWh
    scope:                                            # 选择整个合格事件区间
      rule: eligible                                  # 默认onset，包含最初60秒
    unit: kWh                                         # 直接输出kWh，不在外部再换算
```

ASC/BLF格式自动识别；唯一来源及通道不用在每条信号中重复。配置中的通道1由程序匹配内部编号，不需要用户减1。DBC已经包含类型、单位和报文周期；本例省略`valid_for`，运行时使用1000ms的3倍，即3秒。这里的3秒是旧样本最多能沿用多久，积分仍按两条实际记录之间的时间计算，不能把3秒误当积分步长。

本例也省略了默认`selection_origin: onset`、实际时间间隔模式和默认结果输出。`duration_comparison: ">"`必须明确填写，因为省略时是`>=`。状态直接保留整数，表达式中的`0x2`等于十进制2，无需先配置bool或enum映射。更换真实数据时，报文ID、信号名和状态编码以实际DBC及设备定义为准。

## 输入发生了什么，为什么只有一条能量结果

电流始终是10A，电压始终是400V，每秒更新一次；状态变化如下：

| 时间范围（秒） | 状态 | 两个条件是否成立 | 是否输出能量 |
|---|---|---|---|
| [0,60) | 2 | 成立，连续60秒整 | 否，严格`>60s`不接受恰好60秒。|
| [60,61) | 0 | 不成立 | 否。|
| [61,122) | 2 | 成立，连续61秒；90秒处跨文件 | 是，对完整61秒积分。|
| [122,123) | 0 | 不成立 | 否。|

手算功率为10×400＝4000W，能量为4000×61＝244000J；1kWh＝3600000J，所以结果为 **0.06777777777777777kWh**。电流恰好10A仍满足`>=10`。如果改用充电预设的`current_min: 10`，预设采用`>10`，会得到不同结果；入口选择见[预设适用范围](presets.md#先判断充电预设是否符合目标)。

## 实际输出与解释

普通配置默认输出一张[事件结果.csv](examples/results/conditional-energy-yaml/事件结果.csv)，起止时间和能量在同一行，没有额外的贡献明细或输入追溯。[状态摘要](examples/results/conditional-energy-yaml/result-summary.json)摘取真实运行清单的必要信息。

| 区间 | 开始时间（s） | 结束时间（s） | 区间状态 | energy_kwh（kWh） | energy_kwh：状态 |
|---|---|---|---|---|---|
| 1 | 61 | 122 | 正常结束 | 0.06777777777777777 | 完整 |

只有61秒长的活动合格，60秒整的活动被排除；积分范围为[61,122)，包括最初的60秒。确认时刻是121.000000001秒，代表从61秒开始严格超过60秒的第一个整数纳秒时刻，它不改变积分起点。本例只要整段积分，普通表不额外保存确认时刻；需要底层事件时可使用iter_events。

清单analysis_outcome.rules显示eligible找到1个事件且has_unknown为false；calculations.complete为1，表示一项计算完整，不是能量值。能量直接读取energy_kwh（kWh）列，无需再换单位。completed只代表任务及结果发布成功，是否完整仍看每项指标的状态。

不必再编写跨表关联脚本。如果需要在Python里读取这张表，可保存为show_energy.py：

```python
"""读取已发布的合格区间能量，不扫描ASC或重复计算。"""
import csv
from pathlib import Path

# 一行已经包含本区间的实际起止、能量及状态。
path = Path("result-conditional-energy") / "事件结果.csv"
with path.open(encoding="utf-8-sig", newline="") as stream:
    for row in csv.DictReader(stream):
        print(row["开始时间（s）"], row["结束时间（s）"],
              row["energy_kwh（kWh）"], "kWh", row["energy_kwh：状态"])
```

从本例工作目录执行python show_energy.py，输出为61 122 0.06777777777777777 kWh 完整。这里逐行读结果，不把全部区间装入内存。已有程序依赖原events.csv/calculations.csv时，显式选择outputs.tables: csv，详见[交换格式](results.md#为程序选择交换格式)。

## 换成自己的ASC或BLF

替换`paths`、DBC路径和三条信号的ID/名称，保留你要的比较符、持续时长及kWh。需要严格超过60秒就继续使用`>`；不能改为60.1秒，也不能为了跑通而修改日志时间。普通ASC分析会检查所需通道和报文的时间顺序，无关帧只在确有需要时参与来源范围；显式完整检查或原帧导出仍要求全量顺序。目标报文回退应报告原位置，不自动排序或清洗。

本例证明这份合成输入的跨文件连续判断和能量计算，不能证明任意私人日志、设备编码或业务方向正确。独立核验也应保留同样的有效期、先后顺序和边界；自行排序后的脚本即使总量相同，也不能声称验证了全部这些规则。
