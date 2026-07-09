// Typed fetch wrapper for the context tool server.
// Bearer token is injected from chrome.storage.local on every request.
// BASE_URL is overridable for Codespaces/GitPod forwarded ports.

import {
  Settings,
  SettingsResponse,
  HealthStatus,
  InputsResponse,
  ArenaSummary,
  ModelFiles,
  ModelTarget,
  RunRequest,
  RunResponse,
  RunCheckResponse,
  IgnorePatterns,
} from './types';

const BASE_URL = 'http://127.0.0.1:8765';

async function getToken(): Promise<string | null> {
  return new Promise((resolve) => {
    chrome.storage.local.get(['auth_token'], (result) => {
      resolve(result.auth_token || null);
    });
  });
}

async function setToken(token: string): Promise<void> {
  return new Promise((resolve) => {
    chrome.storage.local.set({ auth_token: token }, () => resolve());
  });
}

async function fetchAPI<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = await getToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(`${BASE_URL}${path}`, { ...options, headers });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || 'API request failed');
  }

  if (response.status === 204) return null as T;
  return response.json() as Promise<T>;
}

export const api = {
  getHealth: () => fetchAPI<HealthStatus>('/health'),

  pair: (code: string) =>
    fetchAPI<{ token: string }>('/auth/pair', {
      method: 'POST',
      body: JSON.stringify({ code }),
    }).then((res) => {
      setToken(res.token);
      return res;
    }),

  getInputs: () => fetchAPI<InputsResponse>('/api/inputs'),
  createInput: (name: string, content: string) =>
    fetchAPI<{ path: string }>('/api/inputs', {
      method: 'POST',
      body: JSON.stringify({ name, content }),
    }),
  deleteInput: (name: string) =>
    fetchAPI<{ ok: boolean }>(`/api/inputs/${name}`, { method: 'DELETE' }),

  getSettings: () => fetchAPI<SettingsResponse>('/api/settings'),
  updateSettings: (settings: Partial<Settings>) =>
    fetchAPI<SettingsResponse>('/api/settings', {
      method: 'PUT',
      body: JSON.stringify(settings),
    }),

  getIgnore: () => fetchAPI<IgnorePatterns>('/api/ignore'),
  updateIgnore: (patterns: string[]) =>
    fetchAPI<{ ok: boolean }>('/api/ignore', {
      method: 'PUT',
      body: JSON.stringify({ patterns }),
    }),

  updateEnv: (gemini_api_key: string) =>
    fetchAPI<{ ok: boolean; has_gemini_key: boolean }>('/api/env', {
      method: 'POST',
      body: JSON.stringify({ gemini_api_key }),
    }),

  getArenas: () => fetchAPI<ArenaSummary[]>('/api/arenas'),
  getArenaFile: async (n: number, file: string) => {
    const token = await getToken();
    const res = await fetch(`${BASE_URL}/api/arenas/${n}/${file}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    return res.text();
  },

  getModels: () => fetchAPI<ModelFiles>('/api/models'),
  /** Legacy alias — accepts any string for backward compat with Task 4. */
  updateModel: (letter: string, content: string) =>
    fetchAPI<{ ok: boolean }>(`/api/models/${letter}`, {
      method: 'PUT',
      body: JSON.stringify({ content }),
    }),
  /** Typed model write — accepts A-D + 'prompt' (content script path). */
  putModel: (target: ModelTarget, content: string) =>
    fetchAPI<{ ok: boolean; target: string; path: string }>(`/api/models/${target}`, {
      method: 'PUT',
      body: JSON.stringify({ content }),
    }),

  checkRun: (input: string) =>
    fetchAPI<RunCheckResponse>('/api/run/check', {
      method: 'POST',
      body: JSON.stringify({ input }),
    }),

  run: (req: RunRequest) =>
    fetchAPI<RunResponse>('/api/run', {
      method: 'POST',
      body: JSON.stringify(req),
    }),
};
