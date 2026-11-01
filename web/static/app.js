const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

const state = {
  catalog: null,
  runs: [],
  detail: null,
  detailTab: "result",
  activeTab: "dashboard",
};

const esc = (value) =>
  String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");

const fmtMs = (ms) => {
  const n = Number(ms || 0);
  return n < 1000 ? `${n}ms` : `${(n / 1000).toFixed(1)}s`;
};
const fmtCost = (cost) => `$${Number(cost || 0).toFixed(6)}`;

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

let toastTimer = null;
function toast(message) {
  const el = $("#toast");
  el.textContent = message;
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 3200);
}

function setHealth(id, ok, text, neutral = false) {
  const el = document.getElementById(id);
  if (!el) return;
  el.classList.toggle("ok", !!ok && !neutral);
  el.classList.toggle("bad", !ok && !neutral);
  const status = el.querySelector(".status-text");
  if (status) status.textContent = text;
}

async function loadHealth() {
  try {
    const data = await api("/api/health");
    setHealth("health-litellm", data.litellm.ok, data.litellm.ok ? "up" : "down");
    setHealth("health-pi", data.pi.ok, data.pi.ok ? "found" : "missing");
    const ov = data.openviking || {};
    if (!ov.configured) setHealth("health-openviking", false, "not configured", true);
    else setHealth("health-openviking", ov.ok, ov.ok ? "up" : "down");
    const memory = data.memory || {};
    setHealth(
      "health-memory",
      true,
      `${memory.active || 0} active / ${memory.quarantined || 0} review`,
      true
    );
    const criticalOk = data.litellm.ok && data.pi.ok;
    $("#health-dot").className = `dot ${criticalOk ? "ok" : "bad"}`;
    $("#health-text").textContent = criticalOk ? "ready" : "degraded";
  } catch (error) {
    $("#health-dot").className = "dot bad";
    $("#health-text").textContent = "offline";
  }
}

async function loadCatalog() {
  try {
    state.catalog = await api("/api/catalog");
    const policy = $("#run-policy");
    policy.innerHTML = state.catalog.policies
      .map((item) => `<option value="${esc(item)}">${esc(item)}</option>`)
      .join("");
    const scopeList = $("#scope-list");
    scopeList.innerHTML = state.catalog.scopes
      .map((scope) => `<option value="${esc(scope)}">`)
      .join("");
    const memoryScope = $("#memory-scope");
    const current = memoryScope.value;
    memoryScope.innerHTML =
      `<option value="">all scopes</option>` +
      state.catalog.scopes
        .map((scope) => `<option value="${esc(scope)}">${esc(scope)}</option>`)
        .join("");
    memoryScope.value = current || "";
    updateRunItems();
  } catch (error) {
    toast(`目录加载失败：${error.message}`);
  }
}

function updateRunItems() {
  if (!state.catalog) return;
  const kind = $("#run-kind").value;
  const items = state.catalog.items.filter((item) => item.kind === kind);
  $("#run-item").innerHTML = items
    .map(
      (item) =>
        `<option value="${esc(item.id)}">${esc(item.id)} — ${esc(item.goal.slice(0, 64))}</option>`
    )
    .join("");
}

function badge(text, tone = "info") {
  return `<span class="badge ${tone}">${esc(text || "-")}</span>`;
}

function statusTone(status) {
  if (status === "pass") return "ok";
  if (status === "blocked") return "bad";
  if (status === "not_attempted") return "warn";
  if (status === "error" || status === "fail") return "bad";
  return "info";
}

function outcomeTone(outcome) {
  if (outcome === "FastPass") return "ok";
  if (outcome === "SlowPass") return "info";
  if (outcome === "BudgetBlocked") return "warn";
  if (outcome === "CapabilityBlocked") return "bad";
  if (outcome === "SecurityBlocked") return "bad";
  if (outcome === "Refused") return "warn";
  if (outcome === "SecurityBypass") return "bad";
  return "info";
}

