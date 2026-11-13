# Building and maintaining the manual

<a id="手册构建与维护"></a>

This page is for documentation maintainers. Human-written guides live in `Docs/Current`; `public-api.json` lists public names, `navigation.json` defines navigation groups, and `annotations.json` contains object annotations. `documentation.json` identifies a committed product baseline. Internal builds extract APIs from that Git object; public source exports use the explicit source-tree mode below and still verify release digests.

<a id="构建依赖"></a>
## Build dependencies

Install the project's Python dependencies, Node.js, marked 17.0.5, and highlight.js 11.11.1. From the repository root, install documentation tooling with:

```powershell
npm install --prefix Docs/Current/_build/tooling marked@17.0.5 highlight.js@11.11.1
```

Installation may contact package registries; rendering and reading do not require a network connection. Existing module files can be selected through `CHRONAXIS_MARKED_PATH` and `CHRONAXIS_HIGHLIGHT_PATH`. Highlight styles come from the versioned tooling directory, so retain the matching highlight.js stylesheets.

## Reproduce dependency combinations

The source `requirements/` directory contains four complete Windows `pip freeze --all` snapshots for Python 3.12 and 3.13 lower/upper combinations. Install with the matching constraints and record the interpreter, dependency versions and actual test group result. An environment snapshot is not a passing test report. Runtime version ranges live in `pyproject.toml`; `.[test]` does not override them with a narrower jsonschema pin. Keep the existing CI environment below distinct from additional compatibility runs.

<a id="从公开源码重建"></a>
## Continuous tests and pre-release checks

`.github/workflows/verify.yml` runs on push, pull_request, or manual dispatch with Windows 2022 and Python 3.12.4. Its four groups cover core/configuration, input/execution/export, bilingual documentation with an actual HTML build, and a wheel built from sdist followed by bundled tasks outside the checkout. The workflow has read-only permissions and does not publish to PyPI or deploy the site. Both publishing workflows remain manual.

`tools/run_ci_tests.py` discovers public tests automatically. Each module belongs to exactly one group; new unclassified modules enter core. The existing nine tests requiring internal material remain excluded from public source. JSON reports list exclusions, failures, and skip reasons; a skip is not a verified result. The docs group explicitly installs Node.js 24.22.1, marked 17.0.5, and highlight.js 11.11.1. Missing tools or stale documentation locks fail instead of silently refreshing the locks.

From clean public source with `.[test]`, documentation dependencies, and matching reviewed sources/locks, run one group as follows. Replace core with input, docs, or install to select another group:

```powershell
python -X utf8 -B tools/run_ci_tests.py --group core --report work/ci/core.json
```

Beyond grouped tests, docs and install must complete the workflow's HTML, AI ZIP, sdist/wheel, and isolated installation checks. Before release, verify all four groups and installation artifacts for the same candidate source. Fix failures and record unexecuted or environment-skipped checks explicitly. Local success is not evidence of a cloud CI run, and a test report does not itself authorize publication.

## Rebuild from public source

Public source exports do not include internal development Git history. To use their release lock manifest, explicitly set this variable before building:

```powershell
$env:CHRONAXIS_DOC_SOURCE_TREE = '1'
```

The runtime source and configuration schemas must match the release manifest; missing or modified files cause errors instead of silently selecting another version. No private Git commit is needed. For a new product release, the maintainer reviews source, examples, and documentation before updating the lock. Installing the package, or rebuilding a wheel from an sdist, does not require rebuilding the entire manual.

<a id="重建与检查"></a>
## Rebuild and check

```powershell
python -B tools/english_docs.py --references-only
python -B tools/english_docs.py
python -B tools/build_m2_docs.py --edition Current
node tools/render_m2_docs.mjs --edition Current
python -B tools/verify_m2_docs.py --edition Current
python -B tools/check_current_html.py
node tools/test_manual_search.mjs
```

Open the [English HTML home](../_build/html/en/index.html). Copy the entire `_build/html` tree when moving the manual, retaining its subdirectories. It includes relative navigation, code styles, search scripts, frozen source, examples, and schemas. Reading needs no local server, Python, or Node.js; executing examples still requires Chronaxis.

<a id="维护规则"></a>
## Maintenance rules

