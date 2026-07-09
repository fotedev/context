/**
 * HTTP client for the Context Tool FastAPI server.
 *
 * Mirrors the wire contract documented in
 * ``gui/browser-extension/src/shared/api.ts`` so the browser extension and
 * this VS Code extension can be swapped transparently:
 *
 *   GET  /health           → loopback liveness check
 *   POST /auth/pair        → exchange pairing code for bearer token
 *   GET  /api/settings     → flat settings dict (wrapper shape)
 *   PUT  /api/settings     → partial update
 *   GET  /api/inputs       → list input files (wrapper shape)
 *   POST /api/run          → kick off an aggregation run
 *
 * The bearer token is stored in VS Code's SecretStorage (not in
 * ``globalState``) so it survives extension restarts but never lands on
 * disk in plaintext.
 */

import type { SecretStorage } from "vscode";

const TOKEN_KEY = "contextTool.bearerToken";

export interface RunResponse {
  run_id: string;
  arena_number: number;
  arena_path: string;
  warnings: string[];
}

export interface SettingsResponse {
  settings: Record<string, unknown>;
  message: string | null;
}

export interface InputsResponse {
  items: Array<{
    name: string;
    path: string;
    mtime: number;
    size: number;
    source: string;
  }>;
  message: string | null;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly statusCode?: number,
    public readonly body?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export class ApiClient {
  private tokenCache: string | null = null;

  constructor(
    private readonly host: string,
    private readonly port: number,
    private readonly secrets: SecretStorage,
  ) {}

  /** Base URL with a trailing slash stripped — `URL` resolves it consistently. */
  get baseUrl(): string {
    return `http://${this.host}:${this.port}`;
  }

  /** Liveness probe used by status checks. */
  async health(): Promise<Record<string, unknown>> {
    return this.request("GET", "/health");
  }

  /** Exchange a freshly-printed pairing code for a long-lived bearer token. */
  async pair(code: string): Promise<string> {
    const body = (await this.request("POST", "/auth/pair", { code })) as { token: string };
    return body.token;
  }

  /** Persist the bearer token in SecretStorage so it survives restarts. */
  async persistToken(token: string): Promise<void> {
    this.tokenCache = token;
    await this.secrets.store(TOKEN_KEY, token);
  }

  /** Read the bearer token from SecretStorage (lazy, cached in-memory). */
  async getToken(): Promise<string | null> {
    if (this.tokenCache) return this.tokenCache;
    const stored = await this.secrets.get(TOKEN_KEY);
    this.tokenCache = stored ?? null;
    return this.tokenCache;
  }

  /** Kick off an aggregation run; matches the browser-extension contract. */
  async run(input: string): Promise<RunResponse> {
    return (await this.request("POST", "/api/run", { input })) as RunResponse;
  }

  /** Read current settings (wrapper shape). */
  async getSettings(): Promise<SettingsResponse> {
    return (await this.request("GET", "/api/settings")) as SettingsResponse;
  }

  /** Update settings (partial). */
  async updateSettings(patch: Record<string, unknown>): Promise<SettingsResponse> {
    return (await this.request(
      "PUT",
      "/api/settings",
      patch,
    )) as SettingsResponse;
  }

  /** List input files (wrapper shape). */
  async listInputs(): Promise<InputsResponse> {
    return (await this.request("GET", "/api/inputs")) as InputsResponse;
  }

  // -------------------------------------------------------------------------
  // Internal: thin fetch wrapper with bearer-token injection + error mapping.
  // -------------------------------------------------------------------------

  private async request(
    method: string,
    path: string,
    body?: unknown,
  ): Promise<unknown> {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    // /health and /auth/pair are public; everything else needs the bearer.
    if (path !== "/health" && path !== "/auth/pair") {
      const token = await this.getToken();
      if (token) headers.Authorization = `Bearer ${token}`;
    }

    const init: RequestInit = { method, headers };
    if (body !== undefined) init.body = JSON.stringify(body);

    let response: Response;
    try {
      response = await fetch(`${this.baseUrl}${path}`, init);
    } catch (err) {
      throw new ApiError(
        `Network error contacting ${this.baseUrl}${path}: ${(err as Error).message}`,
      );
    }

    let parsed: unknown = null;
    const text = await response.text();
    if (text.length > 0) {
      try {
        parsed = JSON.parse(text);
      } catch {
        parsed = text;
      }
    }

    if (!response.ok) {
      const detail =
        parsed && typeof parsed === "object" && "detail" in parsed
          ? String((parsed as { detail: unknown }).detail)
          : response.statusText;
      throw new ApiError(`HTTP ${response.status}: ${detail}`, response.status, parsed);
    }
    return parsed;
  }
}