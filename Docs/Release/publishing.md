# 发布操作流程

[English](publishing.en.md)

从本次交付目录执行以下命令。先完成发布信息确认和本地校核，再依次发布GitHub源码、TestPyPI试装和PyPI正式包。外部上传命令由维护者在确认发布后执行。

## 交付目录

|位置|用途|
|---|---|
|`source/`|已按公开清单导出的源码；在这里建立新的公开Git历史|
|`dist/`|只有wheel和sdist，供TestPyPI/PyPI上传|
|`manual/index.html`、`manual/en/index.html`|中英文离线用户手册|
|`manual/ai-guide/README.md`、`manual/ai-guide/en/README.md`|可直接阅读的AI指南|
|`Chronaxis-Source-0.1.0.dev0.zip`|公开源码的独立压缩副本|
|`Chronaxis-Manual-0.1.0.dev0.zip`|完整双语手册及AI资料，适合作为GitHub Release附件|
|`SHA256SUMS.txt`、`delivery.json`|发行文件摘要、源码与资料版本、验证结果和待补项|

不要直接推送内部开发仓库的完整历史；它包含开发记录和历史业务资料。公开源码使用本目录的`source/`。测试日志和构建暂存保存在交付目录之外。

## 上传前确认

- 本项目仓库为[liuyaoze98/Chronaxis](https://github.com/liuyaoze98/Chronaxis)，包元数据已配置仓库、手册、问题及版本说明链接。PyPI正文在构建时从README生成，将相对文件链接转换为`v0.1.0.dev0`标签下的网页地址；源码README仍支持本地阅读。
- 核对PyPI账户可发布`chronaxis`，目标版本为`0.1.0.dev0`。HTTP 404不等于这个名称一定可注册；账户权限与名称保留状态仍以PyPI为准。
- 公开仓库应在PyPI发布前可访问。MIT、作者liuyaoze和邮箱work@liuyaoze.com已确定。
- 阅读[版本规则](versioning.md)、[第三方说明](third-party.md)和[已知依赖限制](security.md)。已经上传的发行文件不能覆盖；修改后使用新的版本号。

建立专用上传环境并检查待上传的两个文件：

```powershell
$Version = '0.1.0.dev0'
$Wheel = "dist/chronaxis-$Version-py3-none-any.whl"
$Sdist = "dist/chronaxis-$Version.tar.gz"
py -3.12 -m venv .venv-publish
$Python = '.venv-publish/Scripts/python.exe'
& $Python -m pip install --upgrade twine
& $Python -m twine check $Wheel $Sdist
Get-FileHash -Algorithm SHA256 $Wheel, $Sdist
```

两项检查应通过，摘要应与SHA256SUMS.txt相符。上传时明确指定这两个文件，不把手册或源码ZIP当作PyPI安装包。

## GitHub源码与发行附件

先在GitHub创建空仓库，不预先生成README或许可证。如果目标仓库已有提交，先核对其内容，不按下列首次发布步骤覆盖它。

```powershell
$Repository = 'https://github.com/liuyaoze98/Chronaxis.git'
git -C source init -b main
git -C source config user.name liuyaoze
git -C source config user.email work@liuyaoze.com
git -C source add -- src tests examples tools Docs README.md README.en.md LICENSE pyproject.toml setup.py MANIFEST.in .gitattributes .gitignore PUBLIC-SOURCE.json
git -C source diff --cached --stat
git -C source commit -m "Release Chronaxis $Version"
git -C source remote add origin $Repository
git -C source push -u origin main
git -C source tag -a "v$Version" -m "Chronaxis $Version"
git -C source push origin "v$Version"
```

在GitHub Releases中基于此标签先创建草稿，标题用`Chronaxis 0.1.0.dev0`，勾选预发行，正文取[本版说明](release-notes-0.1.0.dev0.md)。附件加入源码ZIP、双语手册ZIP、wheel、sdist及SHA256SUMS.txt。PyPI确认后再发布该草稿。

推送后用未登录浏览器打开仓库、`v0.1.0.dev0`标签以及包元数据中的手册链接，确认外部可读，再上传PyPI。仓库URL已知不代表目前已公开；本地构建检查只核对链接目标文件存在，不能替代这一步。

GitHub Pages为独立的可选发布步骤。若启用，发布`manual/`中的静态页面，并在仓库设置中选择对应的Pages发布来源；仅上传源码不会自动上线手册。本地手册和GitHub Release附件可以先使用。

## TestPyPI试上传与试装

TestPyPI和PyPI使用各自的账户与令牌。运行上传命令后在Twine交互提示中输入对应令牌，令牌不写进项目文件。

```powershell
$env:TWINE_USERNAME = '__token__'
& $Python -m twine upload --repository testpypi $Wheel $Sdist
py -3.12 -m venv .venv-testpypi
$TestPython = '.venv-testpypi/Scripts/python.exe'
& $TestPython -m pip install $Wheel
& $TestPython -m pip install --force-reinstall --no-deps --index-url https://test.pypi.org/simple/ "chronaxis==$Version"
& $TestPython -m pip check
& $TestPython -m chronaxis guide
& $TestPython -m chronaxis guide --language en
```

第一次从本地wheel安装用于从正常索引取得依赖，第二次强制从TestPyPI替换Chronaxis本身，避免要求TestPyPI也保存全部依赖。两个指南路径应指向该新环境内实际存在的README。

## PyPI正式上传与回读

使用与试装一致的两个文件；确认项目地址已公开、delivery.json没有未完成的发布信息后执行：

```powershell
& $Python -m twine upload --repository pypi $Wheel $Sdist
py -3.12 -m venv .venv-pypi
$CheckPython = '.venv-pypi/Scripts/python.exe'
& $CheckPython -m pip install --no-cache-dir --index-url https://pypi.org/simple/ "chronaxis==$Version"
& $CheckPython -m pip check
$Guide = Split-Path (& $CheckPython -m chronaxis guide)
& $CheckPython "$Guide/run_analysis.py" "$Guide/examples/conditional-energy.yaml" result-release-check
```

预期生成一个61–122秒的事件，能量为`0.06777777777777777 kWh`；`result-release-check`必须是新目录。核对PyPI页面的版本、MIT、维护者邮箱、依赖、README及链接，然后发布GitHub Release草稿，记录两个平台的实际地址和时间。

## 维护依据

命令依据[PyPA打包教程](https://packaging.python.org/en/latest/tutorials/packaging-projects/)、[GitHub首次推送说明](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github)及[PyPI文件名复用规则](https://pypi.org/help/#file-name-reuse)。维护者：liuyaoze。
