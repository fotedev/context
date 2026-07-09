/**
 * Context Tool — VS Code extension entry point.
 *
 * Responsibilities (kept intentionally thin — this is a *boilerplate* stub):
 *
 *  1. Register all five `contextTool.*` commands declared in `package.json`.
 *  2. Wire commands to the local FastAPI server (``gui/server/main.py``)
 *     using the shared HTTP client in :mod:`apiClient`.
 *  3. Optionally auto-start the server when the workspace contains
 *     ``files.txt`` (mirrors the browser-extension activation flow).
 *
 * The extension does NOT bundle any aggregation logic — all real work
 * happens in the Python server, just like the browser extension. Pairing,
 * bearer-token storage, and run-conflict detection are delegated to the
 * same endpoints used by the browser extension (see
 * ``gui/browser-extension/src/shared/api.ts`` for the wire contract).
 */

import * as vscode from "vscode";
import { ApiClient, ApiError } from "./apiClient";
import { ensureServerRunning } from "./serverManager";

/**
 * Reads a configuration value with a documented default fallback.
 *
 * VS Code's `getConfiguration(...).get(...)` typing accepts `undefined` for
 * any property whose `default` is missing — we always supply one in
 * `package.json`, but the fallback makes this resilient to a user deleting
 * the setting entirely.
 */
function cfg<T>(key: string, fallback: T): T {
  const value = vscode.workspace.getConfiguration().get<T>(key);
  return value === undefined ? fallback : value;
}

export function activate(context: vscode.ExtensionContext): void {
  const host = cfg<string>("contextTool.server.host", "127.0.0.1");
  const port = cfg<number>("contextTool.server.port", 8765);
  const api = new ApiClient(host, port, context.secrets);

  // -------------------------------------------------------------------------
  // Command: contextTool.startServer
  // -------------------------------------------------------------------------
  context.subscriptions.push(
    vscode.commands.registerCommand("contextTool.startServer", async () => {
      try {
        const pairingCode = await ensureServerRunning();
        vscode.window.showInformationMessage(
          `Context Tool server running on http://${host}:${port}. ` +
            `Pairing code: ${pairingCode}`,
        );
      } catch (err) {
        vscode.window.showErrorMessage(
          `Could not start server: ${(err as Error).message}`,
        );
      }
    }),
  );

  // -------------------------------------------------------------------------
  // Command: contextTool.stopServer
  // -------------------------------------------------------------------------
  context.subscriptions.push(
    vscode.commands.registerCommand("contextTool.stopServer", async () => {
      // Boilerplate: actual shutdown wiring lives in serverManager.ts so it
      // can be unit-tested without a real VS Code host. The stop call is
      // best-effort; the process may already have exited.
      vscode.window.showInformationMessage("Context Tool: stop requested.");
    }),
  );

  // -------------------------------------------------------------------------
  // Command: contextTool.pair — exchange a pairing code for a bearer token.
  // -------------------------------------------------------------------------
  context.subscriptions.push(
    vscode.commands.registerCommand("contextTool.pair", async () => {
      const code = await vscode.window.showInputBox({
        prompt: "Paste the pairing code printed by `aggregator.py --serve`",
        placeHolder: "Pairing code",
        ignoreFocusOut: true,
      });
      if (!code) return;
      try {
        const token = await api.pair(code.trim());
        await api.persistToken(token);
        vscode.window.showInformationMessage("Context Tool: paired.");
      } catch (err) {
        const message = err instanceof ApiError ? err.message : (err as Error).message;
        vscode.window.showErrorMessage(`Pairing failed: ${message}`);
      }
    }),
  );

  // -------------------------------------------------------------------------
  // Command: contextTool.runAggregation — POST /api/run with the active file.
  // -------------------------------------------------------------------------
  context.subscriptions.push(
    vscode.commands.registerCommand(
      "contextTool.runAggregation",
      async (uri: vscode.Uri | undefined) => {
        const inputName = uri ? uri.fsPath.split(/[\\/]/).pop()?.replace(/\.txt$/, "") : "files";
        if (!inputName) {
          vscode.window.showErrorMessage("Context Tool: cannot derive input name.");
          return;
        }
        try {
          const result = await api.run(inputName);
          vscode.window.showInformationMessage(
            `Run #${result.arena_number} complete — see ${result.arena_path}`,
          );
        } catch (err) {
          vscode.window.showErrorMessage(
            `Run failed: ${(err as Error).message}`,
          );
        }
      },
    ),
  );

  // -------------------------------------------------------------------------
  // Command: contextTool.openSettings — open the .context/settings.json file.
  // -------------------------------------------------------------------------
  context.subscriptions.push(
    vscode.commands.registerCommand("contextTool.openSettings", async () => {
      const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
      if (!workspaceFolder) {
        vscode.window.showWarningMessage("Open a folder first.");
        return;
      }
      const settingsUri = vscode.Uri.joinPath(
        workspaceFolder.uri,
        ".context",
        "settings.json",
      );
      try {
        await vscode.workspace.fs.stat(settingsUri);
        await vscode.window.showTextDocument(await vscode.workspace.openTextDocument(settingsUri));
      } catch {
        vscode.window.showInformationMessage(
          "No .context/settings.json yet — run the server once to bootstrap it.",
        );
      }
    }),
  );

  // -------------------------------------------------------------------------
  // Auto-start: only when explicitly enabled AND files.txt is in the workspace.
  // -------------------------------------------------------------------------
  const autoStart = cfg<boolean>("contextTool.server.autoStart", false);
  if (autoStart) {
    vscode.workspace.findFiles("**/files.txt", "**/node_modules/**", 1).then(async (hits) => {
      if (hits.length === 0) return;
      try {
        await ensureServerRunning();
      } catch (err) {
        vscode.window.showWarningMessage(
          `Context Tool auto-start skipped: ${(err as Error).message}`,
        );
      }
    });
  }
}

export function deactivate(): void {
  // Boilerplate — server lifecycle is owned by the Python subprocess; if we
  // ever spawn it from here, kill it here.
}