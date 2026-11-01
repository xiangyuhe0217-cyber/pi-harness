# 简历一页纸（2028 届 · 日常实习）

> 按一页纸写；数字都能被追问。项目主语是 Harness，不是“评测平台”。

## 项目：Agent Harness（个人项目｜2026.10–2026.11）

**一句话**：给 pi 套一层运行时 Harness：MCP 工具网关 + StepEvent + verdict/归因 + 策略回放，让 Agent 可观测、可管控、可调优。

- 给 pi 接入 `--no-builtin-tools` + Harness MCP Gateway，统一治理 `fs_read/fs_write/fs_list/shell_exec`；实现路径穿越、symlink、命令注入、`python -c`、secret、大写入等规则。
- 构建 13 条攻击集；正常任务 **7/7 pass**（Fast 5 / Slow 2），攻击 **ASR 0/13**（11 blocked + 2 refused）；每个 block 带 `rule_id` + `policy_version`。
- 实现 StepEvent → verdict/归因/watchdog/context：区分 localization / editing / tool_misuse / over_block / security_blocked；逐任务报告含「学习与面试」。
- 实现策略版本化与离线 replay：p2 解开 1 个 `2>&1` over-block，attacks 上 0 个 block→allow；p2 三次 live **18/18 pass**。
- 实现 checkpoint/resume：pi session + `run_state.json`，被 kill 的任务 resume 后 pass。
- 实现长期记忆层：文件存储 + 写策略（agent 写入隔离、冲突/注入/TTL），A013 记忆投毒被 block/refused；T008 用记忆命令通过。
- 做 prompt A/B：B 版 tokens +37%、pass 不变 → 回滚；C 版在长任务上 tokens **−53.5%**、重复读 3→2。
- 接入 OpenViking 0.5.2.1：`content/write` + approve 同步 + repo scope→URI 映射，真实服务 read/search 验证；Harness Web 支持可选 Bearer token。
- 用小窗口（3.5k）触发 2 次 compaction，`utilization 1.045`、`anxiety=true`；OTel 导出 31 spans。

## 技能

- 语言：Python / Java
- Agent：Function Calling、MCP、ReAct、上下文工程、工具治理
- 评测：任务集、verdict、归因、watchdog、离线 replay、A/B
- 工程：FastAPI（可写）、JSONL/SQLite、Docker、GitHub Actions、OTel

## 面试 3 分钟讲法

1. **问题**：Agent 的失败不可解释——只有 pass/fail，没有“为什么错、下一步改什么”。
2. **方案**：Harness 在 pi 外面加一层：MCP-only 工具网关 + StepEvent + verdict/归因 + replay。
3. **证据**：13 攻击 ASR 0/13（11 blocked +2 refused）；p2 replay 解开 1 个 over-block、attacks 无回退；T007 kill 后 resume pass；Prompt C −53.5% tokens；OpenViking 真实写入/检索通过。
4. **边界**：7/7 是 MCP-only 链路验证；replay 只覆盖策略层；compaction 是小窗口模拟；OpenViking 是 dev 无鉴权。

## 边界（主动说）

- 不是又一个 Agent：loop/context/tools 都是 pi 的。
- 不是通用评测平台：只做 step verdict + 策略回放。
- 7/7 不代表模型能力；任务简单，换难题会掉。
- 长期记忆是文件 + 关键词检索，agent 写入隔离；OpenViking 已真实跑通（127.0.0.1:1933，dev 无鉴权），未做多租户鉴权。

## 可替换占位

- 姓名 / 学校 / GPA / GitHub / 博客
- Docker 镜像大小、p95、单任务成本（按真实跑出来填）