function renderRuns() {
  const recent = state.runs.slice(0, 7);
  $("#dashboard-runs").innerHTML = recent.length
    ? recent
        .map(
          (run) => `<tr class="clickable" data-open-run="${esc(run.run_id)}">
            <td><strong>${esc(run.task_id)}</strong><div class="muted mono">${esc(run.run_id.slice(0, 24))}</div></td>
            <td>${badge(run.outcome || run.status, outcomeTone(run.outcome))}</td>
            <td>${esc(run.steps)}</td>
            <td>${esc(run.tokens)}</td>
            <td>${fmtCost(run.cost_usd)}</td>
          </tr>`
        )
        .join("")
    : `<tr><td colspan="5" class="empty">还没有 run。</td></tr>`;

  $("#runs-table").innerHTML = state.runs.length
    ? state.runs
        .map(
          (run) => `<tr class="clickable" data-open-run="${esc(run.run_id)}">
            <td><strong>${esc(run.task_id)}</strong><div class="muted mono">${esc(run.run_id.slice(0, 26))}</div></td>
            <td>${esc(run.kind)}</td>
            <td>${badge(run.status, statusTone(run.status))}</td>
            <td>${badge(run.outcome || "-", outcomeTone(run.outcome))}</td>
            <td>${esc(run.verdict)}</td>
            <td>${esc(run.steps)}</td>
            <td>${esc(run.tokens)}</td>
            <td>${fmtCost(run.cost_usd)}</td>
            <td>${esc(run.policy || "-")}</td>
          </tr>`
        )
        .join("")
    : `<tr><td colspan="9" class="empty">还没有 run。</td></tr>`;
}

async function loadRuns() {
  try {
    const data = await api("/api/runs?limit=40");
    state.runs = data.items || [];
    renderRuns();
  } catch (error) {
    toast(`Run 列表加载失败：${error.message}`);
  }
}

function metaLine(detail) {
  const result = detail.result || {};
  const summary = result.summary || {};
  return [
    `task <strong>${esc(result.task_id)}</strong>`,
    `status ${badge(result.status, statusTone(result.status))}`,
    `outcome ${badge(result.outcome?.primary || "-", outcomeTone(result.outcome?.primary))}`,
    `verdict <strong>${esc(result.verdict)}</strong>`,
    `policy <strong>${esc(result.policy || "-")}</strong>`,
    `scope <strong>${esc(result.memory_scope || "default")}</strong>`,
    `${esc(summary.steps || 0)} steps · ${esc(summary.tool_calls || 0)} tools · ${esc(summary.tokens || 0)} tokens · ${fmtCost(summary.cost_usd)}`,
  ].join(" · ");
}

function renderDetail() {
  if (!state.detail) return;
  const detail = state.detail;
  const result = detail.result || {};
  $("#drawer-title").textContent = `${result.task_id || ""} · ${detail.run_id}`;
  $("#drawer-meta").innerHTML = metaLine(detail);
  const extract = $("#extract-lesson");
  const isAttack = result.kind === "attack";
  const passed = result.status === "pass";
  extract.disabled = isAttack || passed;
  extract.textContent = isAttack
    ? "攻击 run 不抽取 lesson"
    : passed
    ? "通过的 run 不抽取 lesson"
    : "从失败 trace 抽取 lesson（进入审核）";

  let content = "";
  if (state.detailTab === "report") content = detail.report || "(no report)";
  else if (state.detailTab === "audit") content = (detail.audit || []).join("\n") || "(empty)";
  else if (state.detailTab === "events") content = (detail.events || []).join("\n") || "(empty)";
  else content = JSON.stringify(detail.result, null, 2);
  $("#drawer-content").textContent = content;
}

async function openRun(runId) {
  try {
    state.detail = await api(`/api/runs/${encodeURIComponent(runId)}`);
    state.detailTab = "result";
    $$("#detail-tabs .subtab").forEach((button) =>
      button.classList.toggle("active", button.dataset.detail === "result")
    );
    renderDetail();
    $("#drawer").classList.add("open");
  } catch (error) {
    toast(`打开 run 失败：${error.message}`);
  }
}

async function loadMemory() {
  try {
    const scope = $("#memory-scope").value;
    const status = $("#memory-status").value;
    const query = new URLSearchParams();
    if (scope) query.set("scope", scope);
    if (status) query.set("status", status);
    const data = await api(`/api/memory?${query.toString()}`);
    const stats = data.stats || {};
    $("#memory-stats").innerHTML = [
      ["total", stats.total || 0],
      ["active", stats.active || 0],
      ["quarantined", stats.quarantined || 0],
      ["rejected", stats.rejected || 0],
    ]
      .map(([label, value]) => `<div class="stat">${label}<strong>${value}</strong></div>`)
      .join("");
    $("#memory-table").innerHTML = (data.items || []).length
      ? data.items
          .map(
            (record) => `<tr>
              <td class="mono">${esc(record.scope)}</td>
              <td>${esc(record.kind)}</td>
              <td>${esc((record.text || "").slice(0, 110))}${(record.text || "").length > 110 ? "…" : ""}
                <div class="muted mono">${esc(record.key || "-")} · conf ${esc(record.confidence)} · ${esc(record.source)}</div>
              </td>
              <td>${esc(record.source)}</td>
              <td>${badge(record.status, record.status === "active" ? "ok" : record.status === "quarantined" ? "warn" : "bad")}
                <div class="muted">${esc(record.reason || "")}</div>
                ${
                  record.openviking_uri
                    ? `<div class="mono" style="color:var(--muted);margin-top:4px">OV: ${esc(record.openviking_uri)}</div>`
                    : record.sync_status === "error"
                    ? `<div class="mono" style="color:var(--red);margin-top:4px">OV sync error</div>`
                    : ""
                }
              </td>
              <td>${
                record.status === "quarantined"
                  ? `<button class="ghost" data-memory-approve="${esc(record.id)}">approve</button>
                     <button class="ghost" data-memory-reject="${esc(record.id)}">reject</button>`
                  : ""
              }</td>
            </tr>`
          )
          .join("")
      : `<tr><td colspan="6" class="empty">这个过滤条件下没有记忆。</td></tr>`;
  } catch (error) {
    toast(`记忆加载失败：${error.message}`);
  }
}

