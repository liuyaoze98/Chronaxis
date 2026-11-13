# 第三方代码和依赖

Chronaxis 采用 MIT 许可证。运行依赖独立安装，各自的许可证不会因本项目采用 MIT 而改变。当前 CAN 读写和解码调用 python-can、cantools 等依赖。

当前运行包的 CAN 读取、解码和 BLF 写出使用共用实现，不包含历史 Sclicer 的 vendor 副本。原项目快照仅作为内部迁移对照资料，不随运行包分发。

文档离线 HTML 使用 marked 渲染，并包含 highlight.js 高亮样式。仅安装在开发环境的工具不自动成为发行内容；许可核对以实际交付文件为准。

## 本轮核对的组件

以下版本来自本轮依赖环境及随包 METADATA／许可证；版本范围见 `pyproject.toml`。端点的许可检查不自动代替未来每个中间版本或不同平台二进制包的检查。

| 组件 | 核对版本 | 随包许可 |
|---|---|---|
| NumPy | 1.26.3、2.1.0、2.5.4 | 本体 BSD-3-Clause；具体 wheel 还带构建所用的第三方代码与运行库许可，见下文。 |
| ruamel.yaml | 0.19.1 | MIT |
| python-can | 4.6.1 | LGPL-3.0-only |
| cantools | 39.4.3、45.1.2 | MIT |
| natsort | 8.4.0 | MIT |
| jsonschema | 4.25.1、4.26.0 | MIT |
| highlight.js，HTML样式 | 11.11.1 | BSD-3-Clause；[完整许可](ThirdParty/highlight.js-LICENSE.txt) |
| marked，构建工具 | 17.0.5 | MIT及随附Markdown条款；[完整许可](ThirdParty/marked-LICENSE.txt) |

核对的 Windows NumPy 1.26.3 wheel 许可证还列出 OpenBLAS、LAPACK、GCC运行库例外和 libquadmath LGPL 条款。2.1.0 的 Windows wheel 随包许可列出 OpenBLAS、LAPACK 与 GCC 运行库例外，没有列出旧包中的 libquadmath。2.5.4 的 METADATA 列出 `BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0`，随包许可另包含其二进制构建所用的 OpenBLAS、LAPACK 和 GCC 运行库例外。不能把 NumPy 源码的 BSD 标题当作整个二进制 wheel 的全部条件，也不能把某个旧 wheel 的库清单套用到所有新 wheel。

传递依赖也属于再分发核对范围。例如本轮 packaging 包附 Apache-2.0 或 BSD-2-Clause 双许可，typing_extensions 采用 PSF-2.0，wrapt 采用 BSD；其余包以实际安装文件为准。cantools 的 diskcache 依赖和安全边界见[依赖安全说明](security.md)。diskcache 的简短许可告知不能代替再分发时需要的完整许可文本。

## 不同交付形式的核对范围

| 交付形式 | 应核对的内容 |
|---|---|
| Chronaxis wheel／sdist | 自有源码、随包AI资料、模板及实际复制的第三方资源；依赖仅由元数据声明，不把所有依赖源码或DLL复制进该包。sdist还包含用于复建的公开工具与许可。 |
| 离线依赖目录／wheelhouse | 每个独立wheel及其完整许可文件；保留原包，不剥离 `.dist-info` 中的版权、许可或通知。 |
| 捆绑解释器和依赖的便携包／冻结程序 | 实际包含的Python、扩展模块、DLL、浏览器资源及传递依赖，另核源码提供和修改／替换组件等条件。不能沿用普通wheel的结论直接宣布合规。 |

python-can 的 LGPL-3.0-only 条件不因安装方式或本项目 MIT 许可证而消失。再分发包含它的组合程序时，应按随包 LGPL/GPL 条款保留版权、完整许可和适用通知，并落实适用的组件修改、重新组合／替换、对应源码和安装信息要求；冻结后的可替换性不能靠一句“使用动态链接”代替核对。此页记录实际依赖与分发边界，不宣称尚未制作的便携包已完成许可验收。

维护者：liuyaoze。核对日期：2026-11-11。
