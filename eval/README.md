# SWE-bench Lite subset

This is the external evaluation chain for pi-harness.

It is intentionally a **12-instance subset**, not full SWE-bench. The goal is a
complete, reproducible pipeline with the official evaluator, not a leaderboard
claim.

## 1. Install

```bash
cd harness
python3 -m venv .venv-eval
source .venv-eval/bin/activate
pip install -U datasets swebench
```

`datasets` is only needed to download the manifest. `swebench` and Docker are
needed for the official evaluator.

## 2. Build manifest

```bash
python -m eval.swebench.run manifest --count 12 --out eval/swebench/manifest.json
```

This selects 12 instances round-robin across repos and records dataset/revision.

## 3. Prepare repos

```bash
python -m eval.swebench.run prepare --limit 2   # smoke first
python -m eval.swebench.run prepare            # all 12
```

Each instance gets a clean repo at `base_commit` under `eval/work/instances/`.

## 4. Run agent

```bash
# smoke: two instances, both configs
python -m eval.swebench.run agent --limit 2 --configs mcp,builtin

# full 12 x 2
python -m eval.swebench.run agent --configs mcp,builtin
```

Outputs:

- `eval/work/predictions/mcp.jsonl`
- `eval/work/predictions/builtin.jsonl`
- `eval/work/meta/{mcp,builtin}.jsonl`

The patch is extracted from the run workspace after pi finishes. `.pi/` and
Python caches are excluded; new files are included via `git add -N`.

## 5. Official evaluation

```bash
python -m eval.swebench.run evaluate --predictions eval/work/predictions/mcp.jsonl --run-id harness-mcp
python -m eval.swebench.run evaluate --predictions eval/work/predictions/builtin.jsonl --run-id harness-builtin
```

Requires Docker. The official evaluator writes `results.json` under
`logs/run_evaluation/...`; the report command searches for it.

## 6. Report

```bash
python -m eval.swebench.run report --results-dir eval/work
```

Output: `eval/swebench/report.md`.

## 7. What it measures

- resolved@1 (official)
- apply rate
- empty patch rate
- tokens/cost
- MCP-only vs builtin

## 8. Boundaries

- 12/300 Lite subset; no generalization claim.
- one model, one run, no full CI.
- agent runs on host; evaluator runs in Docker.
- `builtin` is the control, not a production path.
