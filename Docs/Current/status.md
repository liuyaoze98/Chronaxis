# 支持范围与限制

本手册对应 Chronaxis 0.1.0.dev4，分析配置必须使用整数 `config_version: 4`。本版支持单位自动换算、统计、滚动计算和变化率。按[安装说明](installation.md)安装同版源码或本地 wheel 后运行示例；旧版用户请先阅读[升级说明](../Release/release-notes-0.1.0.dev4.md)。YAML 适合手写配置，JSON 适合程序交换。

| 能力 | 当前支持范围 |
|---|---|
| 输入 | 内存记录、已解码信号CSV、配DBC的BLF/ASC/原始CAN CSV；文件数量、通道及格式限制见[来源指南](inputs.md)。 |
| 分析 | 表达式、持续条件、边沿、迟滞、去抖、起止活动、窗口变化、请求响应配对、事件窗口、统计与积分、逐消息累计。 |
| 版本 4 扩展 | 单位自动换算、分支表达式、查表、方差与分位数、结果聚合、滚动统计和变化率；分别见[表达式](expressions.md)、[统计](calculations.md)及[滚动计算](temporal-transforms.md)。 |
| 同帧累计 | fast run支持一个ASC/BLF来源的连续分卷，按配置并行读取、解码和求单帧贡献，主进程逐条累计；fast batch用于独立试验。见[高性能积分器](fast-energy.md)。 |
| 执行 | Python API与CLI，reference/numpy两种计算实现，独立批量任务、[同一会话多文件并行读取](continuous-files.md)，内存/暂存预算管理。 |
| 输出 | CSV或JSONL摘要、运行清单、按需贡献/输入追溯、信号CSV与CAN报文导出。 |
| 配置工具 | 模板生成、YAML/JSON转换、独立配置导出、单层公共定义、字段来源查询。 |
| 环境 | Python `>=3.12,<3.14`；Windows，以及满足进程与文件系统能力要求的Linux。实际核验环境和未覆盖的平台组合见[安装说明](installation.md)。结果关闭后以统一时间后缀发布，不覆盖旧文件，完成清单最后发布；见[结果发布](results.md#result-publication)。 |

## 需要自行确认的条件

数据的时间同步依据、信号单位、方向、测量位置、有效期和业务阈值需要由使用者确认。加载配置不读取业务报文；省略信号dtype、unit、period或枚举choices时，程序可按对应规则从DBC补齐；仍须提供报文frame_id和信号signal，通道仅在唯一时可省略。标准/扩展帧和CAN/FD标志可自动确定，候选不唯一时须补填。具体条件见[信号绑定](signals.md)与[来源](inputs.md)。读取DBC仍无法证明业务输入内容正确；合成示例可核对计算方法，不能证明真实设备的业务结果。

内存预算只覆盖受管理资源，不是整个Python进程的硬上限。多任务并行或NumPy实现不保证所有输入都加速，应基于实际任务测量。