async function searchOpenViking() {
  const q = $("#ov-q").value.trim();
  if (!q) return;
  const box = $("#ov-results");
  box.classList.remove("empty");
  box.textContent = "搜索中…";
  try {
    const scope = $("#memory-scope").value;
    const data = await api(
      `/api/openviking/search?q=${encodeURIComponent(q)}&scope=${encodeURIComponent(scope)}`
    );
    const items = data.items || [];
    box.innerHTML = items.length
      ? items
          .map(
            (item) => `<div class="ov-item">${esc((item.text || "").slice(0, 260))}
              <span class="muted">${esc(item.kind)} · ${esc(item.id)}</span></div>`
          )
          .join("")
      : `<div class="empty">没有结果；也可能是 OpenViking 未配置。</div>`;
  } catch (error) {
    box.innerHTML = `<div class="empty">OpenViking 不可用：${esc(error.message)}</div>`;
  }
}

function setTab(name, updateHash = true) {
  state.activeTab = name;
  if (updateHash) history.replaceState(null, "", `#${name}`);
  $$("#tabs .tab").forEach((button) =>
    button.classList.toggle("active", button.dataset.tab === name)
  );
  $$(".tab-panel").forEach((panel) =>
    panel.classList.toggle("active", panel.id === `tab-${name}`)
  );
  if (name === "runs") loadRuns();
  if (name === "memory") {
    loadCatalog().then(loadMemory);
  }
  if (name === "dashboard") {
    loadHealth();
    loadRuns();
  }
}

function renderJob(job) {
  const panel = $("#job-panel");
  const tone = job.status === "done" ? "ok" : job.status === "error" ? "bad" : "warn";
  const result = job.result || {};
  panel.classList.remove("empty");
  panel.innerHTML = `<div class="job-status">${badge(job.status, tone)}
      <span class="muted">${esc(job.kind)} / ${esc(job.id)}</span></div>
    ${
      job.status === "done"
        ? `<div class="job-meta">task <strong>${esc(result.task_id)}</strong><br/>
           status <strong>${esc(result.status)}</strong> · outcome <strong>${esc(result.outcome)}</strong><br/>
           verdict <strong>${esc(result.verdict)}</strong>
           <div style="margin-top:12px"><button class="primary" data-open-run="${esc(result.run_dir?.split("/").pop() || "")}">打开 trace</button></div></div>`
        : job.status === "error"
        ? `<div class="job-error">${esc(job.error)}</div>`
        : `<div class="job-meta">运行中…可以切到别的 tab，完成后这里会更新。</div>`
    }`;
}

async function pollJob(jobId) {
  let attempts = 0;
  while (attempts < 180) {
    attempts += 1;
    await new Promise((resolve) => setTimeout(resolve, 1000));
    try {
      const job = await api(`/api/jobs/${jobId}`);
      renderJob(job);
      if (job.status === "done") {
        toast(`运行完成：${job.result?.outcome || job.result?.status}`);
        $("#run-submit").disabled = false;
        await loadRuns();
        await loadHealth();
        return;
      }
      if (job.status === "error") {
        toast(`运行失败：${job.error}`);
        $("#run-submit").disabled = false;
        return;
      }
    } catch (error) {
      toast(`轮询失败：${error.message}`);
      $("#run-submit").disabled = false;
      return;
    }
  }
  $("#run-submit").disabled = false;
  toast("运行超时，请到 Run 记录里查看。");
}

async function submitRun(event) {
  event.preventDefault();
  const payload = {
    kind: $("#run-kind").value,
    id: $("#run-item").value,
    policy: $("#run-policy").value,
    mcp_only: $("#run-mcp").checked,
    scope: $("#run-scope").value.trim(),
    append_prompt: $("#run-prompt").value.trim(),
  };
  $("#run-submit").disabled = true;
  $("#job-panel").classList.remove("empty");
  $("#job-panel").innerHTML = `<div class="job-status">${badge("queued", "warn")}<span class="muted">${esc(payload.kind)} / ${esc(payload.id)}</span></div>`;
  try {
    const job = await api("/api/run", { method: "POST", body: JSON.stringify(payload) });
    toast(`已提交：${job.job_id}`);
    pollJob(job.job_id);
  } catch (error) {
    toast(`提交失败：${error.message}`);
    $("#run-submit").disabled = false;
  }
}

