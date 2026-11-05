# WSL Quickstart

## 1. Project location

The project is in WSL at:

```text
~/pi-harness
```

It was copied from `D:\dsh-pro-harness\harness` (including the local Git
commits). The Windows path is also visible from WSL as:

```text
/mnt/d/dsh-pro-harness/harness
```

If `~/pi-harness` is missing, recreate it:

```bash
rsync -a --delete \
  --exclude runs/ --exclude tmp/ --exclude __pycache__/ \
  /mnt/d/dsh-pro-harness/harness/ ~/pi-harness/
```

## 2. Services

| Service | Address | Start |
|---|---|---|
| pi | CLI, not daemon | `export PATH="$HOME/.pi/agent/bin:$PATH"` |
| LiteLLM | `127.0.0.1:4000` | `~/litellm-proxy` venv |
| OpenViking | `127.0.0.1:1933` | `~/.openviking/start.sh` |
| Harness Web | `127.0.0.1:8765` | `bash scripts/web.sh` |

### Current dev fallback: mini OpenAI proxy

On this WSL setup, LiteLLM 1.106.6 hangs while fetching the remote model cost
map. The project therefore includes a local development fallback:

```bash
cd ~/litellm-proxy
set -a; source .env; set +a

cd ~/pi-harness
nohup env DEEPSEEK_API_KEY="$DEEPSEEK_API_KEY" \
  python3 scripts/mini_openai_proxy.py > /tmp/mini-proxy.log 2>&1 &
```

It exposes `/v1/models` and `/v1/chat/completions` on port 4000 and maps
`deepseek-chat` to `deepseek-v4-pro`.

**This is a dev fallback, not a production replacement for LiteLLM.** If
LiteLLM starts, stop the fallback and use LiteLLM.

## 3. Smoke test

```bash
cd ~/pi-harness
export PATH="$HOME/.pi/agent/bin:$PATH"

PYTHONPATH=src python3 -m harness.cli run \
  --task tasks/T001.json --runs runs/smoke --mcp-only

python3 scripts/setup_attacks.py
PYTHONPATH=src python3 -m harness.cli run \
  --task attacks/A001.json --runs runs/smoke --mcp-only
```

Expected: T001 `pass`; A001 `blocked`.

## 4. OpenViking

```bash
nohup ~/.openviking/start.sh > ~/.openviking/server.log 2>&1 &
curl http://127.0.0.1:1933/health
```

Current: `auth_mode=dev`, local-only, no API key.

For staging extraction, use a second instance on 1934 with an independent
workspace; see `memory/README.md`.

## 5. Web Console

```bash
cd ~/pi-harness
OPENVIKING_URL=http://127.0.0.1:1933 bash scripts/web.sh
# http://127.0.0.1:8765/       user chat
# http://127.0.0.1:8765/admin  debug console
```

## 6. Evaluation / RSI dependencies

```bash
python3 -m venv .venv-eval
source .venv-eval/bin/activate
pip install -U datasets swebench

python3 -m venv .venv-rsi
source .venv-rsi/bin/activate
pip install -U gepa
```

## Notes

- The local `~/pi-harness` copy has commits that may not be on GitHub yet.
- Do not commit `provider.env`, `ov.conf`, `.env`, or `runs/`.
