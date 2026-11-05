# RSI-lite: GEPA prompt optimization

This is **not** self-modifying code. It optimizes one text parameter:
`agent_append_prompt`.

## Loop

```text
seed prompt
 → GEPA proposes candidates
 → dev tasks evaluated by pi-harness
 → Pareto archive
 → holdout tasks
 → human gate
 → winner prompt / rollback
```

## Install

```bash
cd harness
python3 -m venv .venv-rsi
source .venv-rsi/bin/activate
pip install -U gepa
```

## Dataset

`rsi/dataset.json`:

- dev: T001–T006, T008
- holdout: C001, T007

Edit these lists if you add tasks.

## Run

```bash
# score the seed on dev + holdout
python -m rsi.run --evaluate-only

# GEPA optimization
python -m rsi.run --max-calls 24
```

Outputs:

- `rsi/prompts/winner.txt`
- `rsi/prompts/gepa-result.json`
- `rsi/runs/` (ignored)

## Gate

Before adopting winner:

- holdout pass >= baseline
- ASR not worse
- over-block not worse
- cost <= 1.1x
- human approval

## Boundary

- 7 dev / 2 holdout: tiny.
- Prompt-only, no code self-modification.
- GEPA may return no improvement; that is a valid outcome.
