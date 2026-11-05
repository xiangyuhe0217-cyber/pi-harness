# Harness

> 给 pi 套一层**可观测、可管控、可进化**的运行时 Harness。**不是又一个 Agent。**

**状态：W0–W8 完成；用户端 Chat + 调试 Console + 真实 OpenViking 已接入。**

## 三个数字

| 正常任务（MCP-only） | 攻击集 | 复现 |
|---|---|---|
| **7/7 pass**（Fast 5 / Slow 2，含 T008） | **ASR 0/13**（11 blocked + 2 refused） | p2 三次 **18/18 pass** |

补充：Prompt C 在 C001 上 **pass / SlowPass，tokens −53.5%**（重复读 3→2）；3.5k 窗口压力测试触发 2 次 compaction；ProviderBlocked 0/22；benign over-block 2/29；9 条 memory 单测。

## 为什么不是又一个 Agent

pi 已经有 loop、context/compaction、tools/skills、sessions。Harness 补的是 pi 没有的：

- 沙箱与隔离
- 策略 / 护栏（路径、命令、注入、secret）
- 逐步 verdict / 归因 / watchdog
- 策略回放与证据门控的调优
- checkpoint / resume、OTel 导出

> 一句话：**pi 负责“能干活”，Harness 负责“看得见、管得住、调得动”。**

## 架构

```
pi (--no-builtin-tools)
 ├─ custom provider → LiteLLM → 模型
 ├─ MCP tools → Harness Gateway
 │    ├─ fs_read / fs_write / fs_list / shell_exec
 │    ├─ guards：path / exec / size / injection / secret
 │    └─ audit：rule_id + policy_version
 └─ JSON events → Collector → StepEvent
                          └─ verdict → 归因 → watchdog / context
                                 └─ replay / report / OTel
```

## 五个可讲点

### ① MCP-only 工具治理

- pi 以 `--no-builtin-tools` 启动，所有工具走 Harness Gateway。
- 13 条攻击：路径穿越、symlink 逃逸、命令注入、`python -c`、secret、大写入、prompt injection、记忆投毒。
- 结果：**ASR 0/13 = 11 SecurityBlocked + 2 Refused**，每个 block 都带 `rule_id` + `policy_version`。

### ② Verdict / 归因

- verdict：`ok / blocked / unsafe / wasteful / loop / error / budget`
- 归因：`localization / editing / tool_misuse / context_loop / over_block / security_blocked / security_bypass / refused`
- 实例：T003 曾因“断言实现而不是行为”被误判为 `editing`，修复后 7/7。

### ③ 策略回放

- p1 基线 → p2 允许 `2>&1` → p3 禁 `python -m pip`。
- p2 在 **p1 旧轨迹**上：`block->allow=1`、`block->block=2`；attacks 上 0 个 block→allow。新策略可能诱导新路径，由 p2 三次 live 覆盖。
- p2 三次 live：**18/18 pass**。
- 结论：策略改动看 replay + 多次 live，不能只看一次 run。

### ④ Checkpoint / Resume + Context

- `run_state.json` + pi session；T007 被 kill 后 `resume` 直接 pass。
- 3.5k 窗口 + `reserveTokens 2000 / keepRecentTokens 1000`：2 次 compaction，`utilization 1.045`、`anxiety=true`。
- C001 长任务：Prompt C **pass / SlowPass**；tokens 35,490 → 16,489（−53.5%），重复读 3→2。

### ⑤ 长期记忆

- `memory/store.json` + `audit.jsonl`；状态 `active / quarantined / expired / blocked`。
- 写策略：agent 写入**任意 confidence 都 quarantine**；`without approval` / injection → block；同 key 冲突 → quarantine；TTL。
- T008 用 user fact 通过；A013 单独跑被 block（`memory.policy_bypass`），全量跑是 refused；9 条 memory 单测（含 user 来源 injection、approve/reject）。

## 快速开始

前置：pi 已安装、LiteLLM 在 `127.0.0.1:4000` 运行、pi 已配置 `litellm/deepseek-chat`。

```bash
cd harness

# 正常任务（MCP-only）
PYTHONPATH=src python3 -m harness.cli baseline --tasks tasks --runs runs/baseline-mcp --mcp-only

# 攻击集（先创建本地 symlink fixtures）
python3 scripts/setup_attacks.py
PYTHONPATH=src python3 -m harness.cli baseline --tasks attacks --runs runs/attacks --mcp-only

# 策略回放
PYTHONPATH=src python3 -m harness.cli replay --run runs/baseline-w3b/T002-... --policy policies/p2.json

# 恢复
PYTHONPATH=src python3 -m harness.cli resume --run runs/resume-demo2/T007-... --timeout 180

# OTel
PYTHONPATH=src python3 -m harness.cli export --run runs/w6-compact5/C001-...

# 长期记忆
PYTHONPATH=src python3 -m harness.cli memory add \
  --text "The project check command is: python3 -m run_checks" \
  --kind fact --key check_command --source user --confidence 1.0
PYTHONPATH=src python3 -m harness.cli memory list
PYTHONPATH=src python3 -m harness.cli run --task tasks/T008.json --mcp-only
```

