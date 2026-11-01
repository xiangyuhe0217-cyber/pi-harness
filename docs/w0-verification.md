# W0 验证清单（pi 能力实测）

> 目的：在写任何业务代码前，确认 pi 的真实能力，填完能力矩阵，锁定 3 个设计决策。
> 方式：每项给出“怎么测 / 期望 / 不通过时的退路”。命令以 `pi --help` 和官方文档为准。
>
> **2026-10-31 实测环境**：WSL Ubuntu（pi 1.4.0 / Node 22.22.1）、Docker Desktop 29.4.3、Python 3.14.4（无 pip，venv 可用）。

## A. 环境

- [x] **A1** `node --version`、`pi --version` 能跑通。
  - **已确认**：WSL Ubuntu，pi 1.4.0，Node v22.22.1；pi 在 `~/.pi/agent/bin/pi`（`.bashrc` 已加 PATH）。
- [x] **A2** `pi --help` 记录关键 flag。
  - **已确认**：`--mode json|rpc`、`-p/--print`、`--continue/-c`、`--resume/-r`、`--session`、`--session-dir`、`--model`、`--provider`、`--no-builtin-tools`、`--tools`、`--exclude-tools`、`--skill`、`--extension`、`--no-mcp`。
- [ ] **A3** Docker Desktop 可用：`docker run --rm hello-world`。
  - 期望：后续沙箱依赖它。

## B. 模型链路（LiteLLM）

- [x] **B1** 启动 LiteLLM Proxy，配置一个模型；`curl` 调 `/v1/chat/completions` 成功。
  - **已确认（2026-10-31）**：WSL 本地 LiteLLM（无 master key，危险模式），`/v1/models` 200，返回 `deepseek-chat`；`POST /v1/chat/completions` 200。
- [x] **B2** 配置 pi 的 custom provider 指向 LiteLLM（OpenAI 兼容 `/v1`）。
  - **已确认**：`pi --list-models` 出现 `litellm/deepseek-chat`；`pi --provider litellm --model deepseek-chat -p ...` 成功。
- [x] **B3** 记录 pi 一次调用在 LiteLLM 里的字段：model、messages、usage、latency、tool_calls。
  - **已确认**：pi JSON 事件 `message_end` 含 `usage`（input/output/cacheRead/totalTokens/cost）与 `durationMs`；LiteLLM 日志有 200。

## C. 事件、session、compaction

- [x] **C1** 用 JSON 事件流跑一个任务（按 A2 的实际 flag）。
  - **已确认**：`--mode json` 输出 JSONL；事件类型 `session / agent_start / turn_start / message_start / message_update / message_end / tool_execution_start / tool_execution_update / tool_execution_end / turn_end / agent_end / agent_settled`。
  - 工具事件含 `toolCallId / toolName / args / result`，足够还原每一步。
- [x] **C2** 找到 session 文件（`~/.pi/agent/sessions/...`），记录字段。
  - **已确认**：JSONL，首行 `session`，含 `model_change / thinking_level_change / message` 等；`--continue` 实测第二次回答 `42`，resume 成功。
- [x] **C3** 强制 compaction：把 context window 调小，或执行 `/compact`。
  - **已确认**：session 里有 `type:"compaction"`，`tokensBefore: 56554`、`firstKeptEntryId`、结构化 `summary`（Goal/Constraints/Progress/Next Steps）。
- [ ] **C4**（可选）`/tree` 触发 branch summary，记录 `BranchSummaryEntry`。

## D. 工具、Skill、MCP、Hook

- [x] **D1** 配一个最小 MCP server，确认 pi 能列出并调用它的工具。
  - **已确认**：项目 `.pi/mcp.json` + `--approve` + `--no-builtin-tools`；MCP 工具名 `mcp__fs__*`，`list_directory` 返回 `.pi` / `hello.txt`，最终 DONE。
- [x] **D2** 创建一个 skill，确认 pi 能发现并使用。
  - **已确认**：`--skill .../harness-skill`；system prompt 出现 `harness-skill`，模型回答 `BANANA`。
- [x] **D3** 写一个最小 extension，确认可用 hook 列表：是否有 tool 执行前/后的 hook？能否 block / 改写？
  - **已确认**：`pi.on("tool_call", ...)` 可返回 `{block:true, reason}`；`tool_execution_end` 带 `isError:true`，模型能看到 reason。
  - 结论：extension hook 可做 inline block；仍以 MCP-only 为主路径。
