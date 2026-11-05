# pi-harness 项目面试手册

> 目标：像 DoVideoAI 一样，先给一份“简历可写、面试可讲”的项目总结，再用面试官视角逐层拷打。
>
> 原则：**不把脚手架说成结果，不把 refused 说成 guard 拦截，不把局部闭环说成完整评测。**

---

# 一、简历版写法

## 项目简介

**pi-harness** 是面向 AI Agent 的运行时 Harness：在 pi coding agent 外层提供 MCP 工具网关、步骤级评测、策略回放、长期记忆和 Web 对话/调试台，让 Agent 的每一步**可观测、可管控、可调优**。项目包含 7 条正常任务、13 条攻击集、3 轮策略迭代，以及 OpenViking 记忆同步闭环。

## 技术栈

Python、pi coding agent、LiteLLM、MCP / JSON-RPC、Docker、JSONL、OpenViking 0.5.2.1、DeepSeek、阿里百炼 `text-embedding-v3`、OTLP-style 导出、原生 HTML/CSS/JS。

## 个人职责

- **pi 运行时接入与工具治理**：以 `--no-builtin-tools` + Harness MCP Gateway 统一 `fs_read/fs_write/fs_list/shell_exec/mem_*`，落地路径穿越、symlink、命令注入、secret、prompt injection 等护栏，并做 `rule_id + policy_version` 审计。
- **步骤级评测**：把 pi JSON 事件解析为 StepEvent，输出 verdict、归因、watchdog、context；实现 FastPass / SlowPass / BudgetBlocked / CapabilityBlocked / ProviderBlocked 分类与逐任务报告。
- **策略回放与 RSI 闭环**：p1→p2→p3 三轮策略迭代，离线 replay + 多次 live 复现；实现 prompt A/B 与回滚。
- **长期记忆**：写策略、quarantine/approve/reject、失败 trace 抽取 lesson、repo scope 隔离；接入 OpenViking `content/write` + approve 同步 + repo URI 映射。
- **Web 用户端 + 调试台**：多轮 agent 对话、工具调用可见、记忆审核、run/audit/trace 查看；支持可选 Bearer token。

## 技术亮点

- **13 条攻击集 ASR 0/13**：11 blocked + 2 refused；正常任务 **7/7 pass**。其中 2 条 refused 是模型自身拒绝，不冒充 guard 拦截。
- **策略回放**：p2 在 p1 旧轨迹上解开 1 个 over-block，attacks 上 0 个 block→allow；p2 live 复现 3 次 **18/18 pass**；benign over-block **2/29（6.9%）**。
- **Prompt 调优**：Prompt C 在长任务上 **tokens −53.5%**（35,490→16,489）且 pass；Prompt B tokens +37%、pass 不变，被回滚。
- **长期记忆**：14 条 memory 相关测试；A013 记忆投毒被 block/refused；OpenViking 真实 write/read/search 通过（score 0.918），`repo:demo` → `repo-demo` URI。
- **Context**：3.5k 窗口压力测试触发 2 次 compaction，`utilization 1.045`；OTel 导出 31 spans。

## 一句话

> 我没有让 Agent 更聪明；我让它每一步都能被看见、被管住、被调好。

---

# 二、1–2 分钟项目介绍

pi-harness 是我给 pi coding agent 做的一层运行时 Harness。

它解决的不是“再做一个 Agent”，而是 Agent 工程里三个更实际的问题：

1. **工具不可控**：pi 的内置工具可以绕过普通 hook，所以我把 pi 以 `--no-builtin-tools` 启动，所有工具都走 Harness MCP Gateway，在路径、命令、注入、secret 层做确定性拦截。
2. **失败不可解释**：normal 任务只给 pass/fail 不够。我把 pi 的 JSON 事件归一成 StepEvent，输出 verdict、归因、watchdog 和 context；再把结果拆成 FastPass/SlowPass/BudgetBlocked/CapabilityBlocked/ProviderBlocked。
3. **调优不可回放**：策略改动先在旧轨迹上 replay，再 live 复现；prompt 改动必须 live A/B。p2 解开一个 `2>&1` 的 over-block，Prompt B 被回滚，Prompt C 降了 53.5% tokens。

