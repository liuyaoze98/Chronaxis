# BLF／ASC快速开始：直接计算报文中的能量

本例直接读取CAN日志，用DBC取出功率并计算能量、样本均值和时间加权均值。无须先转CSV，也无须写Python入口。先完成[安装](installation.md)，再按以下步骤运行。随附报文是合成教学数据，不代表真实设备。

## 准备日志和DBC

使用随册的[quickstart.asc](examples/data/can/quickstart.asc)与[teaching.dbc](examples/data/can/teaching.dbc)。ASC文字通道1在配置中填写1；DBC的0x100报文含Power信号，单位W。日志解码后的数据如下：

|实际时间|报文|本次值|
|---|---|---|
|0秒|0x100|Power=2W|
|1秒|0x100|Power=4W|
|3秒|0x100|Power=8W|
|4秒|0x100|Power=10W|
|6秒|0x7FE|另一条报文，只确定日志观测到6秒|

末条不是新的功率样本。程序用前值保持计算[0,6)秒，默认按实际时间间隔积分。采样时间不等距，因此样本均值和时间加权均值不同。

## 保存配置并运行

完整文件是[analysis.yaml](examples/analysis.yaml)。保留它与data子目录的相对位置；相对路径从配置文件所在目录计算。

下面使用YAML：没有缩进的键位于根级，缩进两格表示属于上一层，`-`表示列表中的一项。例如`name`缩进在`dataset`下，字段参考把它写成`dataset.name`；不要把这个点号路径直接复制成配置键。第一次编辑请先看[字段路径怎样写成配置](configuration-language.md#field-paths)。

```yaml
config_version: 3                     # 声明分析文件采用的字段结构版本；当前填写整数3
dataset:                              # 设置本次分析名称及可选的对象、会话和时间范围
  name: energy                        # 命名本次分析数据集；名称写入结果身份字段
sources:                              # 列出输入来源；每项规定数据位置、格式和时间解释方式
  - paths: data/can/quickstart.asc    # 选择输入文件、连续分卷列表或目录；相对路径基于本配置，目录按自然序读取
    dbc_by_channel:                   # 为每个CAN通道指定解码用DBC文件；键是通道编号的字符串
      '1': data/can/teaching.dbc      # 为这个通道指定DBC文件；路径相对当前配置文件，通道键须为字符串
signals:                              # 把输入字段定义为有名称、类型、单位和有效期的分析信号
  - name: power                       # 给分析信号取名称；后续表达式和计算通过此名称引用它
    field:                            # 指定来源中的原始字段；CSV填表头，CAN填写通道/报文ID/DBC信号名
      frame_id: '0x100'               # 选择包含信号的报文ID；从对应DBC取得，可写整数或支持的进制文本
      signal: Power                   # 填写DBC中的信号名称，大小写须一致
calculations:                         # 列出希望获得的统计或积分结果，每项独立选择范围和算法
  - name: energy                      # 为这项计算结果取唯一名称；结果表用它区分计算项
    operation: integral               # 选择计算方法；本例将有效数值乘持续时间后累计，例如功率乘秒得到能量
    expr: power                       # 指定参与计算的数值或信号表达式；引用前面已定义的信号
  - name: sample_average              # 为这项计算结果取唯一名称；结果表用它区分计算项
    operation: sample_mean            # 选择计算方法；本例对范围内有效真实样本等权求平均，每个样本计一次
    expr: power                       # 指定参与计算的数值或信号表达式；引用前面已定义的信号
  - name: time_average                # 为这项计算结果取唯一名称；结果表用它区分计算项
    operation: time_weighted_mean     # 选择计算方法；本例按有效值持续时长加权求平均
    expr: power                       # 指定参与计算的数值或信号表达式；引用前面已定义的信号
```

这份配置只给数据集取一个名字，选择日志、DBC、所需信号和三项计算。无需另填session、entity、source_type、time_type、唯一来源引用或scope。类型和单位由DBC取得；单一DBC通道可自动选择。未写domain表示分析实际输入范围。

在examples目录打开终端，执行：

```powershell
chronaxis validate analysis.yaml
chronaxis run analysis.yaml --output new-result
```

输出目录必须尚不存在。validate检查配置并在需要时读取DBC定义；run才读业务日志、计算并发布结果。虚拟环境未激活时，可使用安装页中的`python -m chronaxis`入口。

## 核对结果

打开new-result/会话结果.csv。也可以直接看随册保存的[本例实际运行结果与逐列解释](example-results.md#analysis-yaml)，不必先安装程序才能知道输出长什么样。三项结果应为：

|计算名|手工计算|结果|
|---|---|---|
|energy|2×1 + 4×2 + 8×1 + 10×2|38J|
|sample_average|(2+4+8+10)÷4|6W|
|time_average|38÷6|6.333333333333333W|

三项分别显示“完整”，说明为空；同一行可读到三项数值。共同的数据集、对象和会话名称沿用dataset.name的energy，只在清单保存，不要求另填。可通过[Python API](api-usage.md)读取同样结果。

## 直接试用目录和BLF

[目录配置](examples/input-can-directory.yaml)直接读取随附的quickstart-parts目录，part1.asc、part2.asc按自然序连接，结果仍为38J、6W和38/6W。

```powershell
chronaxis run input-can-directory.yaml --output directory-result
```

如果还想试同一数据的BLF及ASC/BLF混合目录，在examples目录运行以下脚本；目标目录须不存在。它生成三组相同数值的数据、对应配置，并自动核对三组结果一致。生成文件放到你指定的工作目录，不改手册原输入。

```powershell
python prepare_can_examples.py --output can-demo
chronaxis run can-demo/blf.json --output blf-result
```

文件生成与实际读取验证见[prepare_can_examples.py](examples/prepare_can_examples.py)。用户自己的BLF不需要先运行此生成脚本，直接在配置中选择已有日志即可。

## 换成自己的BLF、ASC或日志目录

1. 把sources中的paths换成自己的文件或连续日志目录。`.blf`与`.asc`自动识别；同一采集的多个文件可一起读取，目录内按自然序排列，例如part2在part10之前。
2. 把dbc_by_channel中的路径改为自己的DBC，键按实际公共通道号填写。ASC文字通道1在配置中填写1。
3. 把field.frame_id和field.signal改为DBC中的报文ID及信号名。ID可写0x十六进制、0b二进制或无前缀十进制；不需要报文名称。
4. dataset.name用于给本次分析取名。只分析某段时间时才增加domain；需要窗口、条件或更多计算时再添加对应功能。

DBC包含报文周期时，省略valid_for默认使用该周期的3倍；DBC没有周期时，再提供period或明确valid_for。单位或方向需要换算时，应按实际定义配置，不能凭信号名称猜测。

如果目录内是多次独立试验，应使用[批量任务](batch.md)，而不是把每次从0秒开始的日志强行连成一次分析。只有CSV输入才需要专门的列配置，见[CSV来源](inputs.md)。

同一配置也提供[JSON文件](examples/analysis.json)。[run_example.py](examples/run_example.py)可复验两种配置表示和两种计算实现；[api_example.py](examples/api_example.py)演示Python调用。