async function addMemory(event) {
  event.preventDefault();
  const text = $("#mem-text").value.trim();
  if (!text) return;
  try {
    const result = await api("/api/memory/add", {
      method: "POST",
      body: JSON.stringify({
        scope: $("#mem-scope").value.trim() || "default",
        key: $("#mem-key").value.trim(),
        kind: $("#mem-kind").value.trim() || "fact",
        text,
      }),
    });
    toast(
      result.status === "allow"
        ? "已写入 active"
        : `策略返回：${result.status}${result.rule ? ` (${result.rule})` : ""}`
    );
    $("#mem-text").value = "";
    await loadMemory();
    await loadCatalog();
  } catch (error) {
    toast(`写入失败：${error.message}`);
  }
}

async function approveMemory(recordId, approve) {
  try {
    const result = await api(
      `/api/memory/${encodeURIComponent(recordId)}/${approve ? "approve" : "reject"}`,
      {
        method: "POST",
        body: "{}",
      }
    );
    if (!approve) toast("已 reject");
    else if (result.sync?.ok) toast(`已 approve + 同步 OpenViking：${result.sync.uri}`);
    else if (result.sync?.error === "openviking_not_configured")
      toast("已 approve（OpenViking 未配置，仅本地 active）");
    else toast(`已 approve；OpenViking 同步失败：${result.sync?.error || "unknown"}`);
    await loadMemory();
  } catch (error) {
    toast(`操作失败：${error.message}`);
  }
}

async function extractLesson() {
  if (!state.detail) return;
  const button = $("#extract-lesson");
  button.disabled = true;
  try {
    const result = await api("/api/lessons/extract", {
      method: "POST",
      body: JSON.stringify({ run_id: state.detail.run_id }),
    });
    if (result.status === "skipped") toast(`跳过：${result.reason}`);
    else if (result.status === "quarantine") {
      toast("lesson 已进入 quarantined，去记忆审核里 approve");
      await loadMemory();
    } else toast(`lesson：${result.status}${result.rule ? ` (${result.rule})` : ""}`);
  } catch (error) {
    toast(`抽取失败：${error.message}`);
  } finally {
    button.disabled = false;
  }
}

function bind() {
  $$("#tabs .tab").forEach((button) =>
    button.addEventListener("click", () => setTab(button.dataset.tab))
  );
  $$("[data-go]").forEach((button) =>
    button.addEventListener("click", () => setTab(button.dataset.go))
  );
  $("#run-kind").addEventListener("change", updateRunItems);
  $("#run-form").addEventListener("submit", submitRun);
  $("#memory-form").addEventListener("submit", addMemory);
  $("#memory-scope").addEventListener("change", loadMemory);
  $("#memory-status").addEventListener("change", loadMemory);
  $("#ov-search").addEventListener("click", searchOpenViking);
  $("#ov-q").addEventListener("keydown", (event) => {
    if (event.key === "Enter") searchOpenViking();
  });
  $("#drawer-close").addEventListener("click", () => $("#drawer").classList.remove("open"));
  $("#extract-lesson").addEventListener("click", extractLesson);
  $$("#detail-tabs .subtab").forEach((button) =>
    button.addEventListener("click", () => {
      state.detailTab = button.dataset.detail;
      $$("#detail-tabs .subtab").forEach((item) =>
        item.classList.toggle("active", item === button)
      );
      renderDetail();
    })
  );
  document.addEventListener("click", (event) => {
    const runButton = event.target.closest("[data-open-run]");
    if (runButton) {
      const runId = runButton.dataset.openRun;
      if (runId) openRun(runId);
      return;
    }
    const approve = event.target.closest("[data-memory-approve]");
    if (approve) {
      approveMemory(approve.dataset.memoryApprove, true);
      return;
    }
    const reject = event.target.closest("[data-memory-reject]");
    if (reject) approveMemory(reject.dataset.memoryReject, false);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") $("#drawer").classList.remove("open");
  });
}

async function init() {
  bind();
  await Promise.all([loadHealth(), loadCatalog(), loadRuns(), loadMemory()]);
  const hash = location.hash.replace("#", "");
  if (["dashboard", "run", "runs", "memory"].includes(hash)) setTab(hash, false);
  setInterval(loadHealth, 15000);
}

init();