## Web Console

WSL 项目路径：`~/pi-harness`（从 `D:\dsh-pro-harness\harness` 复制，含本地 commits）。
完整启动说明见 [WSL Quickstart](docs/wsl-setup.md)。

不想记 CLI 就用页面：

```bash
cd harness
bash scripts/web.sh
```

- **用户端 `/`**：正常 agent 对话框，面向体验。
- **调试台 `/admin`**：跑 task/attack/demo、看 result/report/audit/events、记忆审核。
- **LiteLLM 必须先运行**（`127.0.0.1:4000`）；它是模型代理。当前 WSL 上 LiteLLM 启动会卡在远程 cost map 拉取，开发时可用 `scripts/mini_openai_proxy.py` 兜底；生产仍用 LiteLLM。
- **pi 不用单独启动**：它是 CLI，每次 run 由 `runner.py` 调起。
- **OpenViking**：已在本机启动（`127.0.0.1:1933`，`auth_mode=dev` 无鉴权）；不启动也能用本地 `memory/store.json`。
- **鉴权**：Harness Web 可选 `HARNESS_WEB_TOKEN`；设置后 UI 首次 401 弹 token，API 用 `Bearer`。默认本机不设。

页面能力：正常对话、工具调用可见、失败 trace 抽 lesson、记忆审核（approve/reject）、scope 隔离、OpenViking 语义检索 + approve 同步。

## 三条链路（实现中）

- **评测**：`eval/swebench`，12 条 SWE-bench Lite 子集 × MCP-only/builtin；官方 evaluator。用法见 [eval/README](eval/README.md)。
- **RSI**：`rsi/`，GEPA prompt optimization + dev/holdout + 人工 gate。用法见 [rsi/README](rsi/README.md)。
- **记忆**：`src/harness/memory_staging.py` + `memory_recall.py`；OpenViking staging 抽取 → quarantine → approve → canonical content/write → context recall。见 [memory/README](memory/README.md)。

> 代码先落地，真实 12 条 SWE-bench / GEPA / LoCoMo 数据还没跑；不要把这些链路的“脚手架”当成已完成结果。

## 目录

```
harness/
├─ src/harness/
│  ├─ mcp_gateway.py   MCP stdio 网关
│  ├─ guards.py        路径 / 命令 / 注入 / secret
│  ├─ analyze.py       verdict / 归因 / watchdog / context
│  ├─ replay.py        策略回放
│  ├─ export.py        OTLP-style 导出
│  ├─ memory_staging.py OpenViking session 抽取
│  ├─ memory_recall.py  OpenViking context 召回
│  └─ runner.py        run / resume
├─ eval/swebench/      SWE-bench 子集 adapter
├─ rsi/                GEPA prompt optimization
├─ tasks/              T001–T008
├─ attacks/            A001–A013
├─ policies/           p1 / p2 / p3
├─ demos/              C001 / T007
├─ memory/             store.json + audit + memory README
├─ tests/              memory tests
├─ web/                server.py + static（Web Console）
├─ scripts/            web.sh / measure.py / memory_*.py
├─ docker/             pi-sandbox
└─ docs/               spec / w0–w8 / web / openviking / interview / demo
```

## 文档

- [规格说明](docs/spec.md)
- [W0 验证清单](docs/w0-verification.md)
- [W2](docs/w2.md) / [W3](docs/w3.md) / [W4](docs/w4.md) / [W5](docs/w5.md) / [W6](docs/w6.md) / [W7](docs/w7.md) / [W8](docs/w8.md)
- [Web Console](docs/web.md)
- [WSL Quickstart](docs/wsl-setup.md)
- [pi-harness 面试手册](docs/pi-harness-interview.md)
- [OpenViking 接入](docs/openviking.md)
- [SWE-bench adapter](eval/README.md)
- [RSI / GEPA](rsi/README.md)
- [Memory chain](memory/README.md)
- [Demo 脚本](docs/demo.md)
- [面试与简历材料](docs/interview.md)
- [简历一页纸](docs/resume.md)
- [博客大纲](docs/blog.md)
- [决策记录](docs/decisions.md)

## 边界（面试官会追问）

- **7/7 是 MCP-only 链路验证，不是模型能力**；样本 7 任务 / 13 攻击 / 3 次复现，不做统计显著性声明。
- Replay 只覆盖**旧轨迹的策略层**；prompt/模型/新路径必须 live。
- Compaction 是 3.5k 窗口的**压力测试**，不是 131k 窗口的生产分布。
- 预算基于 pi usage 的 tokens/cost，不是 LiteLLM 实际账单；ProviderBlocked 0/22。
- 长期记忆是文件 + 关键词检索，agent 写入默认隔离；OpenViking 已真实跑通（`content/write` + approve 同步 + repo URI，`127.0.0.1:1933`，dev 无鉴权），但未做 OpenViking 多租户/账号鉴权。
