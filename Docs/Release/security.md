# 依赖安全说明

## DBC解析依赖的磁盘缓存公告

本发行的默认CAN依赖 `cantools==39.4.3` 会安装 `diskcache`。核对版本 `diskcache==5.6.3` 存在 [CVE-2025-69872](https://github.com/advisories/GHSA-w8v5-vhqr-4h9v)：攻击者能写入缓存目录时，应用读取其中的pickle内容可能执行恶意代码。公告未列出已修复版本。

Chronaxis的五处DBC加载只传文件名，沿用cantools的 `cache_dir=None`；不创建或读取这类磁盘缓存，也不向配置开放该参数。发行校核检查了全部调用，并在禁止构造 `diskcache.Cache` 的条件下实际解析合成DBC。

这是当前使用路径的限制，不表示diskcache自身漏洞已修复。同一Python环境中的其他应用若自行启用该缓存，仍需按它们的使用方式评估。后续升级依赖或开放缓存功能时必须重新检查。

说明依据：2026-11-02查询PyPI官方版本安全公告，并核对本发行实际安装代码。未命中公告不等于不存在未知漏洞。维护者：liuyaoze。
