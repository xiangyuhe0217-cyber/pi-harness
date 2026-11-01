const $ = (selector) => document.querySelector(selector);
const messagesEl = $("#chat-messages");
const inputEl = $("#chat-input");
const formEl = $("#chat-form");
const sendEl = $("#chat-send");

const state = {
  sessionId: localStorage.getItem("harness-chat-session") || "",
  sending: false,
};

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function format(text) {
  let out = escapeHtml(text);
  out = out.replace(/```([\s\S]*?)```/g, (_, code) => `<pre>${code.trim()}</pre>`);
  out = out.replace(/`([^`]+)`/g, "<code>$1</code>");
  return out;
}

function toast(message) {
  const el = $("#toast");
  el.textContent = message;
  el.classList.add("show");
  clearTimeout(window.__toast);
  window.__toast = setTimeout(() => el.classList.remove("show"), 3000);
}

async function api(path, options = {}, retry = true) {
  const token = localStorage.getItem("harness-web-token") || "";
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(path, { ...options, headers });
  if (response.status === 401 && retry) {
    const entered = window.prompt("Harness access token:");
    if (entered) {
      localStorage.setItem("harness-web-token", entered);
      return api(path, options, false);
    }
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}

function scrollBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function hideWelcome() {
  const welcome = $("#chat-welcome");
  if (welcome) welcome.remove();
}

function showWelcome() {
  messagesEl.innerHTML = `
    <div class="chat-welcome" id="chat-welcome">
      <div class="welcome-mark">H</div>
      <h1>今天想让我做什么？</h1>
      <p>我可以在这个沙箱里读文件、写代码、跑命令；危险操作会被 Harness 拦下并解释。</p>
      <div class="suggestions">
        <button class="suggestion" data-suggest="这个工作区里有什么文件？">看看工作区</button>
        <button class="suggestion" data-suggest="写一个 greet.py，内容是一个 greet(name) 函数，并运行它。">写并运行代码</button>
        <button class="suggestion" data-suggest="解释 hello.py 在做什么。">解释代码</button>
      </div>
    </div>`;
  bindSuggestions();
}

function addMessage(role, text, meta = {}) {
  hideWelcome();
  const wrap = document.createElement("div");
  wrap.className = `msg ${role}`;
  const label = role === "user" ? "你" : "H";
  const tools = Array.from(new Set(meta.tools || []));
  const blocked = Number(meta.blocked || 0);
  let details = "";
  if (tools.length || blocked) {
    details = `<details class="tool-details">
      <summary>执行详情 · 工具 ${tools.length} · 拦截 ${blocked}</summary>
      <div class="tool-list">
        ${tools.map((tool) => `<span class="tool-chip">${escapeHtml(tool)}</span>`).join("")}
        ${blocked ? `<span class="tool-chip blocked">blocked × ${blocked}</span>` : ""}
      </div>
    </details>`;
  }
  wrap.innerHTML = `
    <div class="avatar">${label}</div>
    <div>
      <div class="bubble">${format(text)}</div>
      ${details}
    </div>`;
  messagesEl.appendChild(wrap);
  scrollBottom();
}

function addTyping() {
  hideWelcome();
  const wrap = document.createElement("div");
  wrap.className = "msg assistant";
  wrap.id = "chat-typing";
  wrap.innerHTML = `
    <div class="avatar">H</div>
    <div class="bubble"><div class="typing"><span></span><span></span><span></span></div></div>`;
  messagesEl.appendChild(wrap);
  scrollBottom();
}

function removeTyping() {
  const typing = $("#chat-typing");
  if (typing) typing.remove();
}

function renderHistory(messages) {
  messagesEl.innerHTML = "";
  if (!messages.length) {
    showWelcome();
    return;
  }
  for (const message of messages) {
    if (message.role === "user") addMessage("user", message.text);
    else addMessage("assistant", message.text, message);
  }
}

function updateSessionLabel() {
  $("#chat-session").textContent = state.sessionId || "—";
}

async function newSession() {
  const data = await api("/api/chat/session", { method: "POST", body: "{}" });
  state.sessionId = data.session_id;
  localStorage.setItem("harness-chat-session", state.sessionId);
  updateSessionLabel();
  renderHistory([]);
}

async function ensureSession() {
  if (state.sessionId) {
    try {
      const data = await api(`/api/chat/${encodeURIComponent(state.sessionId)}`);
      updateSessionLabel();
      renderHistory(data.messages || []);
      return;
    } catch (error) {
      localStorage.removeItem("harness-chat-session");
      state.sessionId = "";
    }
  }
  await newSession();
}

async function sendMessage(text) {
  const message = text.trim();
  if (!message || state.sending) return;
  state.sending = true;
  sendEl.disabled = true;
  inputEl.disabled = true;
  addMessage("user", message);
  inputEl.value = "";
  inputEl.style.height = "auto";
  addTyping();
  try {
    const data = await api("/api/chat", {
      method: "POST",
      body: JSON.stringify({ session_id: state.sessionId, message }),
    });
    removeTyping();
    addMessage("assistant", data.reply, {
      tools: data.tools,
      blocked: data.blocked,
    });
    state.sessionId = data.session_id;
    localStorage.setItem("harness-chat-session", state.sessionId);
    updateSessionLabel();
  } catch (error) {
    removeTyping();
    addMessage("assistant", `请求失败：${error.message}`);
    toast(error.message);
  } finally {
    state.sending = false;
    sendEl.disabled = false;
    inputEl.disabled = false;
    inputEl.focus();
  }
}

async function loadHealth() {
  try {
    const data = await api("/api/health");
    const ok = data.litellm?.ok && data.pi?.ok;
    $("#chat-health-dot").className = `dot ${ok ? "ok" : "bad"}`;
    $("#chat-health-text").textContent = ok ? "ready" : "degraded";
  } catch {
    $("#chat-health-dot").className = "dot bad";
    $("#chat-health-text").textContent = "offline";
  }
}

function bindSuggestions() {
  document.querySelectorAll("[data-suggest]").forEach((button) => {
    button.addEventListener("click", () => sendMessage(button.dataset.suggest));
  });
}

function autosize() {
  inputEl.style.height = "auto";
  inputEl.style.height = `${Math.min(inputEl.scrollHeight, 160)}px`;
}

formEl.addEventListener("submit", (event) => {
  event.preventDefault();
  sendMessage(inputEl.value);
});
inputEl.addEventListener("input", autosize);
inputEl.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendMessage(inputEl.value);
  }
});
$("#new-chat").addEventListener("click", async () => {
  try {
    await newSession();
    toast("已新建会话");
  } catch (error) {
    toast(`新建失败：${error.message}`);
  }
});

(async function init() {
  await loadHealth();
  await ensureSession();
  setInterval(loadHealth, 15000);
  inputEl.focus();
})();