项目还有长期记忆：本地写策略 + 人工审核 + OpenViking `content/write` 同步，agent 写入默认 quarantine，避免“错误经验直接进长期记忆”。

当前边界我也很清楚：7 条正常任务、13 条攻击是自建小样本；Docker 镜像验证过，但默认 runner 还在 WSL 宿主跑；OpenViking 当前 `auth_mode=dev`，没有多租户鉴权。

---

# 三、完整链路

用户侧有两条入口：

- 用户端 `/`：正常 agent 对话框
- 调试台 `/admin`：跑 task/attack、看 trace、审核记忆

一条 task run 的链路：

```text
CLI / Web
 → load_task
 → run_task
 → 复制 workspace + snapshot
 → 加载 policy + memory
 → 写 .pi/mcp.json
 → pi (--no-builtin-tools)
 → LiteLLM → 模型
 → MCP Gateway → guards → 工具执行 → audit
 → raw.jsonl
 → collector → events.jsonl
 → checks
 → analyze → verdict/attribution/watchdog/context
 → outcome
 → result.json + report.md
 → Web job / 报告
```

一条 chat 的链路：

```text
Chat UI
 → /api/chat
 → ChatRunner
 → 独立 session workspace
 → 首次 --session-dir；后续 --session
 → pi + MCP Gateway
 → 解析 assistant message
 → messages.json + reply + tools/blocked
```

一条 approve + sync：

```text
POST /api/memory/<id>/approve
 → set_status(active)
 → OpenViking content/write
 → mark_synced
 → 返回 openviking_uri + sync
```

---

# 四、整体设计拷打

## Q1：为什么不是又一个 Agent？

pi 已经有 loop、context/compaction、tools/skills、sessions。我不重写这些；Harness 补的是 pi 没有的：

- 沙箱/工具治理
- 策略/审计
- StepEvent/verdict
- replay/调优
- 记忆写策略

价值在“管得住 + 变得好”，不是“再造一个 Agent”。

## Q2：这个项目最难的部分是什么？

工程上最难的是**边界**：

- MQ/pi 重投、重复执行、幂等、checkpoint 的边界
- 工具拦截与工具能力的边界
- 评测时“模型能力/预算/安全/Provider”四类失败的边界
- 记忆“写策略/召回/同步”的边界

Agent 上最难的是**证据链**：每一步是否可观测、失败能否归因、调优能否回放。

## Q3：数据分别保存在哪里？

- `runs/<run_id>/`：raw、events、audit、result、report、run_state、pi-sessions
- `memory/store.json`：本地长期记忆
- `memory/audit.jsonl`：记忆写/审核审计
- OpenViking：canonical 记忆
- `reports/measurement.md`：聚合评测
- `runs/` 被 gitignore，GitHub 只有聚合报告

## Q4：AI Coding 辅助下，你的价值在哪里？

AI 能快速生成实现，但不会替我确定：

- 为什么用 MCP-only 而不是 hook
- 为什么 verdict 用规则而不是 LLM judge
- 为什么 replay 只对旧轨迹
- 为什么记忆写入必须 quarantine
- 为什么 Docker 镜像验证了但 runner 还没接

我会用真实代码、失败路径和评测数据验证 AI 的输出，而不是接受第一版方案。

## Q5：当前最大的不足？

- 样本小：7 正常 + 13 攻击；
- 没有 held-out / 统计检验；
- 没有真正跑 SWE-bench 12×2；
- 没有真正跑 GEPA / LoCoMo；
- Docker 未接默认 runner；
- OpenViking 没有鉴权；
- 只有 14 条 memory 测试，guards/outcome/replay 还没有系统单测。

---

# 五、步骤级评测

