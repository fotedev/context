// Service worker: health polling + badge status + content-script relay.
// All state lives in chrome.storage.local so service-worker wake-ups
// (MV3 kills idle workers fast) don't lose context.

import { api } from '../shared/api';
import type { ModelTarget } from '../shared/types';

const BASE_URL = 'http://127.0.0.1:8765';

async function checkHealth(): Promise<void> {
  try {
    const res = await fetch(`${BASE_URL}/health`);
    if (res.ok) {
      chrome.action.setBadgeText({ text: 'ON' });
      chrome.action.setBadgeBackgroundColor({ color: '#4CAF50' });
    } else {
      throw new Error('Bad status');
    }
  } catch {
    chrome.action.setBadgeText({ text: 'OFF' });
    chrome.action.setBadgeBackgroundColor({ color: '#F44336' });
  }
}

chrome.runtime.onInstalled.addListener(() => {
  checkHealth();
  setInterval(checkHealth, 30000);
});

chrome.runtime.onStartup.addListener(() => {
  checkHealth();
  setInterval(checkHealth, 30000);
});

// --- Content-script relay: LMArena capture -> local server -------------
// The content script (lmarena.ts) can't call the server directly (CORS +
// no fetch from content context to localhost in some configs), so it
// sends a chrome.runtime.sendMessage which the service worker relays.
chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg?.type === 'CTX_SAVE_MODEL') {
    (async () => {
      try {
        await api.putModel(msg.target as ModelTarget, msg.content as string);
        sendResponse({ ok: true });
      } catch (err) {
        sendResponse({
          ok: false,
          error: err instanceof Error ? err.message : String(err),
        });
      }
    })();
    return true; // keep the message channel open for the async response
  }
  return false;
});

export {};
