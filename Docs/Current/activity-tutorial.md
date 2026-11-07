# 完整任务：事件、窗口与能量

本例的[实际运行结果、CSV下载及数值解析](example-results.md#activity-yaml)随手册提供，可边读边核对。

本任务先识别温度持续过高的活动，再取活动前后各1秒的数据，并分别计算活动能量和窗口能量。`rules`生成事件，`windows`生成片段，`calculations.scope`选择对哪一种范围计算。前提是完成[安装](installation.md)并理解[CAN快速开始](quickstart.md)。

## 输入与完整配置

输入为[activity.asc](examples/data/can/activity.asc)和[teaching.dbc](examples/data/can/teaching.dbc)，完整带注释配置为[activity.yaml](examples/activity.yaml)。把配置与data目录一起保存，保持相对位置。

| 时间（s） | 温度（degC） | 功率（W） |
|---|---|---|
| 0 | 70 | 10 |
| 1 | 80 | 10 |
| 3 | 80 | 10 |
| 6 | 70 | 10 |
| 7 | 70 | 10 |

本例保留valid_for=4s，以覆盖最长3秒的更新间隔；不填写domain，自动分析实际观测的[0,7)。温度与功率的类型、单位从DBC读取，末条记录确定观测终点。

## 来源与信号绑定

以下摘录[activity.yaml](examples/activity.yaml)的根级sources和signals，先看temperature和power绑定到哪个CAN信号；下载文件中已包含，不要重复追加。

```yaml
sources:                          # 列出输入来源；每项规定数据位置、格式和时间解释方式
  - paths: data/can/activity.asc  # 选择输入文件、连续分卷列表或目录；相对路径基于本配置，目录按自然序读取
    dbc_by_channel:               # 为每个CAN通道指定解码用DBC文件；键是通道编号的字符串
      '1': data/can/teaching.dbc  # 为这个通道指定DBC文件；路径相对当前配置文件，通道键须为字符串
signals:                          # 把输入字段定义为有名称、类型、单位和有效期的分析信号
  - name: temperature             # 给分析信号取名称；后续表达式和计算通过此名称引用它
    field:                        # 指定来源中的原始字段；CSV填表头，CAN填写通道/报文ID/DBC信号名
      frame_id: '0x11d'           # 选择包含信号的报文ID；从对应DBC取得，可写整数或支持的进制文本
      signal: Temperature         # 填写DBC中的信号名称，大小写须一致
    valid_for: 4s                 # 设置一次有效更新最多沿用多久；依据采样周期和允许数据陈旧程度填写
  - name: power                   # 给分析信号取名称；后续表达式和计算通过此名称引用它
    field:                        # 指定来源中的原始字段；CSV填表头，CAN填写通道/报文ID/DBC信号名
      frame_id: '0x100'           # 选择包含信号的报文ID；从对应DBC取得，可写整数或支持的进制文本
      signal: Power               # 填写DBC中的信号名称，大小写须一致
    valid_for: 4s                 # 设置一次有效更新最多沿用多久；依据采样周期和允许数据陈旧程度填写
```

## 三个配置部分如何配合

以下摘录activity.yaml的根级rules、windows、calculations；这些是阅读用摘录，不是从空白文件新建的完整配置。请下载上面的activity.yaml；调整时只替换其中同名的rules、windows、calculations段，保留config_version、dataset、sources和signals。下载文件已包含这些内容，不要重复追加。

```yaml
rules:                             # 列出识别活动或瞬间变化的规则；每项产生有独立ID的事件
  - name: hot                      # 为规则取唯一名称；窗口rule和计算scope通过此名选择它的事件
    rule_type: condition_duration  # 选择活动或变化识别算法；本例条件连续成立达到minimum_duration后确认活动
    condition: temperature >= 80   # 填写由已定义信号组成的真假条件；按要检测的业务情况设置
    duration_comparison: ">="      # 达到门槛即满足；要求严格超过时填>
    minimum_duration: 2s           # 设置条件连续成立多久才确认活动；时长阈值由业务要求决定
windows:                           # 围绕已定义规则的事件选取时间片段，供计算或导出使用
  - name: hot_context              # 为窗口定义取唯一名称；计算或导出通过此名选择产生的片段
    rule: hot                      # 选择生成窗口的事件规则；填写前面rules中的name
    pre: 1s                        # 设置起点之前保留多久上下文；0s表示不提前
    post: 1s                       # 设置结束点之后保留多久上下文；0s表示不延长
calculations:                      # 列出希望获得的统计或积分结果，每项独立选择范围和算法
  - name: event_energy             # 为这项计算结果取唯一名称；结果表用它区分计算项
    scope:                         # 选择计算范围；session整段会话，{rule: 名称}逐事件，{window: 名称}逐片段
      rule: hot                    # 按指定规则的每次事件分别计算；填写前面rules中的name
    operation: integral            # 选择计算方法；本例将有效数值乘持续时间后累计，例如功率乘秒得到能量
    expr: power                    # 指定参与计算的数值或信号表达式；引用前面已定义的信号
  - name: context_energy           # 为这项计算结果取唯一名称；结果表用它区分计算项
    scope:                         # 选择计算范围；session整段会话，{rule: 名称}逐事件，{window: 名称}逐片段
      window: hot_context          # 按指定窗口的每个片段分别计算；填写前面windows中的name
    operation: integral            # 选择计算方法；本例将有效数值乘持续时间后累计，例如功率乘秒得到能量
    expr: power                    # 指定参与计算的数值或信号表达式；引用前面已定义的信号
```

## 运行并核对

从仓库根运行；离线包examples目录中则把配置路径改为activity.yaml。activity-result可重复使用，每次输出自动增加时间后缀。

```powershell
chronaxis validate Docs/Current/examples/activity.yaml
chronaxis run Docs/Current/examples/activity.yaml --output activity-result
```

| 输出 | 应核对的事实 |
|---|---|
| 事件结果.csv | 一次hot活动：开始1秒、确认3秒、结束6秒；event_energy（J）为50，状态“完整”。 |
| 窗口结果.csv | 一段hot_context窗口：[0,7)秒，父事件区间为1；context_energy（J）为70，状态“完整”。 |

10W在活动内保持5秒，因此50J；前后窗口共7秒，因此70J。将selection_origin改为confirmed时，活动计算改为[3,6)，得到30J；窗口仍为[0,7)，仍得到70J。只更改这个字段，其他数据与配置保持一致，便于理解差异。

如果自己数据的结果为partial，先检查观测范围和valid_for，再读[部分结果处理](execution.md)；增大pre/post只扩大请求范围，不会增加真实观测。
