# 依赖安全说明

## DBC 解析与磁盘缓存

`diskcache<=5.6.3` 存在 [CVE-2025-69872](https://github.com/advisories/GHSA-w8v5-vhqr-4h9v)：攻击者能写入缓存目录时，应用读取其中的 pickle 内容可能执行恶意代码。2026-11-11 核对的公告没有列出已修复版本。

本轮实际安装的 cantools 39.4.3 将 diskcache 列为默认依赖；45.1.2 将它放在 `cache` 额外依赖组，新建最高组合环境没有安装 diskcache。不能因此宣称整个允许版本范围都不带 diskcache；升级已有环境也不保证删除此前安装的包。

Chronaxis 的 DBC 文件读取统一经过 `chronaxis.dbc_loading.load_dbc_file`。入口按 cantools 原规则确定文件格式与编码，以 `errors="replace"` 打开文件，再调用官方 `cantools.database.load`。DBC/SYM 使用 cp1252，其他扩展名使用 UTF-8；保留原来的严格解析、枚举名称和信号排序规则，文件读取与解析各进行一次。这个接口不进入 `load_file` 的磁盘缓存分支，任务内已加载数据库的复用照常进行。

这样处理的原因是 cantools 45.1.2 的 `load_file(cache_dir=None)` 仍会采用 `CANTOOLS_CACHE_DIR` 环境变量。Chronaxis 不通过修改全局环境变量禁用缓存，也不向配置开放磁盘缓存。缓存目录已由环境设置、diskcache 已安装或可导入时，同样不得创建或读取该缓存。

静态规则检查现役源码中的直接调用、常见别名和显式 `getattr`，确保 DBC 文件读取经过统一入口。运行测试覆盖有无缓存环境变量、缓存对象可用、非 ASCII 内容、非法扩展名和解析失败，并核对与无缓存 `load_file` 的值、元数据、错误及一次读取行为。静态检查不是对任意动态 Python 代码的安全证明；对应测试结果和依赖组合分别保留在验收记录中。

这是 Chronaxis 使用路径的限制，不是 diskcache 漏洞修复。同一 Python 环境中的其他应用若自行读取该缓存，仍需单独评估。以后升级 cantools、改变 DBC 读取入口或提供便携包时，应重新检查实际代码、依赖及缓存使用方式。

说明依据：2026-11-11 安装包 METADATA、随包实现及上述公告。维护者：liuyaoze。