The source AI guide references existing Current and Schema materials. Its task paths are relative to the relevant AI guide entry directory. `lookup.py` reads existing API indexes and schemas on demand without generating files. `build_ai_guide.py` converts declared repository paths to ZIP-internal paths during packaging. When changing an entry point, check source links, task/field lookup, and the standalone ZIP, not only the extracted archive.

`tools/build_ai_guide.py` generates release guidance from public manuals, schemas, and synthetic examples frozen by `Docs/AI/inputs.lock.json`. Internal implementation indexes are not the application entry point. Current HTML and wheels use the same generator; `package_current_docs.py` rejects stale ZIPs before packaging.

At the product's agreed documentation review point, refresh frozen inputs explicitly with `python -B tools/lock_ai_inputs.py <reviewed-documentation-commit> --runtime <reviewed-product-commit> --device-label <measured-label>`, then review the diff. A release wheel requires the entire runtime/template tree to match; matching version numbers or signatures alone do not establish unchanged semantics. Do not relock simply to silence a check. Check imports, original field locations, and runnable examples at feature or stage delivery.

Build wheels from a clean checkout. Run `tests/ai_release/check_bundle.py` for standalone guidance, `tools/verify_ai_distribution.py` for sdist-to-wheel, direct reading, and optional export, and `tools/check_ai_install.py` to rerun bundled cases in a fresh environment without a source checkout. Record independent-model evaluation separately from programmatic checks.

Regenerate pages after changing source docstrings or manual annotations; do not fix only generated output. Compare public constructor signatures with actual Python interfaces at the selected baseline, and read-check members, parameters, returns, and exceptions. Published HTML omits development change histories, while original source histories remain available. Keep implementation references and public entry points distinct. Historical source material stays in read-only RefProjects; the current distribution does not contain the Sclicer vendor copies.

Static coverage, links, and search tests establish their specific structural behavior. They do not replace browser appearance, keyboard/clipboard checks, complete example execution, or user reading. `_build` is reproducible output and is not committed to Git; rebuild it in a fresh checkout.

## Keep English documentation aligned

The build produces Chinese and English HTML pages, navigation, and search. English manuals live in `Docs/Current/en/`, English AI guidance in `Docs/AI/en/`, and the shared AI archive uses `en/README.md` as its English entry. Both languages share the same example inputs, configurations, results, and schemas; guide revision 3 carries both languages.

For every code change, check the affected English manual, AI instructions, and README alongside the Chinese documentation. Update explanations when public APIs, CLI options, fields/defaults, input/output behavior, time/quality semantics, dependencies, diagnostics, or examples change. Record a reason when an internal change has no user-facing effect. Do not translate machine values, alter result data, or substitute a short English summary for complete reference content.

Run `python -B tools/english_docs.py --references-only` to regenerate the English field reference. Review affected source/translation pairs, including parameter defaults, units, boundaries, example values, and links. Only after that review, run `python -B tools/english_docs.py --record-reviewed` to record the reviewed source/translation digests. Ordinary `python -B tools/english_docs.py` checks that the recorded sources have not changed. A mismatch requires reading and updating the translation; refreshing digests alone is not a review. Rebuild and check bilingual HTML and AI packaging at the agreed feature or stage delivery point.

## Directly readable guide delivery

`build_ai_guide.build_files()` assembles the same reviewed files for every channel. Wheel builds install them under `chronaxis/guide`; HTML includes them under `ai-guide`. `python -m chronaxis guide` only locates the README, with `--language en` selecting English. Editable installs read `Docs/AI` directly. ZIP is an optional separate copy, generated from the same files.

Verify installed and HTML directories, relative links, both languages, and optional ZIP content together. Run examples with inputs in the installed guide and outputs in an external working directory, then check that installed files are unchanged. Verify missing resources and overwrite protection. Existing ZIP-only checks cannot establish direct readability.

## PyPI page links

Source READMEs retain relative file links for offline reading. During metadata builds, `setup.py` uses `tools/pypi_readme.py` to derive the PyPI description from README and convert file links to pages under the GitHub version tag, using Repository and version from `pyproject.toml`. It stores no second description and does not change fenced code or the source README. Public source and sdist must contain this tool. After changing the repository or version, inspect the wheel's Project-URL fields, description links and target files. Make the remote tag publicly accessible before uploading to PyPI.
