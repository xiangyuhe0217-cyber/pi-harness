# 博客大纲：《给 pi 套一层 Harness：从“只有 pass/fail”到 ASR 0/12》

## 开头钩子

> Agent 的问题不是不聪明，是不可验证。
> 你让它修一个 bug，它可能改了三个文件、跑了五次测试、烧了 3 万 token，最后告诉你“完成了”。
> 你只能信，或者不信。

## 1. 为什么不是又一个 Agent

- pi 已经有 loop、context/compaction、tools/skills、sessions。
- 缺的是：沙箱、策略、逐 step 判断、可回放的调优。
- 结论：做 Harness，不做 Agent。

## 2. 架构：三层

- LLM 层：pi custom provider → LiteLLM。
- 工具层：`--no-builtin-tools` → Harness MCP Gateway。
- 观测层：JSON events → StepEvent → verdict/归因/watchdog/context。

配图：架构 ASCII / 手绘图。

## 3. 第一步：把工具关进网关

- `--no-builtin-tools` 是关键发现。
- 12 条攻击：symlink、`../../etc/passwd`、`rm -rf`、`python -c`、prompt injection、大写入。
- 结果：ASR 0/12，blocked 12/12。
- 两个真实 bug：
  1. 相对路径把 workspace 拼成双层 → benign 0/6；
  2. `python3 script.py` 绕过写入大小限制 → 补 `exec.script_execution`。

## 4. 第二步：让失败可解释

- verdict 七类：ok / blocked / unsafe / wasteful / loop / error / budget。
- 归因：localization / editing / tool_misuse / over_block / security_*。
- T003 的假失败：断言实现而不是行为 → 误判 editing。
- 结论：断言行为，不要断言实现。

## 5. 第三步：策略回放

- p1 → p2 允许 `2>&1`：replay 上 block→allow=1，attacks 0 回退。
- p3 禁 `python -m pip`：0 新增 block。
- 教训：live 的 block 数有噪声，策略改动看 replay + 多次 live。

## 6. 第四步：Resume 与 Context

- `run_state.json` + pi session：T007 kill 后 resume pass。
- 3.5k 窗口：2 次 compaction，utilization 1.045、anxiety true。
- 长任务 C001：Prompt C tokens −49%、重复读 3→0。

## 7. 负结果也要写

- Prompt B：tokens +37%、pass 不变 → 回滚。
- 结论：prompt 改动必须 live A/B，不能靠“感觉”。

## 8. 局限与下一步

- 6/6 是链路验证，不是模型能力。
- replay 只覆盖策略层。
- compaction 是小窗口模拟。
- 长期记忆未做；下一步 mem0/OpenViking + 写策略/投毒检测。

## 结尾

> 我没有让 Agent 更聪明；
> 我让它每一步都能被看见、被管住、被调好。
