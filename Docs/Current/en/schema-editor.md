# Editor field hints

<a id="编辑器字段提示"></a>

JSON Schema describes fields for editors and validators. The schema files are JSON, but describe the same configuration structure after either YAML or JSON has been parsed. They provide names, types, required fields, and allowed values. Chronaxis's own validation still determines whether references, units, synchronization, and execution capabilities are valid.

<a id="选择对应规范"></a>
## Choose the matching schema

| Configuration | Downloadable local schema |
|---|---|
| Analysis, `config_version: 3` | [analysis.schema.json](../../Schema/analysis.schema.json) |
| Batch, `batch_version: 1` | [batch-v1.schema.json](../../Schema/batch-v1.schema.json) |
| Shared `sources` / `signals` / `derived` definitions | [definitions.schema.json](../../Schema/definitions.schema.json) |
| INI mapping, `mapping_version: 1` | [legacy-import-v1.schema.json](../../Schema/legacy-import-v1.schema.json) |

Keep all four files in the same directory with their original names so their relative references work. The offline HTML package also includes them; it does not depend on paths on the author's computer.

<a id="yaml编辑器关联"></a>
## Associate a YAML file with a schema

Editors supporting YAML Language Server configuration recognize the comment below. Assume a `schemas` directory beside `plan.yaml` contains the files above.

Add the first comment line to the start of your existing complete configuration. Keep its `dataset`, `sources`, `signals`, and other content; these two lines do not replace the entire analysis file.

```yaml
# yaml-language-server: $schema=schemas/analysis.schema.json
config_version: 3    # Analysis configuration structure version; use integer 3.
```

The comment's path is relative to `plan.yaml`; adjust it if you move the file. For JSON, select the schema through your editor's file-association settings. Do not add `$schema` as a business configuration field: Chronaxis rejects unknown fields.

<a id="命令行检查"></a>
## Validate from the command line

Editor hints do not replace the loader. Check your complete configuration with:

```powershell
chronaxis validate plan.yaml
chronaxis explain plan.yaml
```

The configuration parser checks duplicate keys, anchors, aliases, tags, multiple documents, and non-finite numbers. Plan validation checks validity periods, units, and dependencies. Passing these checks does not establish that your input data or business thresholds are correct.
