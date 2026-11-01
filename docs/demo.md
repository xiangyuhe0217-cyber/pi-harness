# 3 分钟 Demo 脚本

## 0. 一句话

给 pi 套一层运行时 Harness：可观测、可管控、可调优。

## 1. 正常任务（30s）

```bash
cd harness
PYTHONPATH=src python3 -m harness.cli run --task tasks/T001.json --mcp-only
```

看点：

- `runs/<id>/events.jsonl`：StepEvent
- `result.json`：verdict / attribution / watchdog / context
- `report.md`：checks + 学习与面试

## 2. 攻击（30s）

```bash
PYTHONPATH=src python3 -m harness.cli run --task attacks/A001.json --mcp-only
```

A001 是 symlink 逃逸：`config_host -> /etc/passwd`。

看点：

- `gateway_audit.jsonl`：`block` + `rule=path.outside_workspace`
- `events.jsonl`：`verdict=blocked`
- result：`blocked` + `security_blocked`

## 3. 策略回放（30s）

```bash
PYTHONPATH=src python3 -m harness.cli replay \
  --run runs/baseline-w3b/T002-... \
  --policy policies/p2.json
```

看点：

- `block->allow=1`（`2>&1` over-block 被解开）
- attacks 上 0 个 `block->allow`

## 4. Resume（30s）

```bash
PYTHONPATH=src python3 -m harness.cli resume \
  --run runs/resume-demo2/T007-... \
  --timeout 180
```

看点：

- `run_state.json`：failed → resumed
- `resume_result.json`：pass
- `changed_files`：calc.py / test_calc.py

## 5. Context stress（30s）

```bash
HOME=/tmp/pi-home-w6 PI_OFFLINE=1 PI_BIN=~/.pi/agent/bin/pi \
PYTHONPATH=src python3 -m harness.cli run \
  --task demos/C001-small.json --mcp-only
```

看点：

- `context.utilization` > 1.0
- `context.anxiety = true`
- `compaction_count = 2`
- `compactions[].tokensBefore`

## 6. OTel（10s）

```bash
PYTHONPATH=src python3 -m harness.cli export --run runs/w6-compact5/C001-...
```

看点：`otel.json` 里的 31 个 span。

## 收尾一句

“我不是又做了一个 Agent；我做的是让 Agent 能被看见、被管住、被调好的那层。”
