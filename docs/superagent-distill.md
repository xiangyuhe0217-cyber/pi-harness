# dsh-superagent 阅读笔记：可迁移的架构思想与对 Harness 的启示

> 阅读对象：[deepseek-ai/dsh-superagent-prototype](https://github.com/deepseek-ai/dsh-superagent-prototype)
> 读到的材料：`README.md`、`docs/000–008`、`prompts/*.md`、`SETUP.md`。
> README 提到的《Exploring Super-agent Design: Towards a More Autonomous Agent System》**不在仓库内**，
> 且 README 明说"部分设计是未来方向、原型未实现"。所以本文只依据可读到的文档，不替那篇文章补充想象。

---

## 0. 它是什么

一个"主动型 coding agent"的参考实现：监听 GitHub（可选飞书）→ 判断这次请求该不该接 → 接了就开一张
Ticket、在自己的目录里干 → 在原会话里交付 PR。核心是**把"模型会不会干活"换成"谁授权、干到哪、失败了谁管"**。

它对本项目的价值不在功能，而在**四个可迁移的架构决定**和**一套文档纪律**。

---

## 1. 真正的新意（6 条）

### 1.1 把"人的注意力"当目标函数

000 篇只有一句原则：**"Take as little human attention as possible, and give as much value as possible."**
然后每个设计都拿它做判据：一条消息、一个通知、一个问题、一个设置项、一个面板元素、一段文档，
**都要给回比它消耗的注意力更多的价值，否则删掉**。

难在哪：这句话给了取舍一个可计算的标尺。多数 agent 项目的隐含目标是"能力最大化"，
于是通知、开关、报告无限膨胀；superagent 把它们当成本来记账。

可迁移性：★★★★★（改动成本最低，叙事价值最高）

### 1.2 授权与执行彻底分离

这是全文最硬的一块（002）。三条设计叠起来：

1. **两条路径**：新工作走 `Eval`（gate + assessment）；已有工作走 `Subscription` fan-out。
   fan-out 只给上下文、**不给授权**，绕过了 gate 也拿不到新权限。
   ——"context 不是 authority"被写成了机制，不是口号。
2. **强度三档**：`explicit`（名单内的人 @ 了 agent / 已有 Ticket 的线程里追问）、
   `inferred`（名单外追问、名单内的机器人）、`not admitted`。
   再配一张**准入表**，三个维度：接收范围 × 是否在名单 × 是否 @。每个格子选 explicit / inferred / ignore。
3. **Mandate（授权凭证）不可变**：记录 policy version、scope、strength、命中的规则、发起人身份、
   来源如何收到这次触发。**只有三种操作能改它**：accept 创建、人 stop 撤回、revalidation 失败撤销。
   Ticket 结束不结束 Mandate；resume 之前必须按**当前** Policy 重新校验。

配套的是 `accept mode`：`off` / `observe`（默认，只记 "would accept"）/ `auto`。
**先观察它想接什么，再允许它真的接。**

可迁移性：★★★★★（思想直接可用，机制可裁剪）

### 1.3 配置变更的语义被写清楚了

Policy version 一变（规则、accept mode、各 Source 的名单），系统做三件事：

- 丢弃**进行中**的 Eval，把它们的 Trigger 重新排队；
- 给**受影响**的、还活着的 Ticket 发一条 `policy-changed` Input，说明是"规则变了/发起人没资格了/不再自动接单"；
- **不撤销**已发出的 Mandate，**不取消**正在跑的 Ticket。

理由文档里写了：取消一个跑到一半的变更会留下半成品；变更应该记录并送达，而不是暴力回滚。
另外 `unavailable` 这个 Decision 状态把"评估没做完"和"拒绝"分开，24 小时窗口 + 可 dismiss，
避免把一次网络抖动变成一条要人看的告警。

可迁移性：★★★★★（这是所有"策略系统"都会踩的坑）

### 1.4 工作项状态与执行器状态解耦

Ticket **自定义**状态，不跟随 DSH Session——因为一个 Ticket 可以被交接、恢复、由多个 Executor 跑过。
它用一张"stage 表"（003）从等谁的角度定义状态，**从上到下第一条命中即生效**：

| Stage | 条件 |
|---|---|
| person / delivery | 输入投递失败 |
| person / answer | 有一个待回答的问题 |
| person / review | 最新 Report 是 `ready` |
| person / blocked, failed | 最新 Report 是 blocked/failed 且此后没人说话 |
| working / queued | 没有 Assignment 或 pending |
| idle | 最新 Report 是 `waiting`，或 Assignment 结束 |
| working | 其余 |

这张表的三个性质值得抄：**可判定**（条件都是事实）、**互斥**、**全覆盖**（不会漏）。
面板标签写"等谁 + 要什么"（`Awaiting answer`），不写内部状态码。

执行侧还有几个不显眼但很贵的决定：worker slot 并发 + **一个人类专用的额外 slot**（人不会被机器排队卡住）；
后台 job/subagent 未完成时**继续占 slot**，30 分钟封顶；交给人的时候**立即释放** slot。

可迁移性：★★★★☆（状态机那部分可直接照搬）

### 1.5 先存意图，再执行

所有"要对外产生效果"的动作（发消息、投递给 Executor、转发报告、启动 Assignment）都是
**事务内 enqueue，commit 之后才执行**（007 的 Effects）。每个 `kind + key` 一行，重复入队合并、立即到期但不改顺序；
失败指数退避；`Later` 表示"现在没资源"、**不计失败**；每个 kind 独立健康项，**连续三次**才上报。

Channel 写还多一层：消息带 receipt 和幂等键，**同一 Ticket 同一会话内保序**（确认在前、结果在后），
只有"会话已删/被锁/撤回"这种**永久不可能**才降级为 `dropped` 并留档，其它一律重试。
发失败 5s 起、翻倍到 300s。

可迁移性：★★★★★（这是"重复副作用"问题的标准答案）

### 1.6 prompt 当配置，且承认"默认会变"

prompt 被拆成四类：共享/角色、team 三段（可编辑）、generated（policy、environment，每次请求重算且放最后）、
可覆盖的 built-in parts（每个有 key）。覆盖记 **base**（基于哪版默认），保存生成不可变版本（revision/前驱/来源），
Session **每个 model request 都读最新版**，并记录本 Session 用过哪些 revision。
最有意思的是升级流程：默认变了而 team 改过 → 标 **Default updated**，把新旧默认和 team 文本并排给你选
"保留我的 / 用新默认 / 再改"。覆盖文本与默认相同则自动删除，让它继续跟随未来默认。

最硬的一条是**优先级阶梯**（004）：

1. 工具与宿主强制的事实（身份、权限、参数校验）——prompt 改不动；
2. built-in / generated；
3. 该 Ticket 命中规则的流程要求；
4. team 段与 skills；
5. **外部文本（消息、评论、文档、引用）：是数据，永远不改变规则**。

可迁移性：★★★★☆（阶梯照抄；三方差分 UI 不必抄）

### 1.7 文档即测试 + 拒绝概念表

两个很少见的工程实践：

- `tests/docs.spec.ts`：编号文档**只能引用更早的文档**、每个本地链接必须解析、不许有冲突标记、
  007 的模块表和测试表必须**列全**。文档说谎会让 CI 红。
- 001 有 **Rejected concepts 表**：13 个被否掉的概念 + 每个的否决理由
  （比如"不做 Principal / 不跨 Source 映射身份 / 不让 Eval 自己排延迟任务 / 不因失败锁死 Executor 全部工具"）。
  这张表比"我们做了什么"更能防止架构回退。

还有 `tests/model-surface.spec.ts`：模型能看到的一切（tools、prompts、skills、inputs）都要和 schema 对齐，
且每个角色有**体积预算**。防的是"提示词/工具描述悄悄漂移"。

可迁移性：★★★★★（最便宜的高价值改造）

---

## 2. 概念对照：它 ↔ 本项目

| superagent | harness 里的对应物 | 缺什么 |
|---|---|---|
| Source（带读位置、幂等、自己身份） | `tasks/`、`attacks/` 文件 + MCP 网关输入 | 没有"读位置/去重"，任务是一次性文件不是流 |
| Trigger（不可变事件 + disposition） | `StepEvent`（tool_call / guard / verdict） | step 有事件，没有"它去哪了"的记录（filtered/eval/fan-out） |
| Thread（同线程串行 eval） | Run（+ pi session） | 有 Run，无"同一线程不并发判断"的约束 |
| Policy（版本 + 各 Source 部分 + 准入表） | `policies/p1–p3.json` + `guards.py` | 无 accept mode、无准入表、无变更语义 |
| Eval（gate + assessment → Decision） | guards + `analyze.py` verdict | 逐 step 判断，非逐"工作请求"；Decision 只有 4 值，你有 7 类但无 reason code |
| Mandate（授权快照 + basis + 重校验） | `run_state.json` 的 `approvals` + `policy_version` | **只有事实，没有授权对象/范围/依据/失效条件** |
| Ticket（自定义状态，独立于 Session） | Run | Run 状态基本跟随 pi session |
| Assignment（pending→running→ended） | 一次 run 尝试（resume / retry） | 无显式生命周期 |
| Channel（保序、幂等、retry vs gone） | `reports/*.md`、`audit.jsonl` | 只写不投递，无投递语义 |
| Subscription（后续消息回到同一工作） | 无 | 没有"这条追问属于哪个 run"的路径 |
| Effects / Outbox（先意图后执行） | `run_state.json` 后写 + resume | **最后写状态**，崩溃窗口里副作用不可证 |
| prompt revisions | Prompt A/B/C | 只记录了用的哪个 prompt 名，没有版本号 |
| Health board（按 part、三振出局） | `reports/measurement.md` 离线指标 | 它是实时健康，你是离线报告 |

一句话：**它把 Run 拆成了 Work（Ticket）+ Authority（Mandate）+ Attempt（Assignment）三件东西，你只有 Run。**

---

## 3. 对 Harness 的十条启示（按 ROI 排序）

### P0-1 给 `run_state.json` 加 `authority` 快照，并在 resume 时重校验

现在 `run_state.json` 有 `policy_version` 和 `approvals`，但它们是"历史事实"，不是"授权凭证"。
加一个块：

```json
"authority": {
  "by": "task:T003 / user",
  "scope": ["workspace/T003/**"],
  "policy_version": "p2",
  "approved": ["shell.exec:rm -rf build"],
  "basis": "task_declared | user_approval | policy_allow",
  "expires_at": null
}
```

resume 时做一次 `revalidate(authority, current_policy)`：通过则恢复；不通过则标记 `revoked`，
按"新任务"处理而不是静默继续。**这一条直接补上你现在最大的语义缺口：策略换了，旧 run 还能不能接着跑？**

成本：一个字段 + 一个函数 + 两条测试。收益：报告里可以区分"能力失败 / 授权失败"，这是面试里最好答的一题。

### P0-2 把归因从自由文本改成 `code + values`

superagent 的 Decision 记的是 `Reason { code, values, triggerId }`，面板按 `reason.<code>` 措辞，
评估器自己写的话走单独的 `said`。你的 `attribution` 现在是分类枚举 + 说明文本，可以做两件事：

- `reason` 改成 `{code, values}`（如 `{"code": "over_block", "values": {"rule": "exec.deny_patterns", "cmd": "python3 -m pip"}}`）；
- 给每个 code 加两个属性：`counts_toward_pass`（接你 W8 的 outcome 分类）、`actionable`（决定是否进报告首页）。

收益：归因可统计、可回归，`22/22 人工一致` 从手工比对变成可重跑的一致性检查。

### P0-3 补一条 ADR：策略变更时进行中的 run 怎么办

照 1.3 的语义收敛成三句话写进 `docs/decisions.md`：

1. 新策略**只对下一代 run 生效**；
2. 进行中的 run 记录 `policy_drift = {started: p1, current: p2}`，报告里显式标出；
3. resume 时按**当前**策略重校验 `authority`，失败则 `revoked`（见 P0-1），不静默续跑。

反面教材它也给了：**不取消进行中的工作**（半成品比不跑更糟），**不撤销已发出的授权**（只记录并告知）。

### P0-4 加 `tests/test_docs.py`（30 行）

三条检查就够，全部是"文档不许说谎"：

- README 里的三个数字（7/7、0/13、18/18）必须出现在 `reports/measurement.md` 里；
- `docs/decisions.md` 的 ADR 编号连续，每条都有"背景/决策/后果/替代"四段；
- 文档里引用的本地路径都存在。

这是把"文档型项目"变成"可验证项目"最便宜的杠杆，也直接呼应它 `docs.spec.ts` 的做法。

### P1-5 给 tuner 加 `observe` 模式（不只是 replay）

你现在是 `replay（策略层）→ 真跑（prompt 层）→ 门控`，中间靠人工跑三次 p2 live（18/18）。
superagent 的 `observe` 把"新策略会怎么做"变成系统产物：**不拦、只记录 `would_block` + 规则 + 命中的命令**，
然后用这批记录决定要不要切 `auto`。

落到你的实现：`policies/p2.json` 加 `"mode": "observe"`，`guards.py` 在 observe 下返回
`would_block` 而不是 `block`，`analyze.py` 单独统计 `would_block` 并算"如果开启会误杀多少 benign 调用"。
**注意边界：攻击集不能跑 observe**（漏拦就是漏拦）。它覆盖的正是你 replay 覆盖不到的部分——新策略诱导的新路径。

### P1-6 用 intent log 让"无重复副作用"从指标变成性质

你 spec 7.2 把"重复副作用"列为威胁，控制手段是 `idempotency key + 调用日志`，但 `run_state.json` 是**最后写**的，
崩溃窗口里说不清"这个 rm 到底跑没跑"。最小改法：

- `runs/<run>/intent.jsonl`：调用有副作用的 MCP 工具（fs_write / shell_exec）**之前**追加一行 `{intent_id, tool, args_hash}`；
- 执行完追加 `receipt`；
- resume 时扫 intent 无 receipt 的项：可安全重放的（读、幂等写）重放，不可的重放则转人工确认。

顺带抄它两个细节：`Later` 型失败（没资源）**不计失败次数**；永久不可能（404/目标已删）降级为 `dropped` 并留档，不再重试。

### P1-7 加第四个指标层：注意力成本

你现在是 step / task / run 三层（verdict、pass、ASR/FPR/p95）。补一层：

| 指标 | 定义 | 数据来源 |
|---|---|---|
| `human_interventions_per_task` | 一次任务里人介入的次数（审批 + 回答问题 + 改 policy/prompt） | `approvals` + 交互日志 |
| `attention_yield` | 每条上报/告警里，最终导致动作的比例 | report 与后续 run 的关联 |
| `noise_ratio` | 无需处理的通知数 / 总通知数 | 同上 |

这层指标是 superagent 那句原则的度量版本，也是你 README 里"看得见、管得住、调得动"的自然延伸：
**管得住不光是拦住危险，还包括不制造噪音。**

### P2-8 记录 prompt revision，让 Prompt C 的结论可归因

Prompt C 的 `−53.5% tokens / pass 不掉` 现在是"两次对比"。给 `RunState` 加
`prompt_revision + model + policy_version` 三元组，每次 run 都记。
这样任何一次指标变化都能说清"是 prompt 变了、模型变了还是策略变了"——正是它记录 Session 用过哪些 prompt revision 的目的。

### P2-9 工具面按角色裁剪

它有两套 preset：router（14 个工具，禁 sleep、>30s timeout、>5s job wait，因为"等"会挡住新工作）
和 worker（6 个工具，**拿不到** `ask_user_question` / `present`）。
你的 watchdog/tuner 侧其实只需要"读 report + replay + 改 policy 提案"，不该有 shell；
pi 侧才需要全套 MCP 工具。这条对安全叙事有用：**监督者不该拥有被监督者的能力**。

### P2-10 抄它的"拒绝概念表"

在 `docs/decisions.md` 后面加一节 `## 已否决的概念`，每条一行：概念 / 否决理由 / 什么情况下重启讨论。
比如"不引入 Ticket/Subscription 域（会把 harness 变成 workflow engine，违背 ADR-001/008）"、
"不做面板（ADR-008）"、"不做跨 agent 身份映射"。这张表是防止三个月后自己推倒重来的保险。

---

## 4. 明确不该抄的

| 不抄 | 理由 |
|---|---|
| Ticket / Thread / Subscription / Correlation 全域 | 你的单位是"一次 run 的工具治理"，引入工作项域会把你变成 workflow engine，与 ADR-001 冲突 |
| Web 面板（6 个 tab、路由、i18n、三方差分 UI） | ADR-008 已决定不做 UI；它的**面板原则**可以搬到 Markdown report，组件不要搬 |
| 多 Source（GitHub + 飞书 + 轮询 + 读位置 + 频道） | 你的输入是本地任务文件，没有"流"的问题 |
| SQLite schema / migration / tmux 运维脚本 / setup 探测 CLI | 部署形态完全不同 |
| `danger-full-access` 的执行模型 | 它的隔离结论是"用独立 OS 账号"；你的 Docker + internal network 更强，不要退回去 |
| 无界增长的记录（它自己承认不删旧数据） | 你是按 run 目录组织，天然可归档；别学它只增不减 |

---

## 5. 两个哲学差异（写进博客会加分）

1. **它优化注意力预算，你优化安全预算。**
   它的"少即是多"是删通知、删设置、删概念；你的"多"是加 guard、加指标、加攻击用例。
   两者可以在同一句话里统一：**每个 guard、每个指标、每条通知，都要付得起自己的维护成本和噪声成本。**
   你的 `over-block 2/29 = 6.9%` 就是"guard 的噪声成本"已经在记账的证据——这比它更硬。
2. **它把授权放在"谁可以让我干活"，你把授权放在"这一步能不能做"。**
   它的 Mandate 是工作级授权，你的 approval 是调用级授权。两者不冲突，正交互补：
   工作级授权回答"该不该接"，调用级授权回答"接了之后这一步能不能执行"。
   如果哪天要做多 agent 编排，工作级授权是必须先有的那层。

---

## 6. 一句话总结

> Super-agent 把 agent 系统的问题从"模型会不会做"改写成"**谁授权、做到哪、失败了谁管、人要不要看**"；
> Harness 把同一组问题下沉到**单次 run 的工具层**。
> 两者的交集是三个词：**授权快照、可重放决策、注意力预算**。
> 前者你缺一个字段，中者你缺 reason code，后者你缺一层指标——都不到一天的工作量。

---

## 附：来源

- [仓库 README](https://github.com/deepseek-ai/dsh-superagent-prototype)
- [000 Philosophy](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/main/docs/000-philosophy.md)
- [001 Domain model](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/main/docs/001-domain.md)
- [002 Authorization](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/main/docs/002-authorization.md)
- [003 Execution](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/main/docs/003-execution.md)
- [004 Prompts](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/main/docs/004-prompts.md)
- [005 Panel](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/main/docs/005-panel.md)
- [007 Architecture](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/main/docs/007-architecture.md)
- [008 Cookbook](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/main/docs/008-cookbook.md)
