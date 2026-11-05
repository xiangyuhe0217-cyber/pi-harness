# Memory chain

Code lives in `src/harness/memory*.py`; this directory holds the local store and
the OpenViking-facing chain.

## Components

| Component | File |
|---|---|
| local store / write policy | `src/harness/memory.py` |
| staging session extraction | `src/harness/memory_staging.py` |
| context recall | `src/harness/memory_recall.py` |
| LoCoMo-style retrieval scoring | `src/harness/memory_locomo.py` |
| canonical OpenViking write/sync | `src/harness/openviking.py` |

## Staging flow

```text
run/chat trace
  → OpenViking staging (1934): session → messages → commit
  → memory_diff.json
  → local MemoryStore.add(source=agent) = quarantined
  → approve
  → main OpenViking (1933) content/write
  → recall search(mode=context)
```

### Staging server

Use a second OpenViking instance, not the main one:

```bash
mkdir -p ~/.openviking-staging/workspace
# Copy the main ov.conf, then change server.port to 1934 and
# storage.workspace to ~/.openviking-staging/workspace.
# Start it with the same embedding/vlm env.
```

The staging instance is disposable; its memories are candidates, not truth.

## Commands

```bash
# Extract a run into quarantine (HTTP to staging)
python scripts/memory_extract.py \
  --run runs/... \
  --scope repo:demo \
  --staging-url http://127.0.0.1:1934

# Or convert a saved memory_diff without HTTP
python scripts/memory_extract.py \
  --run runs/... --scope repo:demo --diff /tmp/memory_diff.json

# Recall via main OpenViking
python scripts/memory_recall.py \
  --scope repo:demo --query "test command"

# Runner-side recall
HARNESS_MEMORY_RECALL=openviking \
PYTHONPATH=src python3 -m harness.cli run --task tasks/T008.json --mcp-only
```

## Boundary

- Agent-extracted candidates are always quarantined.
- OpenViking staging is `auth_mode=dev`, local only.
- Reject does not delete remote canonical memory.
- Recall quality is not yet benchmarked on full LoCoMo; only the adapter/scorer exists.
