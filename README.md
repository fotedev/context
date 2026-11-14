# context

Turn selected files into LLM-ready context — aggregate code, count tokens, and judge model outputs head-to-head on **LMArena**.

![License](https://img.shields.io/badge/license-MIT-green) ![Release](https://img.shields.io/badge/release-v3.6.1-blue) ![CI](https://github.com/fotedev/context/actions/workflows/ci.yml/badge.svg) ![Python](https://img.shields.io/badge/Python-%3E%3D3.9-informational)

`context` grabs the files and snippets you select, assembles them into a clean prompt bundle with a project map and accurate token counts, then keeps score: a Gemini-powered judge compares model responses in `arena.{md,txt}` and declares a winner with technical reasons.

**Four interfaces, one core:**

| Interface | Entry point | Notes |
|---|---|---|
| CLI | `aggregator.py` | The main pipeline |
| TUI | `aggregator_tui.py` | Interactive terminal UI ([textual](https://github.com/Textualize/textual)) |
| GUI | `aggregator_gui.py` | Tkinter desktop app + local server |
| Browser extension | `gui/browser-extension/` | Capture pages straight into inputs |

## Quickstart

```bash
git clone https://github.com/fotedev/context && cd context
make install                # runtime + GUI server deps
python scripts/install.py   # optional extras: tiktoken (exact counts), textual (TUI)

python aggregator.py        # CLI pipeline
python aggregator_tui.py    # interactive TUI
python aggregator_gui.py    # desktop GUI
```

Inputs live in `.context/inputs/` — whole files, line ranges (`file.py:10-20`), multi-ranges (`file.py:10-20,50-60`), or structure-only views (`!file.ts:1-15`). Outputs land in auto-numbered `context_output/NNN-<name>/` arenas; a `# Target Arena:` directive pins a folder when you need one.

## Documentation

The full usage guide — judge setup, archiving, paste attachments, arena numbering — lives in [docs/README.md](docs/README.md).

## License

[MIT](LICENSE) © Ahmed Aboalayoun
