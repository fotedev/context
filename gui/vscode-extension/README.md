# Context Tool — VS Code extension (boilerplate)

A companion extension for the **Context aggregator** tool that ships in this
repository. It provides editor-side shortcuts for the same local FastAPI
server used by the browser extension (`gui/server/main.py`), so you can
start the server, pair, and kick off an aggregation run without leaving
VS Code.

> **Status: boilerplate.** The commands, settings, and HTTP client are
> wired up, but the actual server-spawn logic in `src/serverManager.ts`
> is a stub. A follow-up change will replace the placeholder `PAIRING_CODE`
> regex with real subprocess plumbing once the upstream server learns to
> print the code to stdout.

## Commands

| Command | Title | Purpose |
| --- | --- | --- |
| `contextTool.startServer` | Context Tool: Start Local Server | Spawn `python -m gui.server` and capture the pairing code. |
| `contextTool.stopServer` | Context Tool: Stop Local Server | Tear down the server subprocess. |
| `contextTool.pair` | Context Tool: Pair With Server | Exchange a pairing code for a bearer token. |
| `contextTool.runAggregation` | Context Tool: Run Aggregation | POST `/api/run` with the active editor's `.txt` file. |
| `contextTool.openSettings` | Context Tool: Open Settings | Open `.context/settings.json` if it exists. |

## Settings

| Setting | Default | Notes |
| --- | --- | --- |
| `contextTool.server.host` | `127.0.0.1` | Loopback only — the server refuses non-loopback clients. |
| `contextTool.server.port` | `8765` | Must match `host_permissions` in `gui/browser-extension/manifest.json`. |
| `contextTool.server.autoStart` | `false` | When true, the extension spawns the server on activation if `files.txt` is in the workspace. |
| `contextTool.pythonPath` | `python` | Override if you keep the tool's dependencies in a virtualenv. |

## Token storage

The bearer token is held in VS Code's `SecretStorage`, never in
`globalState` or on disk. Clearing it via the command palette (`Developer:
Clear Extension Storage`) is the only way to forget it short of
uninstalling the extension.

## Build / package

```bash
npm install
npm run build      # compiles src/ → out/
npm run package    # produces a .vsix via @vscode/vsce
```

Then in VS Code: `Extensions → … → Install from VSIX…`.

## Tests

This boilerplate ships without a test runner to keep the stub minimal. A
follow-up should add `mocha` + `@vscode/test-cli` and cover the request
shapes in `src/apiClient.ts`.