# 项目简介 / 技术栈 / 职责 / 亮点

> 可直接用于简历、GitHub About、面试自我介绍。数字都来自本仓库的可复现实验；边界也写清楚，避免把“链路验证”讲成“模型能力”。

## 项目简介

**pi-harness** 是面向 AI Agent 的运行时 Harness：在 pi coding agent 外层提供 MCP 工具网关、步骤级评测、策略回放、长期记忆和 Web 对话/调试台，让 Agent 的每一步**可观测、可管控、可调优**。

项目包含 7 条正常任务、13 条攻击集、3 轮策略迭代，以及 OpenViking 记忆同步闭环。

## 技术栈

Python、pi coding agent、LiteLLM、MCP / JSON-RPC、Docker、JSONL、OpenViking 0.5.2.1、DeepSeek、阿里百炼 `text-embedding-v3`、OTLP-style 导出、原生 HTML/CSS/JS。

## 个人职责

- **pi 运行时接入与工具治理**：以 `--no-builtin-tools` + Harness MCP Gateway 统一 `fs_read/fs_write/fs_list/shell_exec/mem_*`，落地路径穿越、symlink、命令注入、secret、prompt injection 等护栏，并做 `rule_id + policy_version` 审计。
- **步骤级评测**：把 pi JSON 事件解析为 StepEvent，输出 verdict、归因、watchdog、context 指标；实现 FastPass / SlowPass / BudgetBlocked / CapabilityBlocked / ProviderBlocked 分类与逐任务报告。
- **策略回放与 RSI 闭环**：p1→p2→p3 三轮策略迭代，离线 replay + 多次 live 复现；实现 prompt A/B 与回滚，避免“凭感觉调 prompt”。
- **长期记忆**：写策略、quarantine/approve/reject、失败 trace 抽取 lesson、repo scope 隔离；接入 OpenViking `content/write` + approve 同步 + repo URI 映射。
- **Web 用户端 + 调试台**：多轮 agent 对话、工具调用可见、记忆审核、run/audit/trace 查看；支持可选 Bearer token。

## 技术亮点

- **攻击集 ASR 0/13**：11 blocked + 2 refused，正常任务 7/7 pass；其中 2 条 refused 是模型自身拒绝，不冒充 guard 拦截。
- **策略回放**：p2 在 p1 旧轨迹上解开 1 个 over-block，attacks 上 0 个 block→allow；p2 live 复现 3 次 **18/18 pass**；benign over-block **2/29（6.9%）**。
- **Prompt 调优**：Prompt C 在长任务上 **tokens −53.5%**（35,490→16,489）且 pass；Prompt B tokens +37%、pass 不变，被回滚。
- **长期记忆**：9 条单测；A013 记忆投毒被 block/refused；OpenViking 真实 write/read/search 通过（score 0.918），`repo:demo` → `repo-demo` URI。
- **Context**：3.5k 窗口压力测试触发 2 次 compaction，`utilization 1.045`；OTel 导出 31 spans。

## 简历精简版（3 条）

- 给 pi 构建运行时 Harness：MCP 工具网关 + StepEvent + verdict/归因 + 策略回放，支持 Docker 隔离与 OpenViking 记忆。
- 13 条攻击集 **ASR 0/13**（11 blocked + 2 refused），正常任务 **7/7 pass**；p2 策略复现 **18/18**，benign over-block **2/29**。
- Prompt C 长任务 **tokens −53.5%**；长期记忆接入 OpenViking 真实 write/read/search，repo scope 映射通过。

## 面试口径（主动说）

- `ASR 0/13` 不等于“13 条全是 guard 拦的”：11 blocked + 2 refused，refused 是模型对齐，不是 Harness 的功劳。
- `7/7` 是 **MCP-only、小样本**的链路验证，不代表模型能力。
- replay 只覆盖 **p1 旧轨迹**；新策略可能诱导新路径，由 p2 三次 live 覆盖。
- compaction 的 `utilization 1.045` 是 **3.5k 窗口压力测试**，不是 131k 生产分布。
- OpenViking 当前 `auth_mode=dev`，**没有开鉴权**，只监听本机；多租户鉴权未做。
- 9 条 memory 单测不是全量覆盖；reject 不删远端。
