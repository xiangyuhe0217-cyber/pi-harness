# Web Console

> 不想记 CLI 的话，用这个页面：跑任务、看 trace、审核记忆。

## 启动顺序

| 组件 | 是否常驻 | 说明 |
|---|---|---|
| **LiteLLM** | **是** | Harness 通过它调模型；`127.0.0.1:4000` |
| **pi** | 否 | 每次运行由 Harness 调起 CLI，不是 daemon |
| **Harness Console** | 是 | 本页面 |
| **OpenViking** | 可选（当前已启动） | 语义检索 + approve 同步写；不配也能用本地记忆 |

```bash
# 1. LiteLLM（已配置过的话，在它自己的 venv 里启动）
curl -f http://127.0.0.1:4000/v1/models

# 2. Web Console（连接已启动的 OpenViking）
cd harness
OPENVIKING_URL=http://127.0.0.1:1933 bash scripts/web.sh
# 可选鉴权：HARNESS_WEB_TOKEN=... OPENVIKING_URL=... bash scripts/web.sh
# 或：PYTHONPATH=src python3 web/server.py --port 8765
```

打开：

- **用户端**：**http://127.0.0.1:8765/**（正常 agent 对话框）
- **调试台**：**http://127.0.0.1:8765/admin**（run / trace / memory review）

页面右上角会显示 `ready / degraded`：

- `LiteLLM down`：模型代理没起；
- `pi missing`：`PI_BIN` 或 `~/.pi/agent/bin/pi` 不对；
- `OpenViking not configured`：没设 `OPENVIKING_URL`，不影响本地记忆。

## 功能

### 用户端 Chat（`/`）

- 正常 agent 对话框：发消息、看回复、继续追问；
- 每个会话独立 workspace + pi session + `chat:<id>` memory scope；
- 工具调用可见，被拦截的数量/工具名显示在回复下方；
- “新会话”会换一个独立 sandbox，不污染上一个。
- 对话里也能看到：评测开启、工具拦截开启、scope 隔离。

### 运行（`/admin`）

- 选 task / attack / demo；
- 选 policy `p1/p2/p3`；
- 选 MCP-only、记忆 scope、追加 prompt；
- 后台线程跑，页面轮询 job；
- 完成后可直接打开 trace。

### Run 记录

- result / report / gateway audit / StepEvent；
- 失败 run 可以点「从失败 trace 抽取 lesson」：
  - 规则抽取，不额外调模型；
  - 写入仍是 `source=agent` → **quarantined**；
  - 需要到「记忆审核」approve。

### 记忆审核

- quarantined 列表，approve → active，reject → rejected；
- **approve 时会同步写 OpenViking**（配置了 `OPENVIKING_URL`）；
- 用户来源新增记忆直接 active，并同步；agent 来源必须审核后才同步；
- 记录里显示 `openviking_uri` / `sync_status`；
- scope 过滤（repo 隔离）；
- OpenViking 语义检索 + 同步写（配置后可用）。

## API

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/api/health` | LiteLLM / pi / OpenViking / memory |
| GET | `/api/catalog` | tasks / attacks / demos / policies |
| GET | `/api/runs?limit=40` | 最近 run |
| GET | `/api/runs/<id>` | result / report / audit / events |
| POST | `/api/run` | 提交后台运行 |
| GET | `/api/jobs/<id>` | 轮询 job |
| GET | `/api/memory?scope=&status=` | 记忆列表 |
| POST | `/api/memory/add` | 用户写入（active） |
| POST | `/api/memory/<id>/approve` | 审核通过 |
| POST | `/api/memory/<id>/reject` | 审核拒绝 |
| POST | `/api/lessons/extract` | 失败 trace → lesson 候选 |
| GET | `/api/openviking/search?q=&scope=` | OpenViking 语义检索 |
| POST | `/api/chat/session` | 新建聊天会话 |
| GET | `/api/chat/<sid>` | 聊天历史 |
| POST | `/api/chat` | 发一条消息（同步返回） |
| POST | `/api/memory/<id>/sync` | 手动重试 OpenViking 同步 |

## 鉴权

- **Harness Web**：可选 `HARNESS_WEB_TOKEN`。
  - 设置后，`/api/*`（除 `/api/health`）需要 `Authorization: Bearer <token>`；
  - 页面首次 401 会弹 token 输入框，存在 localStorage；
  - 默认不设，本机单用户。
- **OpenViking**：当前 `server.auth_mode = "dev"`，**没有开鉴权**，只监听 `127.0.0.1:1933`。
- 多租户/登录页还没做；`HARNESS_WEB_TOKEN` 是单 token。

## 注意

- 默认 bind `0.0.0.0`，方便 WSL/Windows 访问；**默认没有登录**，只在本机用。
- 用户端 Chat 和调试台共用同一个本地 server；`/admin` 不隐藏。
- 如果 Windows 访问不到 WSL 端口，用 WSL 的 IP，或把 `--host` 改成 `127.0.0.1` 后用端口转发。
- 首次 `/api/runs` 会扫描 `runs/`，有 4 秒缓存；run 结束后自动失效。
- 页面只依赖 Python 标准库，不需要 Node/TS。

## 每次都要启动 LiteLLM 和 pi 吗？

- **LiteLLM：要。** 它是模型代理，Harness 不直接连模型。
- **pi：不要单独启动。** 它是 CLI，每次 run 由 `runner.py` 调起；只要二进制和配置在。
- **OpenViking：当前已在本机启动（127.0.0.1:1933，dev 无鉴权）。** 不启动也能用本地 `memory/store.json`。
