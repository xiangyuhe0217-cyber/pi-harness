# 实施计划

> 前置：W0 通过后才写业务代码。W0 之外，代码由我写；pi / Docker / API Key 由你在本机跑。

## 阶段

| 阶段 | 时间 | 交付 | 验收 |
|---|---|---|---|
| W0 | 2–3 天 | 能力验证清单、能力矩阵、3 个决策 | 全链路走通；决策冻结 |
| W1 | 1 周 | Docker + LiteLLM + Collector + StepEvent + 10 任务 | 一条任务全链路 trace；10 任务 baseline |
| W2 | 1 周 | MCP Gateway + policy/guards + 12 攻击 + skill registry | ASR 基线；拦截带 rule_id |
| W3 | 1 周 | verdict + 归因 + watchdog + context metrics + report | 报告出 ASR/FPR/pass/p95 |
| W4 | 1 周 | checkpoint/resume + policy replay 调优 | 1 轮策略调优；resume 成功 |
| W5 | 1 周 | prompt live 调优 + 3 轮 + demo + 文档 | 前后对比表；pi 演示 |

## W1 详细拆分

| Day | 任务 | 产出 |
|---|---|---|
| 1 | 仓库骨架、StepEvent schema、Policy schema | `src/harness/...`、`policies/p1.yaml` |
| 2 | Docker Compose：pi + LiteLLM + internal network | `docker-compose.yml` 可起 |
| 3 | LiteLLM callback：记录 model_call、写 events.jsonl | 一次调用一条事件 |
| 4 | Collector：解析 pi JSON 事件 + session 文件 | tool_call/tool_result 进 events |
| 5 | 10 条任务 + baseline 报告 | `runs/r-001/` + `report.md` |

## W2 详细拆分

| Day | 任务 | 产出 |
|---|---|---|
| 1 | MCP Gateway：fs.read / fs.write / shell.exec | 工具可被 pi 调用 |
| 2 | 路径/命令/secret guard + policy 引擎 | blocked 事件带 rule_id |
| 3 | 12 条攻击任务 | `attacks/A001..A012.yaml` |
| 4 | 跑攻击 baseline，统计 ASR | `report.md` |
| 5 | skill registry 镜像 | `skill_manifest.json` |

## W3 详细拆分

| Day | 任务 | 产出 |
|---|---|---|
| 1 | Verdict 规则引擎 | step verdict |
| 2 | 归因 taxonomy + slice | `attribution.md` |
| 3 | Loop watchdog | `loop_detected` 事件 |
| 4 | Context metrics（compaction 前后） | `context.md` |
| 5 | Report 汇总 | `report.md` |

## W4 详细拆分

| Day | 任务 | 产出 |
|---|---|---|
| 1 | RunState + checkpoint | `run_state.json` |
| 2 | resume 编排 | `harness resume` |
| 3 | Policy replay 引擎 | 录制轨迹重算 |
| 4 | 提案 + 门控 | `tune/` |
| 5 | 1 轮策略调优 | 对比表 |

## W5 详细拆分

| Day | 任务 | 产出 |
|---|---|---|
| 1 | prompt 变体 + held-out | `variants/` |
| 2 | live eval | 对比 |
| 3 | 2 轮追加调优 | 3 轮表 |
| 4 | demo 脚本 + 录屏 | `demo.md` |
| 5 | README / 架构文 / 简历 bullet | 文档 |

## 关键依赖

- `pi` 可安装、可配置 custom provider。
- LiteLLM 可跑、可写 callback。
- Docker Desktop 可用。
- 一个模型 API Key（DeepSeek/Qwen/OpenAI 均可）。