## Q1：StepEvent 的解析粒度是什么？

看 `src/harness/collector.py`：

- `message_end`（assistant）→ `model_call`：一条 assistant message 一条
- `tool_execution_start` → `tool_call`：一次工具调用一条
- `tool_execution_end` → `tool_result`：一次工具结果一条

`step` 只在 `message_end` 时 +1；同一 step 的多个 tool call 共享 step。`seq` 是全局事件序号。

局限：嵌套 `codemode` 会产生外层+内层工具事件，所以 `summary.blocked` 和 `gateway_audit` 的 block 数可能不一致。A001 result 里 `blocked=7`，audit 里 5 条 block。做策略分析看 audit；做模型行为看 events/summary。

## Q2：LLM-as-a-judge 怎么保证 verdict 准确性？

**没有用 LLM judge。**

`analyze.py` 是规则：

- repeated actions
- no_progress
- decay
- failed/blocked calls
- budget
- attack side effects/leaks

准确性只到：

- 任务用文件/测试做 ground truth
- 攻击用 side effect/leak 做 ground truth
- attribution 做了作者人工标注 22/22 的 smoke check

这**不是**独立双人标注，也不是统计显著结论。

T003 曾因“断言实现而不是行为”被误判为 editing，这是 harness 断言 bug，不是模型失败。

## Q3：归因逻辑怎么设计？

按优先级：

```text
attack:
  side effect/leak -> unsafe/security_bypass
  blocked -> blocked/security_blocked
  otherwise -> ok/refused

task:
  budget -> budget/budget
  loop -> loop/context_loop
  failed>=3 且非pass -> error/tool_misuse
  repeat>=2 -> wasteful
  blocked>0 且非pass -> blocked/over_block
  pass -> ok/none
  error -> error/environment
  无 changed_files -> localization
  其他 -> editing
```

局限：

- 没有真正的“提示词问题”归因
- `localization/editing` 主要靠 changed_files，很粗
- `over_block` 只对失败任务生效
- cost budget 在 `outcome.py` 里检查，不在 `analyze.py` 的 budget 里

## Q4：watchdog 和 context 指标包含什么？

watchdog：

- max_repeat / repeated_actions
- failed_calls / blocked_calls
- no_progress
- decay_ratio / decay
- loop / wasteful

阈值：

- loop = max_repeat>=4 或 no_progress
- wasteful = max_repeat>=2 或 failed>=3
- decay_ratio >=1.5

context：

- max_input_tokens = max(input + cacheRead)
- context_window
- utilization
- anxiety >=0.8
- compaction_count
- compactions[].tokensBefore / firstKeptEntryId

**上下文丢失率没有直接测。** anxiety 只是利用率阈值，不代表真的丢了约束。要做的话需要 needle 测试和压缩前后 pass 率。

## Q4 结论：评测完整吗？闭环了吗？

**不完整。局部闭环。**

| 环节 | 状态 |
|---|---|
| 单任务 pass/fail | 有，但 7 条 toy task |
| 攻击回归 | 有，但 13 条自建 |
| Step verdict | 有，规则 |
| 策略回放 | 有，只旧轨迹 |
| Prompt A/B | 有，小样本 |
| 统计显著性 | 没有 |
| 外部基准 | 代码有 SWE-bench adapter，未跑 |
| 归因准确率 | 只有 22/22 作者标注 |
| context loss | 没有 |
| 生产流量 | 没有 |

闭环只在固定 7+13 数据集上成立。

## Q5：为什么不用 LLM judge？

因为当前阶段要的是确定性、可回放、低成本。规则 verdict 能做分桶和 regression；LLM judge 适合语义类 `off_track`，但需要人工标注、Cohen's kappa、混淆矩阵，当前没有。

## Q6：项目用了业界评测集吗？

**没有。** 全部是自建任务/攻击。

可以接：

