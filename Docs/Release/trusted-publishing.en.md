# Publish to PyPI through GitHub

[简体中文](trusted-publishing.md)

This workflow uploads the release files already built, installed, verified, and attached to the GitHub Release. GitHub obtains short-lived publishing credentials from PyPI; no password or API token needs to be stored in the repository.

## First-time setup

Sign in to [PyPI publishing settings](https://pypi.org/manage/account/publishing/). Under “Add a new pending publisher”, choose GitHub and enter:

|Field|Value|
|---|---|
|PyPI Project Name|`chronaxis`|
|Owner|`liuyaoze98`|
|Repository name|`Chronaxis`|
|Workflow name|`pypi-publish.yml`|
|Environment name|`pypi`|

Enter only the workflow filename, without `.github/workflows/`. The environment name matches the GitHub workflow environment, not a Python virtual environment. Click Add. The account must meet PyPI's email verification and two-factor authentication requirements. A pending publisher does not reserve the project name. If the chronaxis project already exists under your account, add the same configuration on its Publishing page instead.

## Verify and upload

Open [GitHub Actions](https://github.com/liuyaoze98/Chronaxis/actions/workflows/pypi-publish.yml), select Run workflow, and choose main.

1. Run without selecting the upload option: download the two release files and check the source tag and SHA256 values. Nothing is uploaded to PyPI.
2. After verification succeeds and the PyPI setup is complete, run with the upload option selected. Check the [PyPI project page](https://pypi.org/project/chronaxis/0.1.0.dev0/) after success.
3. Follow the [publishing workflow](publishing.en.md) to install from PyPI in a new environment, verify dependencies, guides, and the energy example, then publish the GitHub Release draft.

The current workflow is pinned to version 0.1.0.dev0 and its reviewed hashes. It does not rebuild files or move the source tag. Before releasing another version, verify its packages, then update the workflow version, source commit, and both file hashes. Do not enable skip-existing to bypass an upload failure; first compare the remote files with the local files.

TestPyPI is an optional, separate upload testing service. Without a TestPyPI account, verify installation locally first, then verify installation from the production PyPI service.

Reference: [Creating a PyPI project with a Trusted Publisher](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/). Maintainer: liuyaoze.
