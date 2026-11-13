# Publishing workflow

[简体中文](publishing.md)

This page records the workflow used to publish `0.1.0.dev1` on 2026-11-02 and makes it reusable for the next release. That version is already published. Choose a new version using the [version policy](versioning.md); preserve existing files and tags.

The order is: **local build and verification → public source and release assets → HTML deployment → PyPI verification-only run → PyPI upload → fresh installation checks → record the outcome**. This release used GitHub Trusted Publishing. It did not use TestPyPI or a local Twine upload.

## One-time setup

|Item|Established setting|
|---|---|
|Public source|[liuyaoze98/Chronaxis](https://github.com/liuyaoze98/Chronaxis)|
|PyPI|Project `chronaxis`; authorize GitHub through [Trusted Publishing](trusted-publishing.en.md)|
|Publisher identity|Owner=`liuyaoze98`, Repository=`Chronaxis`, Workflow=`pypi-publish.yml`, Environment=`pypi`|
|GitHub Pages|Repository Settings → Pages → Source: GitHub Actions|
|HTML URLs|[Chinese](https://liuyaoze98.github.io/Chronaxis/) and [English](https://liuyaoze98.github.io/Chronaxis/en/)|
|Maintainer and license|`liuyaoze <work@liuyaoze.com>`, MIT|

PyPI accepts short-lived GitHub identity credentials; no password or token needs to be shared with an AI. The existing publisher supports later releases. Recheck the binding if the repository, workflow filename, or environment changes. Both workflows are manually triggered; pushing source does not automatically deploy the site or publish packages.

Before the next release, also verify the candidate public source with all four `verify.yml` test groups and isolated installation checks; see [continuous testing](../Current/en/maintenance.md#continuous-tests-and-pre-release-checks). This verification workflow does not change the manual publishing entry points. Historical dev1/dev3 reports cannot replace checks of the new candidate.

## 1. Build and verify locally

Use `project.version` in `pyproject.toml` as the sole release-version source. Change it and synchronize both READMEs, installation examples, AI guides and release notes. The builder writes the installed version automatically; the default `RunMetadata.software_version` reads the current software version rather than maintaining another constant, while explicit historical values remain unchanged. Verify the runtime version, package metadata and AI manifest together. `Documentation` points to the online HTML manual and `Changelog` to the release-history entry. The build converts relative README links to URLs under the public version tag.

Verify and commit in the internal repository, then export a specific commit. The following tools formed the actual build chain. Any revision passed to a tool must have been reviewed.

|Tool or check|Purpose and acceptance condition|
|---|---|
|`tools/build_m2_docs.py --edition Current`|Generate references from the source revision in `Docs/Current/documentation.json`; public signatures must match the actual interfaces|
|`tools/english_docs.py --record-reviewed`|Review affected translations before recording source hashes; refreshing hashes alone does not resolve a failed check|
|`tools/lock_ai_inputs.py <manual-commit> --runtime <runtime-commit> --device-label <home-or-work>`|Lock the matching guide inputs after committing the corresponding material|
|`tools/export_public_source.py <new-directory> --revision <commit>`|Export the public allowlist and `PUBLIC-SOURCE.json`, excluding internal Git history, management records, real data, and uncommitted files|
|`tools/verify_ai_distribution.py <new-build-directory> --public-source <public-export>`|Build an sdist from clean source without Git, build its wheel, and compare the installed guide with the optional ZIP|
|`node tools/render_current_docs.mjs`|Generate bilingual HTML and directly readable AI material|
|`tools/check_current_html.py`, `node tools/test_manual_search.mjs`, `tools/package_current_docs.py`|Check pages, assets, search, copyable code, and the packaged manual after relocation|
|`tools/check_ai_install.py <wheel> <AI-ZIP> <prepared-dependencies-directory> <report-path> --device-label <home-or-work>`|Check guides, public signatures, and bundled tasks in isolation|
|`python -m twine check <wheel> <sdist>`|Validate package formatting and the README without uploading|

Run the Python tools with `python -B`. See [documentation maintenance](../Current/en/maintenance.md) for build dependencies and documentation tooling. Rebuild affected material after source changes and compare the AI guides in HTML and the wheel at delivery. Investigate failures instead of changing hashes or skipping assertions to claim success.

Prepare five GitHub Release assets and record SHA256 values: wheel, sdist, `Chronaxis-Source-<version>.zip`, `Chronaxis-Manual-<version>.zip`, and `SHA256SUMS.txt`. The checksum file lists the other four assets; verify all five assets themselves after upload. Keep `delivery.json` and verification logs in the local delivery workspace. Filenames must match the workflows. Only wheel and sdist are uploaded to PyPI.

## 2. GitHub source and release assets

The internal and public repositories have separate histories. Initialize the public repository only for its first release. Later releases reuse the public checkout: inspect its working tree, fetch and fast-forward `main`, then synchronize the reviewed public export. Review the exact changes before committing and pushing. Do not push the internal repository's complete history to the public remote.

Use these commands after synchronizing the public source. `$PublicRepo` must be the public checkout, not the internal repository; `$Version` must be an unpublished new version.

```powershell
$PublicRepo = Read-Host 'Public repository checkout path'
$Version = Read-Host 'New release version'
git -C $PublicRepo status --short
git -C $PublicRepo push origin main
git -C $PublicRepo tag -a "v$Version" -m "Chronaxis $Version"
git -C $PublicRepo push origin "v$Version"
```

The current PyPI workflow resolves an **annotated tag**, so use `git tag -a`. The tag identifies the verified public source commit. Compare the public files with `PUBLIC-SOURCE.json`; an internal commit SHA is not the public commit SHA.

Create a draft GitHub Release for that tag and upload the five assets. Verify their names, sizes, and SHA256 values. Mark development previews as prereleases. Once the assets are verified, publish the prerelease with an accurate note that PyPI upload is pending. Public assets are required for the subsequent workflows' read-only repository access.

## 3. Update the release workflows

The workflows do not infer new versions or rebuild files. **Changing the local `$Version` variable is insufficient.** Check the following settings for every release and commit them to public `main`.

|File|Update for each release|Current permissions|
|---|---|---|
|`.github/workflows/pages.yml`|Release tag, manual ZIP filename, and SHA256|`contents: read`, `pages: write`, `id-token: write`|
|`.github/workflows/pypi-publish.yml`|Version description, Release tag, public source SHA resolved by that tag, wheel/sdist filenames, and both SHA256 values|`contents: read`, `id-token: write`|

Both workflows are restricted to this repository and `main`, with official Actions pinned to commits. After freezing the source tag, make a separate workflow commit on `main` if necessary; do not move the tag to fill in its source SHA. This is the sequence used for `dev1`. Read the current workflow files to determine their pinned versions and hashes; do not infer them from this historical record. Keep existing workflows while a candidate still lacks its final public-source commit or asset hashes. Update and verify those values together before an authorized publication, without placeholder hashes or premature dispatch.

## 4. Deploy HTML

```powershell
gh workflow run pages.yml --repo liuyaoze98/Chronaxis --ref main
```

Wait for this run to succeed in Actions. It downloads the public manual asset, checks SHA256, extracts it, and deploys it. It does not regenerate documentation in the cloud.

Check the public Chinese and English homepages, language-switch targets, styles, scripts, search data, a real tutorial, and AI guides. Compare the response content with the verified manual and confirm that pages are HTML. HTTP 200 alone may represent an error page or access challenge. The online site serves the current release; earlier manuals remain available from their corresponding Release assets.

## PyPI upload and verification

First run without uploading:

```powershell
gh workflow run pypi-publish.yml --repo liuyaoze98/Chronaxis --ref main -f upload=false
```

Confirm that **this run** succeeded: the source tag resolves correctly, both asset hashes match, and the upload step was skipped. Only then run the upload:

```powershell
gh workflow run pypi-publish.yml --repo liuyaoze98/Chronaxis --ref main -f upload=true
```

Publishing uses PyPI Trusted Publishing and retains publication signing. After success, inspect `https://pypi.org/pypi/chronaxis/<version>/json`: both filenames and SHA256 values, version, Python and dependency requirements, MIT, maintainer email, README, and project links. Also check that the default project version's `Documentation` points to HTML.

Create a fresh environment from the production PyPI index and run the bundled example:

```powershell
py -3.12 -m venv .venv-pypi
$CheckPython = '.venv-pypi/Scripts/python.exe'
& $CheckPython -m pip install --no-cache-dir --index-url https://pypi.org/simple/ "chronaxis==$Version"
& $CheckPython -m pip check
& $CheckPython -m chronaxis guide --language en
$Guide = Split-Path (& $CheckPython -m chronaxis guide)
& $CheckPython "$Guide/run_analysis.py" "$Guide/examples/conditional-energy.yaml" result-release-check
```

Use new directories for the environment and `result-release-check`. Expect one event from 61 to 122 seconds, `0.06777777777777777 kWh`, and status `完整` (complete). Both guide languages must be directly locatable, and running the example must leave guide files unchanged. Windows/Python 3.12 was the environment actually verified; this does not establish support for additional platforms.

Finally update the GitHub Release text to remove temporary wording such as “PyPI upload pending”. Record URLs, source/tag identities, hashes, workflow runs, and installation results, then update internal plans, issues, and handover memory. A successful workflow alone does not establish a successful installation.

## Problems encountered and their handling

|Symptom|Actual handling and next-release guidance|
|---|---|
|The dev0 PyPI Documentation link opened GitHub Markdown|Deploy HTML and release dev1 with corrected metadata. Editing the repository README does not replace metadata already uploaded for a version|
|Reading a draft asset returned `release not found`|Drafts are not visible to read-only workflow identities. Verify and publish assets before Pages/PyPI. The maintainer queried the release ID to inspect the draft|
|Automatic approval rejected Pages `contents:write`|Use public assets and `contents:read`, retaining only the Pages/OIDC permissions needed for deployment|
|Git HTTPS transfers reset|Use GitHub's Git Data API for the same reviewed content, fast-forwarding only the checked parent. Then fetch and fast-forward the local public mirror. No force push or history rewrite was used|
|Sigstore/Rekor returned HTTP 502|Check the failure stage and PyPI files first. This release retried the original workflow after confirming that dev1 had no files. If partial files already exist, inspect hashes and status before proceeding; do not blindly retry, enable `skip-existing`, or disable signing|
|The system temporary directory was not writable|Set `TEMP`/`TMP` to the dedicated task workspace and repeat the affected verification|
|An old manual validator required Chinese history text in English pages|Use applicable bilingual source, HTML, and guide checks while retaining the failure record; do not call an inapplicable assertion a repaired product defect|
|PyPI HTML returned `Client Challenge`|Verify metadata through the official JSON API and independently verify the target HTML; record that browser interaction was not tested|

Historical `dev1` evidence: [successful second Pages attempt](https://github.com/liuyaoze98/Chronaxis/actions/runs/41463321957), [PyPI verification-only run](https://github.com/liuyaoze98/Chronaxis/actions/runs/41464499414), [successful second PyPI attempt](https://github.com/liuyaoze98/Chronaxis/actions/runs/41464970458), and [GitHub prerelease](https://github.com/liuyaoze98/Chronaxis/releases/tag/v0.1.0.dev1). These records do not establish that a later version has passed the same checks.

Maintainer: liuyaoze. See [distribution scope](distribution.md) and [dependency security notes](security.md).