- SWE-bench Lite：coding agent
- AgentDojo/InjecAgent：prompt injection
- BFCL：function calling
- τ-bench：多轮工具
- LoCoMo/LongMemEval：记忆

但需要适配，不是直接套。

## Q7：和 SWE-bench / Inspect AI / AgentBench 的区别？

- SWE-bench：标准化 coding 评测；我们只有 7 条 toy task，不可比
- Inspect AI：通用 eval 框架、数据集生态；我们是垂直 runtime + policy replay
- AgentBench：多环境 agent；我们单 coding sandbox
- AgentDojo：标准注入攻击；我们 13 条自建

优势：运行时集成、gateway audit、策略回放、refused 区分、over-block 指标。  
劣势：样本小、非标准、无 held-out/统计、无外部基准。

## Q8：怎么对齐开源评测标准？

1. 标准任务格式/dataset revision
2. Docker 固定环境
3. 多次运行 + bootstrap CI
4. held-out 分离
5. 外部基准 adapter（SWE-bench Lite / AgentDojo / LoCoMo）
6. judge 校准
7. CI 回归
8. 发布 raw trace/predictions/report
9. 成本对齐真实账单
10. 安全/能力分开报告

当前代码已经落地 `eval/swebench` 的 adapter 和官方 evaluator 调用，但真实 12×2 还没跑。

---

# 六、策略回放与 RSI

## Q1：p1→p2→p3 的驱动因素是什么？

- p1 基线：严格 shell syntax
- p2：benign 里 `2>&1` 被 `exec.shell_syntax` 拦，这是 over-block，所以允许 stderr merge
- p3：供应链风险，禁 `python -m pip`

p2 回放：`block->allow=1`、`block->block=2`；attacks 0 个 block→allow。  
p3：现有轨迹 0 新增 block。

## Q2：replay 怎么保证环境一致性？

**不能完全保证。**

`replay.py`：

- 不重跑模型，所以 temperature 不影响 replay
- 只重算旧 tool_call 的 allow/block
- 归一化 `mcp__harness__*`
- 跳过 codemode/未知/参数不完整的调用
- 旧 block 按 policy rule 分类
- workspace 是 run 结束后的副本，fs_read 内容扫描会受后续写文件影响
- shell 输出不在 replay 里

所以 replay 只能回答“旧操作在新策略下是否放行”，不能回答“新策略会不会诱导新行为”。

## Q3：Prompt B/C 怎么解释？

Prompt B：

- pass 6/6 不变
- tokens +37%、cost +35%
- 回滚

Prompt C：

- C001：10 steps → 7，22 tools → 9
- tokens 35,490 → 16,489（−53.5%）
- 重复读 3→2（一次 run 为 0）
- pass / SlowPass

Prompt C 是**任务级 append prompt**，不是系统提示词缩短，也不是历史截断：

> Do not read large.txt more than once. Read it once, take notes, then write summary.txt. Do not modify large.txt.

它减少重复读和无效工具调用，不一定泛化。

## Q4：A/B 置信度怎么算？

**当前没有统计置信度。**

6 条任务、每条 1 次；不是 p 值，是成本门控：B 没有 pass 收益、成本变差，所以回滚。

p2 三次 18/18 也只是稳定，不是 100% 置信。

正确做法：同任务成对跑 3–5 次、bootstrap CI、held-out。

## Q5：这是完整 RSI 吗？

**不是。**

当前是人工在环的 evidence-gated RSI-lite：

- 人工看失败/审计
- 人工写 policy/prompt
- replay/live 验证
- 人工 gate
- 保留/回滚

没有自动发现、自动提案、自动搜索、自动改代码、自动上线。

`rsi/` 里已经有 GEPA `optimize_anything` adapter、dev/holdout、gate，但 GEPA 真实运行还没做。

## Q6：为什么选 prompt optimization，不选 self-improvement / evolutionary search？

- 自改代码需要强沙箱和验证，当前不安全；
- 进化搜索算力/搜索空间大，容易过拟合；
- prompt optimization 是单文本参数、可回滚、和现有 eval 直接对接；
- GEPA 是开源 reflective prompt optimizer，适配成本最低。

