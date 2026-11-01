# OpenViking 接入

## 状态：真实服务已跑通

本机（WSL Ubuntu）已安装并启动：

- `openviking-server 0.5.2.1`
- venv：`~/.openviking/venv`
- 配置：`~/.openviking/ov.conf`
- workspace：`~/.openviking/workspace`
- 地址：**http://127.0.0.1:1933**
- Studio：**http://127.0.0.1:1933/studio**
- 鉴权：**未开启**（`server.auth_mode = "dev"`，只监听 127.0.0.1）

`openviking-server doctor` 全部 PASS：

```text
Embedding: openai/text-embedding-v3  dimension=1024  probe ok
VLM:       openai/deepseek-flash
Authentication: dev
```

## 模型配置

- Embedding：阿里百炼 `text-embedding-v3`，OpenAI 兼容
  - `https://dashscope.aliyuncs.com/compatible-mode/v1`
  - key：`~/.openviking/provider.env` 的 `DASHSCOPE_API_KEY`
- VLM：DeepSeek `deepseek-flash`
  - `https://api.deepseek.com/v1`
  - key：WSL `~/.bashrc` 的 `DEEPSEEK_API_KEY`
- 没有配置视觉能力；`vlm` 只用于文本摘要/查询规划。

`ov.conf` 不存明文 key，使用环境变量引用：

```json
{
  "embedding": {
    "dense": {
      "provider": "openai",
      "model": "text-embedding-v3",
      "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
      "api_key": "${DASHSCOPE_API_KEY}",
      "dimension": 1024,
      "input": "text"
    }
  },
  "vlm": {
    "provider": "openai",
    "model": "deepseek-flash",
    "api_base": "https://api.deepseek.com/v1",
    "api_key": "${DEEPSEEK_API_KEY}",
    "temperature": 0,
    "max_retries": 2
  },
  "server": {"host": "127.0.0.1", "port": 1933, "auth_mode": "dev"}
}
```

## 启动

```bash
~/.openviking/start.sh
# 或后台：
nohup ~/.openviking/start.sh > ~/.openviking/server.log 2>&1 &
```

健康检查：

```bash
curl http://127.0.0.1:1933/health
curl http://127.0.0.1:1933/ready
```

## Harness 写入 / 同步

```bash
export OPENVIKING_URL=http://127.0.0.1:1933
# auth_mode=dev 不需要 OPENVIKING_API_KEY

cd harness
bash scripts/web.sh
```

已实现：

- `POST /api/v1/content/write`：审核后的记忆写成 Markdown；
- **approve 同步**：quarantined → active 时写 OpenViking；
- **repo URI 映射**：`scope` → `viking://~/memories/harness/<scope-slug>/<record-id>.md`；
- 同步失败记录 `sync_status=error`，可调 `/api/memory/<id>/sync` 重试；
- Web Console 显示 `openviking_uri` / sync 状态。

| Harness | OpenViking |
|---|---|
| `scope=default` | `viking://~/memories/harness/default/<id>.md` |
| `scope=repo:demo` | `viking://~/memories/harness/repo-demo/<id>.md` |
| `kind=lesson` | tag `kind=lesson` |
| `source=agent` | 先 quarantine，approve 后才写 |
| `source=user` | 直接 active，直接写 |

## 真实端到端结果

1. approve 一条 `review-demo` lesson；
2. Harness 写入 `viking://user/default/memories/harness/review-demo/mem_c85a....md`；
3. `GET /api/v1/content/read` 读回完整正文；
4. `POST /api/v1/search/find` 返回该记忆，`score=0.918`；
5. `repo:demo` 用户记忆写入 `viking://user/default/memories/harness/repo-demo/mem_3b51....md`。

写入响应里 `vector_status=complete`，`semantic_status=skipped`（没有多模态/摘要模型链）；向量检索已验证可用。

## 鉴权

- 当前 `auth_mode=dev`：**没有开鉴权**，只监听 `127.0.0.1`。
- 如果要对其他机器开放，必须先改：
  - `server.auth_mode = "api_key"`
  - 配置 `root_api_key`
  - 创建 account / admin / user key
  - Harness 用 user key 调 OpenViking。
- 这一步还没做。

## 边界

- 只在本机 WSL 跑，没有对外暴露。
- 没有启用 OpenViking 鉴权/多租户。
- `semantic_status=skipped`：文本摘要/语义增强未完整跑；向量检索正常。
- reject 不会删除远端（quarantined 从未写过；active 后再 reject 才会留下远端记录）。
- 没有 batch write、删除、冲突合并。
- 真实服务已跑通，但只用单条 lesson 和单条 repo 记忆验证，不是全量回归。

## 参考

- [OpenViking 内容 API（write/read）](https://docs.openviking.ai/zh/api/12-content)
- [OpenViking 检索 API](https://docs.openviking.ai/zh/api/06-retrieval)
- [OpenViking 记忆 API](https://docs.openviking.ai/zh/api/16-memory)
- [OpenViking 认证](https://docs.openviking.ai/zh/getting-started/17-authentication)
- [Agent 安装 SOP](https://docs.openviking.ai/zh/getting-started/04-setup-for-agent)
