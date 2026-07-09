// Shared types — MUST mirror the server pydantic models + response wrappers.
// Response shapes were finalised in Task 1 (gui/server/main.py) and are
// mirrored here in the same commit to prevent silent `undefined` rendering.

export interface Settings {
  output_dir: string;
  output_format: string;
  model_count: number;
  gemini_judge: boolean;
  compact_mode: boolean;
  archive: boolean;
  archive_dir: string;
  paste_attachments_enabled: boolean;
  respect_target_arena_directive: boolean;
  on_arena_number_conflict: string;
  use_default_ignore: boolean;
}

/** Wrapper for GET /api/settings — NOT a flat dict (gap 5). */
export interface SettingsResponse {
  settings: Settings;
  message: string | null;
}

export interface HealthStatus {
  version: string;
  project_root: string;
  has_gemini_key: boolean;
  pid: number;
}

export interface InputFile {
  name: string;
  path: string;
  mtime: number;
  size: number;
  source: 'inputs-dir' | 'cwd-fallback';
}

/** Wrapper for GET /api/inputs — NOT a bare list (gap 6 / edge 9). */
export interface InputsResponse {
  items: InputFile[];
  message: string | null;
}

export interface ArenaSummary {
  number: number;
  name: string;
  files: string[];
}

export interface ModelFiles {
  count: number;
  files: Record<string, string>;
  notes: Record<string, string>;
}

/** Model target — A-D for responses, 'prompt' for the shared prompt file. */
export type ModelTarget = 'A' | 'B' | 'C' | 'D' | 'prompt';

/** Run overrides include output_dir — parity with CLI --output (gap 4). */
export interface RunOverrides {
  output_dir?: string;
  output_format?: 'md' | 'txt';
  model_count?: number;
  gemini_judge?: boolean;
  compact_mode?: boolean;
  archive?: boolean;
}

export interface RunRequest {
  input: string;
  overrides?: RunOverrides;
}

/** POST /api/run response includes warnings (gap 3 — no-crash Gemini key). */
export interface RunResponse {
  run_id: string;
  arena_number: number;
  arena_path: string;
  warnings: string[];
}

/** POST /api/run/check response (gap 2 — edge 5 interactive merge/skip). */
export interface RunCheckResponse {
  conflict: boolean;
  existing_files: string[];
}

/** GET /api/ignore response (gap 1 — Req 9). */
export interface IgnorePatterns {
  patterns: string[];
  sources: {
    '.context/ignore': string[];
    '.contextignore': string[];
  };
}