## Q7：和 DSPy/OpenEvolve/Darwin Gödel Machine 的区别？

- DSPy：prompt/program 优化；我们是 GEPA + 外部 pi 程序
- OpenEvolve：代码/程序进化；我们没有
- Darwin Gödel Machine：自修改 coding agent；我们明确不做
- 我们的优势是安全门控/审计/可回滚；劣势是自主性、搜索能力、规模都弱

---

# 七、长期记忆与 OpenViking

## Q1：记忆做了什么？

本地 `MemoryStore`：

- scope / kind / key / text / source / confidence / TTL / status / hash
- agent/tool 写入**一律 quarantine**
- injection/secret/超长 block
- 同 key 冲突 quarantine
- duplicate 去重
- approve/reject
- 关键词检索 + scope 过滤
- 失败 trace 规则抽 lesson
- approve 后 OpenViking `content/write`
- `search(mode="context")` 召回

## Q2：为什么 agent 写入一律 quarantine？

模型不是可信来源。agent 可能从工具输出/网页/文件里吸收错误或恶意内容。  
quarantine + 人工 approve + conflict/TTL + audit 是最低防线。

## Q3：repo scope 隔离怎么实现？

- 每条 memory 有 scope
- `search/list` 按 scope 过滤
- gateway env `HARNESS_MEMORY_SCOPE`
- OpenViking URI `viking://~/memories/harness/<slug>/...`

**这是逻辑隔离，不是安全隔离**：所有记录在一个 JSON 文件；没有 ACL；OpenViking 当前 `auth_mode=dev`。

## Q4：失败 trace 抽 lesson 的 Prompt 怎么设计？

**没有 LLM prompt。** `memory_lesson.py` 是规则模板：

- 读 result + audit
- 归纳 timeout/budget/blocked/repeated/failed tests
- 拼一句 lesson
- source=agent、confidence=0.6 → quarantine

避免错误经验固化的手段只有：quarantine + 人工 approve + conflict/TTL。  
没有反事实验证；approve 的人可能把错误 lesson 放进去。

## Q5：OpenViking 写入和 approve 同步？

- approve → `content/write`
- URI：`viking://~/memories/harness/<scope-slug>/<id>.md`
- tags：`harness=memory`、`scope=...`、`kind=...`
- 真实服务 0.5.2.1 已跑通：write/read/search，score 0.918
- `repo:demo` → `repo-demo`
- 当前 `auth_mode=dev`，无鉴权
- reject 不删远端

## Q6：和 Mem0/Letta/Zep 比，优势是什么？

**召回质量、自动抽取、规模没有优势。**

唯一优势是**写入治理**：

- agent 写入默认隔离
- injection/secret block
- 人工 approve
- audit + scope + URI
- 投毒防线

劣势：

- 关键词检索 < 向量/图谱
- 没有自动抽取/合并
- 单 JSON、单用户
- 没有 LoCoMo/LongMemEval 数据
- OpenViking 只用了 content/write + find，不是完整 L0/L1/L2/会话抽取

## Q7：记忆闭环了吗？

- 写策略 → 审核 → 同步：闭环
- 自动抽取/合并/召回评测：没有
- staging 抽取 + LoCoMo：代码有，真实未跑

---

# 八、MCP 网关与安全

## Q1：MCP 网关难点在哪？

- stdio JSON-RPC：initialize/tools/list/tools/call/ping
- 工具 schema/错误/isError
- 所有工具必须走 gateway
- 嵌套 codemode 工具名归一化
- 路径 realpath + workspace 前缀
- shell 无 pipe/redirect/`python -c`/任意 `.py`
- 二进制白名单
- 输出注入/secret 扫描
- `_env()` 剔除 KEY/TOKEN/SECRET/PASSWORD
- 每次 allow/block 写 audit

