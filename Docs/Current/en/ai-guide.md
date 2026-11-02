# AI guide

<a id="把当前版本交给-ai-使用"></a>

When asking an assistant to generate a configuration or Python code, start with the AI guide's README, then look up the relevant task, fields, and public API. Choose the entry that matches the files you already have:

| What you have | How to open the guide |
|---|---|
| Project source | Open `Docs/AI/en/README.md` directly, or `Docs/AI/README.md` for Chinese. Keep the repository layout intact to follow links and run queries. No guide download, build, or export is needed. |
| Offline HTML manual | Open the included [English guide](../_build/html/ai-guide/en/README.md) or [Chinese guide](../_build/html/ai-guide/README.md) directly. The files are already available as a directory. |
| Only an installed Chronaxis package | Use the command below to locate the README, then open it in an editor or give its path to the assistant. |

```powershell
python -m chronaxis guide --language en
python -m chronaxis guide
```

These commands only print paths; they do not generate or extract files. The installed `chronaxis/guide` directory already contains the instructions, field references, and examples. Write example results to your own working directory.

To save a separate offline copy, optionally use `python -m chronaxis guide --output my-guide.zip`. The target must be new and always contains both languages. This step is unnecessary for reading.

Reading the guide does not require Chronaxis to be installed; the lookup script uses only Python's standard library. Running analysis examples requires Chronaxis and its dependencies. Select a matching example from the task index, check its inputs, time units, and expected result, then adapt it to your files. Resolve missing information that would affect the result before running the analysis.
