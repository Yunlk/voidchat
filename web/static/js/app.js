/* ── voidchat client ─────────────────────────────── */

const $ = (s) => document.querySelector(s);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// state
let charId = '';
let sessionId = '';
let sending = false;
let dlIframeRef = null;

// dom
const msgList = $('#msgList');
const msgInput = $('#msgInput');
const sendBtn = $('#sendBtn');
const statusBar = $('#statusBar');
const charNameEl = $('#charName');
const charModelEl = $('#charModel');

// ── init ───────────────────────────────────────────

async function init() {
  charId = new URLSearchParams(location.search).get('c') || '';
  if (!charId) { location.href = '/'; return; }

  sessionId = 's_' + charId + '_' + Date.now();
  try {
    const res = await fetch('/api/characters');
    const chars = await res.json();
    const char = chars.find((c) => c.id === charId);
    if (!char) { status('角色不存在'); return; }

    charNameEl.textContent = char.name;
    charModelEl.textContent = '';

    addMsg('assistant', char.greeting);
    enableInput();
    status('已上线');
  } catch (e) {
    status('无法连接');
  }
}

// ── messages ───────────────────────────────────────

function addMsg(role, text) {
  const div = document.createElement('div');
  div.className = 'msg ' + role;

  if (role === 'assistant') {
    const label = document.createElement('div');
    label.className = 'msg-label';
    label.textContent = charNameEl.textContent || '…';
    div.appendChild(label);
  } else if (role === 'user') {
    const label = document.createElement('div');
    label.className = 'msg-label';
    label.textContent = '你';
    div.appendChild(label);
  }

  const body = document.createElement('div');
  body.className = 'msg-body';
  body.textContent = text;
  div.appendChild(body);

  msgList.appendChild(div);
  scrollBottom();
  return div;
}

function addSystem(text) {
  const div = document.createElement('div');
  div.className = 'msg system';
  const body = document.createElement('div');
  body.className = 'msg-body';
  body.textContent = text;
  div.appendChild(body);
  msgList.appendChild(div);
  scrollBottom();
}

function typingBubble() {
  const div = document.createElement('div');
  div.className = 'msg assistant typing';
  const label = document.createElement('div');
  label.className = 'msg-label';
  label.textContent = charNameEl.textContent || '…';
  div.appendChild(label);
  const body = document.createElement('div');
  body.className = 'msg-body';
  body.textContent = '…';
  div.appendChild(body);
  msgList.appendChild(div);
  scrollBottom();
  return div;
}

function scrollBottom() {
  msgList.scrollTop = msgList.scrollHeight;
}

function status(text) {
  statusBar.textContent = text;
}

// ── enable / disable ──────────────────────────────

function enableInput() {
  msgInput.disabled = false;
  sendBtn.disabled = false;
  msgInput.focus();
}

function disableInput() {
  msgInput.disabled = true;
  sendBtn.disabled = true;
}

// ── send ───────────────────────────────────────────

async function doSend() {
  if (sending) return;
  const text = msgInput.value.trim();
  if (!text) return;

  sending = true;
  disableInput();
  msgInput.value = '';

  addMsg('user', text);
  const typing = typingBubble();
  status('…');

  try {
    const resp = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ character: charId, message: text, session_id: sessionId }),
    });

    if (!resp.ok) throw new Error(await resp.text());

    // read SSE stream
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buf = '';
    let full = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });

      const lines = buf.split('\n');
      buf = lines.pop() || '';

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const data = line.slice(6);
        if (data === '[DONE]') continue;
        try {
          const { token } = JSON.parse(data);
          full += token;
        } catch {}
      }
    }

    // remove typing bubble
    typing.remove();
    status('');

    // parse & play actions
    await playActions(full);

  } catch (e) {
    typing.remove();
    addSystem('连接断开了');
    status('离线');
  }

  sending = false;
  enableInput();
}

// ── action parser ──────────────────────────────────

async function playActions(text) {
  // check DL_SEQ
  const dlMatch = text.match(/\[DL_SEQ\]([\s\S]*?)\[\/DL_SEQ\]/);
  let outside = text;
  if (dlMatch) {
    outside = (text.slice(0, text.indexOf('[DL_SEQ]')) + text.slice(text.indexOf('[/DL_SEQ]') + '[/DL_SEQ]'.length)).trim();
    const inner = dlMatch[1].trim();
    const lines = inner.split('\n').map((l) => l.trim()).filter(Boolean);

    for (const line of lines) {
      if (line.startsWith('[DL:START]')) {
        const fname = line.slice('[DL:START]'.length).trim();
        const dlId = 'dl_' + Date.now();
        const iframe = document.createElement('iframe');
        iframe.style.display = 'none';
        iframe.src = '/api/dl/' + dlId + '?f=' + encodeURIComponent(fname);
        document.body.appendChild(iframe);
        dlIframeRef = iframe;

        addSystem('⬇ 开始下载 ' + fname + ' …');
        await sleep(350);

      } else if (line.startsWith('[DL:CANCEL]')) {
        await sleep(800);
        if (dlIframeRef) {
          dlIframeRef.remove();
          dlIframeRef = null;
        }
        // also send abort to server
        try {
          await fetch('/api/dl-abort', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: dlIframeRef ? '' : 'x' }),
          });
        } catch {}

        addSystem('⬇ 下载中断');
        await sleep(350);

      } else {
        // text action
        addMsg('assistant', line);
        await sleep(350);
      }
    }
  }

  // split remaining text by [MSG]
  if (outside) {
    const parts = outside.split(/\[MSG\]/i);
    for (const part of parts) {
      const trimmed = part.trim();
      if (trimmed) {
        addMsg('assistant', trimmed);
        await sleep(400);
      }
    }
  }

  scrollBottom();
}

// ── input events ───────────────────────────────────

msgInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    doSend();
  }
});

msgInput.addEventListener('input', () => {
  msgInput.style.height = 'auto';
  msgInput.style.height = Math.min(msgInput.scrollHeight, 120) + 'px';
});

sendBtn.addEventListener('click', doSend);

// ── start ──────────────────────────────────────────

init();