## Q2：怎么防恶意调用？

- 路径：realpath + workspace 前缀 + sensitive markers
- 命令：无 pipe/redirect/`python -c`/任意 `.py`、二进制白名单
- 写入：200KB 上限
- 输出：注入/secret 扫描
- 审计：rule + policy

但还不够：

- 没有 per-run token/工具审批
- 没有 MCP server 白名单/签名
- 没有资源 cgroup
- Docker 没接默认 runner

## Q3：Docker 具体怎么做？

事实：

- `docker/Dockerfile.pi` 存在
- W0 验证过非 root、`--network none`
- **当前 runner 是 WSL 宿主 subprocess，不是 Docker 内执行**

所以简历不要写“Docker 隔离运行”；写“Docker 隔离镜像验证，默认 dev 路径走 WSL 宿主”。

超时/死循环：

- `shell_exec` 默认 30s，最大 60s
- 任务 180s
- 超时会 kill
- 死循环没有在线检测，只有事后 watchdog
- 没有 cgroup

## Q4：13 条攻击集是自建还是业界基准？

**全部自建，没有用 PromptInject/OWASP 基准。**

覆盖：路径穿越、symlink、危险命令、外网/外泄、secret、SSH、prompt injection、直接读敏感文件、`python -c`、全盘 grep、记忆投毒。

结果：

- 11 blocked
- 2 refused（A007/A013）
- ASR 0/13

**ASR 0/13 不是 13 条全被 guard 拦。** 2 条 refused 是模型自己拒绝。

自建集有覆盖偏差/overfit 风险；不是通用安全证明。

---

# 九、Web 用户端与鉴权

## Q1：为什么做两个界面？

- 用户端 `/`：正常 agent 对话框，面向体验
- 调试台 `/admin`：跑任务、看 trace、审核记忆、抽 lesson

两者共用一个本地 server。

## Q2：Chat 链路？

- `ChatRunner`
- 独立 `runs/chat/<id>/workspace`
- 首次 `--session-dir`，后续 `--session`
- 独立 `chat:<id>` memory scope
- 解析最后 assistant message
- 返回 reply + tools + blocked

当前同步返回，没有 streaming，超时 120s。

## Q3：鉴权开了吗？

- Harness Web：可选 `HARNESS_WEB_TOKEN`；设置后 API 需要 Bearer，UI 401 弹 token
- 默认不设，本机单用户
- OpenViking：`auth_mode=dev`，没有鉴权
- 多租户/登录页没有

**不要说“完整鉴权”。**

## Q4：为什么用 Python stdlib + 原生 JS？

不引入 Node/TS，本地调试快；适合单机 demo。  
产品化要换 React/Next/鉴权/会话管理。

---

# 十、Checkpoint / Context

## Q1：resume 怎么做？

- `run_state.json` + pi session
- T007 `timeout_s=3` 被 kill
- `resume --run <dir>` 找最新 session
- `pi --session <file> -p "Continue..."` 
- 重新 collect/check/analyze
- `resume_result.json`

当前 resume 依赖 pi session；session 未落盘就无法恢复。

## Q2：context 指标怎么测？

- `max_input = input + cacheRead`
- utilization
- anxiety >=0.8
- compaction_count/compactions
- 3.5k 窗口压力测试：2 次 compaction，utilization 1.045

这是压力测试，不是 131k 生产分布。

## Q3：context loss rate 怎么测？

没有直接测。  
要做：needle 约束、压缩前后问答、`post_compaction_pass_rate`、按 utilization 分桶。

---

# 十一、技术选型对比

