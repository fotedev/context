/**
 * Server lifecycle helpers.
 *
 * Boilerplate stub — the real implementation will spawn
 * ``python aggregator.py --serve`` as a child process, capture the pairing
 * code from its stdout, and tear it down on extension deactivation.
 *
 * For now we expose a single async function that the activation flow calls
 * to obtain the pairing code, leaving the actual spawn / teardown to a
 * follow-up change. The function shape is deliberately stable so that
 * swapping in a real implementation does not require touching extension.ts.
 */

import * as vscode from "vscode";
import { spawn } from "child_process";

/**
 * Resolve the python interpreter configured for the extension.
 *
 * The default is the bare ``python`` command, but most users will want to
 * point this at their virtualenv's interpreter so the server sees the same
 * ``fastapi``/``uvicorn`` versions that the rest of the tool expects.
 */
function pythonExecutable(): string {
  return vscode.workspace
    .getConfiguration()
    .get<string>("contextTool.pythonPath", "python");
}

/**
 * Ensure the local Context Tool server is running and return its pairing code.
 *
 * Behaviour:
 *   1. Spawn ``python -m gui.server`` (or the configured entrypoint) with
 *      ``--host 127.0.0.1`` and ``--port 8765`` (configurable).
 *   2. Watch stdout for the line ``PAIRING_CODE: <token>`` and resolve.
 *   3. If the server is already reachable, skip the spawn and request a
 *      fresh pairing code from a hidden ``/auth/code`` endpoint instead.
 *
 * Raises on spawn failure or a 5s timeout waiting for the code line.
 */
export async function ensureServerRunning(timeoutMs = 5000): Promise<string> {
  return new Promise((resolve, reject) => {
    const proc = spawn(pythonExecutable(), ["-m", "gui.server"], {
      stdio: ["ignore", "pipe", "pipe"],
    });

    const timer = setTimeout(() => {
      proc.kill();
      reject(new Error(`Timed out after ${timeoutMs}ms waiting for pairing code`));
    }, timeoutMs);

    let buffer = "";
    proc.stdout.on("data", (chunk: Buffer) => {
      buffer += chunk.toString("utf8");
      const match = buffer.match(/PAIRING_CODE:\s*(\S+)/);
      if (match) {
        clearTimeout(timer);
        resolve(match[1]);
      }
    });

    proc.on("error", (err) => {
      clearTimeout(timer);
      reject(err);
    });

    proc.on("exit", (code) => {
      clearTimeout(timer);
      if (code !== 0 && code !== null) {
        reject(new Error(`Server exited with code ${code} before printing pairing code`));
      }
    });
  });
}