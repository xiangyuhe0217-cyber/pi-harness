# 面试与简历材料

## 一句话

给 pi 套一层运行时 Harness：**LLM 代理 + MCP 工具网关 + StepEvent + verdict/归因 + 策略回放**，让 Agent 的每一步可观测、可管控、可调优。

## 三个数字

- 正常任务：**7/7 pass**（MCP-only，Fast 5 / Slow 2）
- 攻击集：**ASR 0/13**（11 blocked + 2 refused）
- 策略 p2 复现 3 次：**18/18 pass**，attacks 无 block→allow 回退

## 架构

```
pi (Docker, internal network)
 ├─ custom provider → LiteLLM → 模型
 ├─ MCP tools → Harness Gateway（路径/命令/注入/secret）
 └─ JSON events → Collector → StepEvent
                         └─ Verdict → 归因 → Replay → Report
```

## 面试问答

**Q1：为什么不直接做一个 Agent，而做 Harness？**
A：pi 已经有 loop、context/compaction、tools/skills、sessions。我不重写这些；Harness 补的是 pi 没有的：沙箱、策略/护栏、逐步 verdict、评测、回放调优。价值在“管得住 + 变得好”，不是“又一个 Agent”。

**Q2：工具调用失败怎么处理？**
A：分三类：策略拦截（`blocked`，带 rule id）、执行错误（`error`，重试/换工具）、无效重复（`wasteful`/`loop`）。所有拦截带 rule + policy 版本，能归因、能回放。

**Q3：上下文和记忆怎么管？**
A：上下文归 pi：sessions + compaction（阈值、摘要、`CompactionEntry`）。Harness 只观测 `max_input`、`utilization`、`compaction_count`，不重写压缩。长期记忆是独立层：`memory/store.json` + audit，状态 `active/quarantined/expired/blocked`；agent 写入默认隔离，`without approval` / injection 直接 block，冲突 quarantine，TTL 过期。A013 记忆投毒被 block/refused。OpenViking 0.5.2.1 已接入 content/write + approve 同步 + repo URI，真实 read/search 通过。

**Q4：怎么评测一个会自我修改的系统？**
A：三层：StepEvent → verdict；任务级测试；攻击集 ASR。策略改动先在录制轨迹上 replay（不调模型），再看 live A/B；prompt/模型改动只能 live。用 held-out 攻击 + 多次复现 + 回滚。

**Q5：沙箱怎么做的？**
A：两层：pi 在 Docker 里，非 root、`--network none`、资源限制；工具层是 MCP Gateway，做 realpath、路径/命令/大小/注入/secret 检查。pi 官方明确不 sandbox 工具调用，这是 Harness 的第一价值。

**Q6：RSI 怎么做？**
A：策略层可回放：p1→p2 解开 1 个 over-block，attacks 无回退；p3 加 `pip` 禁用无回归。Prompt 层用 live A/B：B 版 tokens +37%、pass 不变，直接回滚。**不是每轮都涨，负结果也要记录。**

**Q7：你最大的坑？**
A：三个：
1. 相对路径把 workspace 拼成双层，benign 直接 0/6；
2. `python3 script.py` 绕过写入大小限制，补了 `exec.script_execution`；
3. replay 把 `codemode`/MCP 外层工具名、内容型 guard、非策略 block 都算错，逐个修。

## 简历 bullet（可直接改）

- 为 pi 构建运行时 Harness：LLM 代理 + MCP 工具网关 + StepEvent 采集 + verdict/归因，支持 `--no-builtin-tools` 全工具治理。
- 设计 13 条攻击集（路径穿越、symlink 逃逸、命令注入、prompt injection、secret 外泄、记忆投毒等），**ASR 0/13**（11 blocked + 2 refused）；正常任务 **7/7 pass**。
- 实现策略版本化与离线 replay：p2 解开 1 个 over-block，attacks 无 block→allow 回退；p2 复现 3 次 18/18 pass。
- 实现 checkpoint/resume：pi session + `run_state.json`，被 kill 的任务 resume 后通过。
- 建立逐任务报告：verdict、归因、watchdog、context 指标 + 学习/面试笔记。

## 边界（面试官会追问）

- 7/7 是链路验证，不是模型能力；换难题/换模型会掉。
- replay 只覆盖策略层；prompt/模型改动必须 live。
- 上下文利用率还低，compaction 未真正触发；需要小窗口模型或长会话。
- 预算还没接 LiteLLM 实际 token/成本；当前用 pi usage。
- 长期记忆是文件 + 关键词检索，agent 写入默认隔离；OpenViking 已真实跑通（127.0.0.1:1933，dev 无鉴权），多租户鉴权未做。