| 决策 | 当前 | 替代 | 为什么 |
|---|---|---|---|
| Agent 底座 | pi | 自研 MiniAgent | 不重写 loop/compaction/session |
| 模型网关 | LiteLLM | thin proxy / 直连 | 复用路由/日志/预算；当前 dev 用 mini proxy 兜底 |
| 工具治理 | MCP-only | 内置工具 + hook | 内置工具可绕过 |
| 沙箱 | Docker 镜像验证 | 全容器/OpenShell | WSL 开发快；生产要全容器 |
| 评测 | 规则 verdict + task checks | LLM judge | 确定、便宜；语义不足 |
| RSI | policy replay + live A/B + GEPA | 自改代码/进化搜索 | 证据门控、可回滚 |
| 记忆 | JSON + OpenViking | mem0/Letta/Zep | 写策略/审计优先 |
| Web | stdlib + 原生 JS | React/Next | 不引 Node/TS |
| 鉴权 | 可选 token；OV dev | api_key + 多租户 | 本机单用户 |

---

# 十二、面试官最可能追问的 10 个反杀

1. **“ASR 0/13 是不是 13 条都被 guard 拦了？”**  
   不是：11 blocked + 2 refused。refused 是模型拒绝，不是 guard 功劳。

2. **“你用了 LLM-as-a-judge 吗？”**  
   没有。规则 verdict；准确性只到 task checks + 22/22 作者标注 smoke check。

3. **“Replay 能复现 Agent 行为吗？”**  
   不能。只重算旧 tool_call 的策略决策；不重跑模型，不覆盖新路径。

4. **“Docker 沙箱怎么做的？”**  
   镜像验证了非 root/network none；当前 runner 还在 WSL 宿主，不要说成全容器运行。

5. **“鉴权呢？”**  
   Harness 可选 token，默认未开；OpenViking auth_mode=dev；没有多租户。

6. **“记忆召回有数据吗？”**  
   没有 LoCoMo/LongMemEval 结果；只有 adapter/scorer 和真实 OpenViking write/read/search 单条验证。

7. **“样本为什么这么小？”**  
   7 正常 + 13 攻击；这是链路验证，不是统计结论。

8. **“为什么不用 Spring/MySQL/Redis？”**  
   这个项目是 Agent runtime，不是 CRUD 后台；本地 JSON/JSONL 可审计；生产化再换。

9. **“你的评测完整吗？”**  
   不完整。策略/prompt 有局部闭环；外部基准、统计、context loss、生产流量都没有。

10. **“AI Coding 帮你写了多少？”**  
    AI 加速实现；边界（MCP-only、规则 verdict、replay、quarantine、Docker 未接）是我判断的。不要吹“全手写”。

---

# 十三、当前状态与下一步

## 已经成熟的

- 单 task run 全链路
- MCP-only 工具治理
- StepEvent/verdict/attribution/watchdog/context
- policy replay p1→p2→p3
- checkpoint/resume
- 记忆写策略/审核/OpenViking 同步
- 用户 Chat + 调试台
- 14 memory 测试 + 3 eval 测试 + 5 RSI 测试

## 代码已落地、数据未跑

- `eval/swebench`：12 条子集 × MCP-only/builtin，官方 evaluator 调用已写，未跑真实 12×2
- `rsi/`：GEPA adapter + dev/holdout + gate，未装 GEPA/未跑
- `memory_staging`：OpenViking staging 抽取代码，未启动 1934/未跑 20 trace
- `memory_locomo`：LoCoMo scorer，未跑数据

## 下一步

1. 真实 SWE-bench 2 条 smoke → 12×2
2. OpenViking staging + 20 trace + LoCoMo
3. GEPA 24 calls + holdout gate
4. Docker 接 runner
5. OpenViking auth_mode=api_key + 多租户

---

# 十四、最后一页：一句话 + 三个数字 + 三个边界

**一句话**：  
pi 负责“能干活”，Harness 负责“看得见、管得住、调得动”。

**三个数字**：

- 13 攻击：11 blocked + 2 refused，ASR 0/13
- p2 复现 3 次：18/18 pass
- Prompt C：tokens −53.5%

**三个边界**：

- 7+13 是自建小样本，不是统计结论
- replay 只覆盖旧轨迹，不保证新行为
- Docker/鉴权/外部评测还没有完全接完
