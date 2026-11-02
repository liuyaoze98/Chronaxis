# Publishing workflow

[简体中文](publishing.md)

Run these commands from the delivery directory. Confirm release information and local checks before publishing source to GitHub and packages to PyPI. TestPyPI installation testing is optional. For automatic uploads through GitHub, first complete the one-time [Trusted Publishing setup](trusted-publishing.en.md). This page also retains manual upload commands.

## Delivery layout

|Location|Purpose|
|---|---|
|`source/`|Reviewed public source; initialize a new public Git history here|
|`dist/`|Only the wheel and sdist intended for TestPyPI/PyPI|
|`manual/index.html`, `manual/en/index.html`|Chinese and English offline manuals|
|`manual/ai-guide/README.md`, `manual/ai-guide/en/README.md`|Directly readable AI guides|
|`Chronaxis-Source-0.1.0.dev1.zip`|Standalone public source archive|
|`Chronaxis-Manual-0.1.0.dev1.zip`|Complete bilingual manual and AI material for GitHub Release attachments|
|`SHA256SUMS.txt`, `delivery.json`|Artifact hashes, source/documentation revisions, verification and outstanding release information|

Publish `source/`, rather than the internal development repository's history, which contains development records and historical business data. Test logs and build staging are stored outside the delivery directory.

## Before uploading

- The repository is [liuyaoze98/Chronaxis](https://github.com/liuyaoze98/Chronaxis). Package metadata includes repository, documentation, issue and changelog links. Builds derive the PyPI description from README and convert relative file links to pages under the `v0.1.0.dev1` tag; the source README remains readable locally.
- Confirm that your PyPI account can publish `chronaxis` and version `0.1.0.dev1`. An HTTP 404 does not prove that the name is available for registration.
- Make the repository accessible before the PyPI release. MIT, author liuyaoze, and work@liuyaoze.com are confirmed.
- Read the [version policy](versioning.md), [third-party notices](third-party.md), and [known dependency limitation](security.md). Uploaded filenames cannot be replaced; changed artifacts need a new version.

```powershell
$Version = '0.1.0.dev1'
$Wheel = "dist/chronaxis-$Version-py3-none-any.whl"
$Sdist = "dist/chronaxis-$Version.tar.gz"
py -3.12 -m venv .venv-publish
$Python = '.venv-publish/Scripts/python.exe'
& $Python -m pip install --upgrade twine
& $Python -m twine check $Wheel $Sdist
Get-FileHash -Algorithm SHA256 $Wheel, $Sdist
```

Both packages must pass and match SHA256SUMS.txt. Upload these two explicit files, not the documentation or source ZIP.

## GitHub source and release assets

Create an empty GitHub repository without generated README or license files. If the target already contains commits, review them before proceeding; these first-release commands do not merge an existing history.

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

Create a draft GitHub Release from this tag, titled `Chronaxis 0.1.0.dev1`, and mark it as a prerelease. Use the [release notes](release-notes-0.1.0.dev1.md). Attach the source ZIP, bilingual manual ZIP, wheel, sdist, and SHA256SUMS.txt. After verifying all five attachment hashes, publish the prerelease so the Pages workflow can read the manual with read-only repository permissions. Update its publication status after verifying PyPI.

After pushing, open the repository, `v0.1.0.dev1` tag and metadata documentation link in a signed-out browser before uploading to PyPI. A known URL does not establish public access. Local build checks verify that target files exist; they do not replace this remote check.

Publish the HTML manual at https://liuyaoze98.github.io/Chronaxis/ with English at https://liuyaoze98.github.io/Chronaxis/en/. Select GitHub Actions in the repository Pages settings, then run pages.yml to download the reviewed manual attachment, verify its SHA256, and deploy it. Before uploading a new PyPI version, check the online pages, language switch, search, and AI guide; a successful HTTP status alone is insufficient.

## TestPyPI upload and installation

TestPyPI and PyPI use separate accounts and tokens. Enter the appropriate token at Twine's interactive prompt; keep tokens out of project files.

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

The local wheel installation obtains dependencies from the normal index. The second command replaces Chronaxis itself from TestPyPI, which need not host all dependencies. Both guide paths must point to existing README files in this new environment.

## PyPI upload and verification

Use the same two verified files after making the repository public and resolving all missing release information in delivery.json:

```powershell
& $Python -m twine upload --repository pypi $Wheel $Sdist
py -3.12 -m venv .venv-pypi
$CheckPython = '.venv-pypi/Scripts/python.exe'
& $CheckPython -m pip install --no-cache-dir --index-url https://pypi.org/simple/ "chronaxis==$Version"
& $CheckPython -m pip check
$Guide = Split-Path (& $CheckPython -m chronaxis guide)
& $CheckPython "$Guide/run_analysis.py" "$Guide/examples/conditional-energy.yaml" result-release-check
```

Expect one event from 61 to 122 seconds and `0.06777777777777777 kWh`. The result directory must be new. Check the PyPI version, MIT license, maintainer email, dependencies, README and links, then update the publication status in the GitHub Release and record both URLs and times.

## References

Commands follow the [PyPA packaging tutorial](https://packaging.python.org/en/latest/tutorials/packaging-projects/), [GitHub import instructions](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github), and [PyPI filename policy](https://pypi.org/help/#file-name-reuse). Maintainer: liuyaoze.
