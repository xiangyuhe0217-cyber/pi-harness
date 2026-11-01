# 决策记录（ADR）

## ADR-001：pi 作为底座，不重写 Agent

- **背景**：pi 已有 loop、context/compaction、tools/skills、sessions、durable。
- **决策**：Harness 不实现这些；只做观测、策略、评测、调优。
- **后果**：少写一半代码；代价是依赖 pi 的稳定性和事件格式。
- **替代**：自研 MiniAgent（已放弃，用户选择 pi）。

## ADR-002：LiteLLM 作为模型网关

- **背景**：需要 OpenAI 兼容、虚拟 key、预算、日志。
- **决策**：pi 的 custom provider 指向 LiteLLM；Harness 以 callback/guardrail 接入。
- **后果**：复用成熟链路；代价是 callback 能力受 LiteLLM 限制（W0 验证）。
- **替代**：自写 thin proxy（放弃，用户选择复用）。

## ADR-003：plain Docker + internal network

- **背景**：pi 官方明确不 sandbox 工具调用。
- **决策**：pi 跑在 Docker；workspace 单独挂载；pi 与 LiteLLM 在 internal network；LiteLLM 双网卡出网。
- **后果**：进程/文件/网络隔离；代价是 Windows 需要 Docker Desktop/WSL2。
- **替代**：OpenShell / Gondolin（更强，后置）。

## ADR-004：MCP-only 作为主路径，extension hook 仅增强

- **背景**：MCP Gateway 只能管走 MCP 的工具；pi 内置工具可能绕过。
- **已确认（2026-10-31，pi 1.4.0）**：pi 提供 `--no-builtin-tools`、`--tools`、`--exclude-tools`，可以禁用内置工具、只保留 MCP/extension 工具。
- **决策**：pi 以 `--no-builtin-tools` 启动，所有工具走 Harness MCP Gateway；inline 拦截由网关保证。extension hook 只用于增强（自定义压缩、额外审计），不作为主路径。
- **后果**：工具策略是确定性的；代价是必须把 fs/shell 等能力都做成 MCP 工具。
- **替代**：容器 + 事后审计（仅在 MCP-only 不可用时）。

## ADR-005：Checkpoint 复用 pi，Harness 只存元数据

- **背景**：pi 有 session 和 durable。
- **决策**：对话状态归 pi；Harness 存 `run_state.json`（task、policy hash、approvals、workspace hash、last step）。
- **后果**：resume 需要两边对齐；代价是多一层校验。
- **替代**：Harness 全量自研（放弃）。

## ADR-006：先策略层回放，再 prompt 真跑

- **背景**：策略层确定性可回放；prompt 改动不可回放。
- **决策**：Phase 1 只调策略；Phase 2 才动 prompt，且必须 held-out 真跑。
- **后果**：避免“回放万能”的伪论证；代价是 Phase 2 成本更高。
- **替代**：一步到位（放弃）。

## ADR-007：旧项目在 W0 通过后删除

- **背景**：`servicedesk-agent` 是错误场景（CRUD）。
- **决策**：W0 通过后删除；新项目 `harness/`。
- **后果**：避免仓库噪音；代价是丢失参考代码（已无价值）。

## ADR-008：不做 UI（已被 ADR-009 取代）

- **背景**：时间有限，评测/调优是核心。
- **决策（当时）**：CLI + Markdown 报告；UI 后置。
- **后果**：交付更快；代价是演示观感一般。
- **2026-11-01 更新**：用户明确“CLI 操作不习惯”，新增 ADR-009；本条废弃。

## ADR-009：本地 Web Console（替代 ADR-008）

- **背景**：演示和日常操作需要跑任务、看 trace、审核记忆，CLI 门槛高。
- **决策**：
  - Python 标准库 HTTP server + 原生 HTML/CSS/JS，不引入 Node/TS；
  - 本地优先，默认 bind `0.0.0.0:8765`；可选 `HARNESS_WEB_TOKEN`，默认本机单用户；
  - 运行通过后台线程 + job 轮询，避免请求阻塞；
  - 记忆审核（quarantined → approve/reject）、失败 trace 抽 lesson、scope 过滤都进 UI；
  - OpenViking 支持健康检查、检索和 `content/write`；agent 记忆先由本地 `MemoryStore` 门控，approve 后同步写。
- **后果**：演示和操作成本降低；代价是多一个进程、默认无登录、OpenViking `auth_mode=dev` 未开鉴权；真实 OpenViking 已端到端验证。
- **替代**：继续纯 CLI（放弃，用户明确要求页面）。