- [x] **D4** pi 的内置工具能否禁用或替换？
  - **已确认（2026-10-31，pi 1.4.0）**：`--no-builtin-tools` / `--tools` / `--exclude-tools` 可用；MCP-only 可行。
  - 结论：主路径改为 `--no-builtin-tools`，所有工具走 Harness MCP Gateway。

## E. 沙箱与网络

- [x] **E1** 按官方 `Dockerfile.pi` 构建镜像；`docker run --rm -it -v "$PWD:/workspace" pi-sandbox`。
  - **已确认**：镜像基于 `docker.m.daocloud.io/library/node:24-bookworm-slim`（国内镜像）；`pi --version` = 1.4.0；workspace 挂载可读写。
- [x] **E2** 网络隔离：pi 容器与 LiteLLM 放同一 internal network；pi 能访问 LiteLLM，但不能访问公网。
  - **已确认**：`--network none` 下 node fetch 返回 `NO_NET`；容器内 pi 正常启动（`--version`）。
  - 待 W1：internal network + LiteLLM 的连通性。
- [x] **E3** 资源限制：`--memory`、`--cpus`、`--pids-limit`、非 root。
  - **已确认**：`--memory 256m --cpus 1 --pids-limit 64` 可运行；镜像 `USER node`，`id -u` = 1000。

## F. 长任务与 Checkpoint

- [ ] **F1** 运行中 kill pi，`--continue` / `--resume` 恢复。
  - 记录：session 恢复点、丢失的步骤。
- [ ] **F2** 查 Pi Durable 的实际能力（崩溃恢复 / 断点续跑）。
  - 期望：能复用就不自研；不能则 harness 加 run metadata + workspace diff。
- [ ] **F3** 跑完后做 workspace diff；记录 hash 与变更文件。

## G. LiteLLM 回调与策略

- [x] **G1** 写一个 LiteLLM custom callback / guardrail：pre-call 能拒绝请求吗？post-call 能记录吗？能改写响应吗？
  - **已确认**：第二实例 4010，pre-call 抛异常 → 500 `blocked by harness W0 callback`；post-call 写入 `events.jsonl`。改写未测。
- [~] **G2** 虚拟 key / 预算：per-run key + 预算限制生效。
  - **结论：暂缓**。master key 已验证；虚拟 key/预算需要 PostgreSQL，W0 不做；预算放 Harness 层。
- [x] **G3** 日志导出：请求/响应/usage/latency 可被 collector 读取。
  - **已确认**：callback 写 `events.jsonl`；pi 事件里有 usage/cost/durationMs。

## H. 结论（填完才能进 W1）

### H1. 能力矩阵

| 能力 | 结论（✅/⚠️/❌） | 证据 |
|---|---|---|
| custom provider → LiteLLM | ✅ | `pi --list-models` 出现 `litellm/deepseek-chat` |
| JSON 事件流可还原 step | ✅ | message / tool_execution 事件 |
| session 可 resume | ✅ | `--continue` 第二次回答 `42` |
| compaction 可观测 | ✅ | session `compaction`，`tokensBefore: 56554` |
| MCP 工具可接入 | ✅ | `mcp__fs__list_directory` 返回 `.pi` / `hello.txt` |
| skill 可发现 | ✅ | system 出现 `harness-skill`；回答 `BANANA` |
| extension 可 block tool | ✅ | `tool_call` 返回 block，`isError: true` |
| 内置工具可禁用 | ✅ | `--no-builtin-tools` |
| Docker + internal network | ✅ | pi 1.4.0 容器、`NO_NET`、uid=1000；internal network 待 W1 |
| Pi Durable 可用 | ⏳ | F 待测 |
| LiteLLM callback 可拦截 | ✅ | 4010 实例 pre-call 返回 500 |
| LiteLLM 可改写响应 | ❓ | 未测；按事后脱敏设计 |

### H2. 三个决策

| 决策 | 选项 | 选择 |
|---|---|---|
| 工具拦截路径 | A. extension hook inline block；B. MCP-only + 容器 + 事后审计 | **B 主路径；extension hook 已验证，可做补充** |
| 沙箱方式 | A. plain Docker；B. OpenShell / Gondolin | **A plain Docker** |
| Checkpoint 范围 | A. pi session/durable + harness metadata；B. harness 全量自研 | **A pi + harness metadata** |

### H3. 通过标准

- 至少一条任务能从 pi → LiteLLM → 模型 → 工具 → 事件 → session 全链路走通。
- 至少一条攻击能被容器或策略拦截（或明确记录为“只能事后发现”）。
- 三个决策有明确结论，写进 `docs/decisions.md`。
