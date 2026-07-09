// src/content/lmarena.ts
// Extracts the prompt + model responses from the LMArena comparison
// carousel and relays them to the background worker -> local server.
//
// Selectors prefer ARIA anchors (role="group", aria-roledescription="slide")
// since Tailwind utility classes are the part most likely to change on
// redesign. Update SELECTORS if LMArena's markup changes — the extraction
// and serialization logic below should not need to.

const SELECTORS = {
  carousel: '[role="region"][aria-roledescription="carousel"]',
  slide: '[role="group"][aria-roledescription="slide"]',
  slideHeaderName: ':scope > div:first-child span.truncate',
  slideResponseBody: 'div.prose',
  slideToolbar:
    'div.flex.items-center.justify-between.gap-2 > div.flex.items-center.gap-1',
  userBubbleProse: '.self-end .prose',
} as const;

const MODEL_LETTERS = ['A', 'B', 'C', 'D'] as const;

// ---------------------------------------------------------------------------
// HTML → Markdown serialization (handles <pre>, <code>, <p>, <li>, etc.)
// ---------------------------------------------------------------------------

function serializeProse(el: Element): string {
  const parts: string[] = [];

  const walk = (node: Node): void => {
    if (node.nodeType === Node.TEXT_NODE) {
      parts.push(node.textContent ?? '');
      return;
    }
    if (!(node instanceof HTMLElement)) return;

    switch (node.tagName.toLowerCase()) {
      case 'pre': {
        const codeEl = node.querySelector('code');
        const lang = codeEl?.className.match(/language-(\w+)/)?.[1] ?? '';
        const code = (codeEl?.textContent ?? node.textContent ?? '').replace(/\n$/, '');
        parts.push(`\n\`\`\`${lang}\n${code}\n\`\`\`\n`);
        break;
      }
      case 'code':
        // Inline code (not inside <pre>)
        if (node.parentElement?.tagName.toLowerCase() !== 'pre') {
          parts.push(`\`${node.textContent}\``);
        }
        break;
      case 'p':
        node.childNodes.forEach(walk);
        parts.push('\n\n');
        break;
      case 'br':
        parts.push('\n');
        break;
      case 'li':
        parts.push('- ');
        node.childNodes.forEach(walk);
        parts.push('\n');
        break;
      case 'strong':
      case 'b':
        parts.push(`**${node.textContent}**`);
        break;
      case 'em':
      case 'i':
        parts.push(`_${node.textContent}_`);
        break;
      default:
        node.childNodes.forEach(walk);
    }
  };

  walk(el);
  return parts.join('').replace(/\n{3,}/g, '\n\n').trim();
}

// ---------------------------------------------------------------------------
// Extraction
// ---------------------------------------------------------------------------

function extractPrompt(): string | null {
  const bubbles = document.querySelectorAll(SELECTORS.userBubbleProse);
  if (bubbles.length === 0) return null;
  // Most recent user turn is the last right-aligned bubble.
  return serializeProse(bubbles[bubbles.length - 1]);
}

// ---------------------------------------------------------------------------
// UI: toast + button injection
// ---------------------------------------------------------------------------

function flashToast(msg: string, isError = false): void {
  const toast = document.createElement('div');
  toast.textContent = msg;
  toast.style.cssText = `position:fixed;bottom:16px;right:16px;z-index:99999;
    padding:8px 14px;border-radius:8px;font:12px sans-serif;color:#fff;
    background:${isError ? '#b91c1c' : '#15803d'};box-shadow:0 2px 8px rgba(0,0,0,.3);`;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 2500);
}

function sendCapture(target: string, content: string): void {
  chrome.runtime.sendMessage(
    { type: 'CTX_SAVE_MODEL', target, content },
    (res) => {
      if (chrome.runtime.lastError) {
        flashToast(`Send failed: ${chrome.runtime.lastError.message}`, true);
        return;
      }
      flashToast(
        res?.ok ? `Saved ${target}.txt` : `Failed: ${res?.error ?? 'unknown'}`,
        !res?.ok,
      );
    },
  );
}

function injectSlideButton(slide: Element, letter: string): void {
  // Idempotent across re-renders — skip if already injected.
  if (slide.querySelector('.ctx-send-btn')) return;

  const toolbar = slide.querySelector(SELECTORS.slideToolbar) ?? slide;
  const btn = document.createElement('button');
  btn.textContent = 'Send to Context';
  btn.className = 'ctx-send-btn';
  btn.style.cssText =
    'font-size:11px;padding:2px 8px;border-radius:6px;border:1px solid currentColor;' +
    'background:transparent;cursor:pointer;margin-left:4px;';
  btn.addEventListener('click', (e) => {
    e.preventDefault();
    e.stopPropagation();
    const bodyEl = slide.querySelector(SELECTORS.slideResponseBody);
    const content = bodyEl ? serializeProse(bodyEl) : '';
    if (!content) {
      flashToast(`${letter} response is empty`, true);
      return;
    }
    sendCapture(letter, content);
  });
  toolbar.appendChild(btn);
}

function injectPromptButton(): void {
  const carousel = document.querySelector(SELECTORS.carousel);
  if (!carousel || document.querySelector('.ctx-send-prompt-btn')) return;

  const btn = document.createElement('button');
  btn.textContent = 'Send Prompt to Context';
  btn.className = 'ctx-send-prompt-btn';
  btn.style.cssText =
    'position:absolute;top:-28px;right:0;font-size:11px;padding:2px 8px;' +
    'border-radius:6px;border:1px solid currentColor;background:transparent;cursor:pointer;';
  btn.addEventListener('click', (e) => {
    e.preventDefault();
    const prompt = extractPrompt();
    if (!prompt) {
      flashToast('No prompt found', true);
      return;
    }
    sendCapture('prompt', prompt);
  });
  (carousel.parentElement ?? carousel).appendChild(btn);
}

function attachButtons(): void {
  document.querySelectorAll(SELECTORS.slide).forEach((slide, i) => {
    injectSlideButton(slide, MODEL_LETTERS[i] ?? String.fromCharCode(65 + i));
  });
  injectPromptButton();
}

// ---------------------------------------------------------------------------
// Init: re-scan on mutation (debounced) so buttons survive streaming re-renders
// ---------------------------------------------------------------------------

let debounceTimer: number | undefined;
new MutationObserver(() => {
  window.clearTimeout(debounceTimer);
  debounceTimer = window.setTimeout(attachButtons, 400);
}).observe(document.body, { childList: true, subtree: true });

attachButtons();

export {};
