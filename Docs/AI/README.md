# 用 AI 编写 Chronaxis 分析

[English guide](en/README.md)

从这份README开始，再按[任务索引](tasks.json)选择相关示例，只读任务需要的说明。阅读源码中的指南无需先安装Chronaxis、生成文件或导出ZIP；保留仓库目录结构即可。独立资料ZIP使用同一正文，解压时保留完整目录结构。

先向AI提供本README和[资料版本信息](../Current/documentation.json)，再按需提供示例、接口或字段说明。未另行注明的相对命令以本README所在目录为起点；已安装环境使用下方工作目录示例；配置内部的ASC、DBC路径相对配置文件所在目录。运行分析需要安装匹配版本的Chronaxis，可用 `python -c "from importlib.metadata import version; print(version('chronaxis'))"` 核对。安装包已经附带普通指南文件，`python -m chronaxis guide`只显示中文README的路径，`--language en`选择英文，不写入或解压资料。源码指南同样直接阅读。资料版本与合成示例不代表私人日志已通过验证。

### 在已安装环境中直接使用

从自己的工作目录执行下列PowerShell命令。它直接读取安装目录的指南和示例，结果写到当前工作目录，不复制或修改安装资料：

```powershell
$guide = Split-Path (python -m chronaxis guide)
python "$guide/lookup.py" task CONDITION_ENERGY
python "$guide/run_analysis.py" "$guide/examples/conditional-energy.yaml" result-energy
```

下文的相对命令展示源码/独立指南目录用法；在安装环境执行时，也可像上面一样使用完整输入路径和自己的输出目录。

## 安装Chronaxis及默认运行依赖

普通安装本地 wheel 就会自动安装完整运行依赖，支持 BLF、ASC、原始报文 CSV、DBC 解码、已解码信号 CSV 和内存任务；无需添加 `[can]`。下面是在 Windows PowerShell 中创建环境并安装的完整命令；将 wheel 路径替换为实际收到的文件：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install ".\chronaxis-0.1.0.dev0-py3-none-any.whl"
.\.venv\Scripts\python.exe -m pip check
```

在后续命令中用同一个 `.venv\Scripts\python.exe`；无需激活环境。该版本声明并已验证的 CAN 依赖为 `python-can==4.6.1`、`cantools==39.4.3`、`natsort==8.4.0`，由 wheel 的默认依赖统一安装。不要为了消除缺模块错误单独安装任意最新版，也不要更改信号、阈值或 DBC。其他依赖版本不代表已验证支持；实际发布物以其安装元数据为准。本项目未声明发布到在线包索引，不能假定 `pip install chronaxis` 会取得这个包。离线安装须事先备齐依赖。

`dependency_missing` 表示运行环境缺少 CAN 依赖，不是信号绑定内容错误；按错误中的本地 wheel 安装命令修复。即使全部信号元数据已经手填、静态校验通过，实际运行仍需要相应读取/解码依赖。

## 我该读哪几份文件？

第一次使用时先读[从输入到结果](workflow.md)，决定走单次计划、预设还是批量。

1. 从 [任务索引](tasks.json) 找中文需求，只读命中条目的范例、适用条件和相关字段。先用 BLF/ASC＋DBC 场景；已解码信号表用 CSV，不需要 DBC。不要把别的发布版的配置或内部函数混进来。
2. 写分析配置，使用 YAML 或 JSON，分析版本为整数 3。范例是完整文件；保留 ../Current/examples/data 相对位置。示例工程数值只适用于合成输入。缺真实时间基准、工程阈值、编码、单位或方向依据时，指出哪项缺失以及它会改变什么结果。
3. 写 Python，查 [公开 API 索引](../Current/public-api.json)，再读对应单个 API 文件。文件用 load_analysis_plan，已展开字典用 AnalysisPlan.from_dict。预设构建得到 PlanFragment，不能直接交给 run。批量返回时逐任务核对状态。
4. 配置加载 → 检查声明 → 查看依赖 → 运行 → 写出结果。可用命令见下方；Python方式见 [完整调用](run_analysis.py)。报告实际输入、单位、边界、质量和未验证项。计算返回不代表发布完成。

## 一个从输入到结果的任务

需要具体参数时，用标准 Python 在本README所在目录查询，不用读取整份规范：

```text
python lookup.py task 持续
python lookup.py api AnalysisRunner
python lookup.py field valid_for --schema analysis
python lookup.py field source_type --schema analysis --branch can_asc
```

字段表给出原规范位置及分支。参见[高风险语义与真实诊断](semantics.md)及[完整字段参考](../Current/reference/configuration-schema.md)。条件必填、引用、时间单位和工程契约以完整规范及运行校验为准，不应把独立分片用作验证器。没有匹配项返回退出码1；先查正确的版本、名称或分支，不自动猜同义字段。

在这份资料的目录运行（Windows/Python 3.12，已安装项目默认运行依赖）：

```text
python -m chronaxis config init --list
python -m chronaxis validate ../Current/examples/conditional-energy.yaml --format json
python -m chronaxis explain ../Current/examples/conditional-energy.yaml --format json
python run_analysis.py ../Current/examples/conditional-energy.yaml result-energy
```

这个例子连续读取两卷ASC，用DBC解码状态、电流和电压，要求`state == 0x2 and current >= 10`连续严格超过60秒，再对整个合格事件积分。恰好60秒的第一段被排除；第二段跨越分卷，实际区间为[61,122)秒，结果4000×61/3600000＝0.06777777777777777kWh。默认从条件开始时刻积分，包括最初60秒；`confirmed_ns=121000000001`表示严格超过60秒的确认时刻，不是积分起点。完整配置位于任务`CONDITION_ENERGY`；预设`CHARGE`采用不同电流比较时，不能替代这个任务。

结果目录必须是新的。默认readable_csv在`事件结果.csv`同一行给出精确秒起止和energy_kwh（kWh），先检查每项指标的状态和说明；从run_manifest.json.outputs找到实际文件。原程序交换格式须显式设置outputs.tables为csv或jsonl，才按parent_id关联原表；CLI与清单中的`analysis_outcome`区分无观测、未知、条件未成立、时长不足和已有事件。没有事件不等于能量为0。换成自己的数据时按实际DBC替换路径、ID、信号和条件；已解码信号表仍可选`CSV`任务，不应用合成阈值替用户决定生产参数。

分析命令和配置解释只证明声明和执行路径；加载按需可读 DBC 元数据、展开来源目录，不扫描业务记录。真实运行、输出和关闭完成后才报告成功。独立样例不能证明其他设备具有相同含义。
