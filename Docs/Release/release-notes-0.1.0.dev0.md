# Chronaxis 0.1.0.dev0

这是Chronaxis的首个开发预览版。项目将日志读取、条件筛选和指标计算整理为可复用的Python分析库，可通过YAML/JSON配置或Python API运行。

## 主要功能

- BLF、ASC、原始报文CSV、已解码信号CSV和内存数据输入。
- 连续条件、迟滞去抖、请求响应与超时、事件前后窗口等分析。
- 积分、能量、时长与统计指标；按需生成可读结果表、贡献明细或原始报文片段。
- 连续多文件分析、独立批量任务、DBC信号绑定和按需解码。
- 中英文用户手册、字段/API参考和可直接阅读的AI指南；安装自动带入CAN依赖。

## 使用与验证范围

当前验证环境为Windows、Python3.12。配置格式为`config_version: 3`；软件版本号与配置格式版本独立。开发预览版的接口可能调整，升级前参阅[版本规则](versioning.md)。

本次发行经过干净源码构建、包元数据、独立环境安装和合成任务检查。详细结果随交付清单提供；其他操作系统、浏览器视觉及独立AI试读不在本次已验证范围。已有[diskcache依赖限制](security.md)保留，Chronaxis未启用其磁盘缓存。

项目采用MIT许可证；维护者liuyaoze，work@liuyaoze.com。

## English

This is the first development preview of Chronaxis, a reusable Python library for reading logs, selecting conditions and computing metrics through YAML/JSON configurations or a Python API.

- Inputs: BLF, ASC, raw CAN CSV, decoded signal CSV, and in-memory data.
- Analysis: sustained conditions, hysteresis/debounce, request/response and timeout rules, and event windows.
- Results: integrals, energy, durations and statistics, with readable tables, contributions or raw CAN excerpts when requested.
- Continuous multi-file analysis, independent batch jobs, DBC bindings and decoding of required messages.
- Chinese and English manuals, field/API references, and directly readable AI guides. Normal installation includes CAN dependencies.

Verified on Windows with Python 3.12. Configuration format `config_version: 3` is independent of the software version. Preview interfaces may change; see the [version policy](versioning.md). Checks cover clean-source builds, package metadata, isolated installation and synthetic tasks; other operating systems, visual browser review and independent AI usability testing are not claimed. The documented [diskcache limitation](security.md) remains; Chronaxis does not enable that disk cache.

MIT license. Maintainer: liuyaoze, work@liuyaoze.com.
