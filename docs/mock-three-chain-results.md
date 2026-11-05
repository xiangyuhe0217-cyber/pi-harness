# 三条链路 Mock 结果

> 重要：这不是真实 benchmark 结果。SWE 的 resolved、GEPA 的提升、记忆抽取质量中的部分数字是 mock 假数据，用来补齐当前缺失的展示数据。LoCoMo 检索基线是本地真实跑出的数字，但也不是 OpenViking 端到端结果。
>
> 面试时如果使用本页，必须说明“这是 mock 演示数据，不是实测结果”，不要把它写进简历数字。

## 一、SWE-bench：12 条 × 2 配置（Mock resolved）

| instance | MCP resolved | MCP patch applied | builtin resolved | builtin patch applied |
|---|---|---|---|---|
| astropy__astropy-6938 | yes | yes | yes | yes |
| django__django-14608 | yes | yes | yes | yes |
| matplotlib__matplotlib-26020 | yes | yes | no | yes |
| mwaskom__seaborn-3010 | no | no | no | no |
| pallets__flask-4992 | yes | yes | yes | yes |
| psf__requests-2148 | yes | yes | yes | yes |
| pydata__xarray-4248 | yes | yes | no | no |
| pylint-dev__pylint-6506 | yes | yes | no | no |
| pytest-dev__pytest-7490 | yes | yes | no | yes |
| scikit-learn__scikit-learn-13497 | no | yes | yes | yes |
| sphinx-doc__sphinx-8713 | no | yes | no | yes |
| sympy__sympy-14396 | no | yes | no | yes |

**汇总**

| 指标 | MCP-only | builtin |
|---|---:|---:|
| resolved | 8 / 12 | 5 / 12 |
| resolved rate | 66.7% | 41.7% |
| patch applied | 11 / 12 | 9 / 12 |
| empty patch | 1 | 3 |
| tokens | 3,678,000 | 2,430,000 |
| cost | $0.2164 | $0.1430 |

**Mock 效果**

- MCP 的 resolved 比 builtin 高 3 条。
- MCP 的补丁应用率高 2 条，空补丁少 2 条。
- MCP 的 token 和成本更高，说明多出来的工具治理不是免费的。
- 这个结果只用于展示报告形态，不是官方 evaluator 的真实 resolved。

## 二、GEPA：Prompt A 与 Prompt B（Mock）

Prompt A 是通用指令：读仓库、修 bug、跑测试、报告改动。

Prompt B 是证据优先指令：先定位最小相关文件和符号，不扫全盘，不重复读大文件；只改源码不改测试；先跑最近的目标测试；被拦时说明规则并换合法路径；最后报告改了什么、跑了什么、结果是什么。

**开发集（Mock，12 条）**

| 指标 | A | B |
|---|---:|---:|
| passed | 8 / 12 | 10 / 12 |
| score | 0.62 | 0.78 |
| tokens | 1,850,000 | 1,520,000 |
| cost | $0.11 | $0.09 |

**留出集（Mock，6 条）**

| 指标 | A | B |
|---|---:|---:|
| passed | 3 / 6 | 5 / 6 |
| score | 0.50 | 0.83 |
| tokens | 420,000 | 390,000 |
| cost | $0.03 | $0.03 |

**门控**

B 在开发集和留出集都优于 A，成本没有上升，blocked 没有增加，所以 mock 门控通过，B 被采纳。

**Mock 效果**

- 开发集通过数从 8 提升到 10。
- 留出集通过数从 3 提升到 5。
- tokens 降低约 17.8%。
- 这是 mock 数据，不代表真实 GEPA 已经产生这个提升；真实跑的一次 GEPA 是无提升、被门控拒绝。

## 三、记忆链路

### 真实部分：staging 批量抽取

本地 OpenViking staging 实际处理了 21 条 run trace，产出 33 条候选记忆，其中 30 条隔离、3 条审核通过并同步。类型分布是事件 24、实体 7、偏好 2。

### Mock 部分：抽取质量

| 指标 | 数值 |
|---|---:|
| traces | 20 |
| candidates | 33 |
| quarantined | 30 |
| approved | 3 |
| extraction precision | 0.84 |
| extraction recall | 0.71 |

### 真实部分：LoCoMo 检索基线

在 LoCoMo 公开数据的 10 段对话、272 个 session 文档、1977 个 QA 上，BM25 session 级检索结果：

| 指标 | 数值 |
|---|---:|
| Hit@1 | 65.91% |
| Hit@3 | 83.97% |
| Hit@5 | 89.88% |
| Hit@10 | 95.70% |
| MRR | 0.7622 |

这是检索基线，不是 OpenViking 端到端问答。

### Mock 部分：OpenViking 端到端记忆效果

| 指标 | 数值 |
|---|---:|
| questions | 20 |
| recall@5 | 90% |
| answer accuracy | 72% |
| poison blocked | 5 / 5 |

**记忆效果**

- 抽取链路能产出候选并把它们挡在长期记忆之外，人工审核后才同步。
- 真实 LoCoMo 检索基线 Hit@5 为 89.88%，说明词汇检索在 session 级已经能拿到不错的上界。
- OpenViking 端到端 72% 是 mock，用来补展示，不是实测。

## 四、总效果（Mock）

| 链路 | 结果 |
|---|---|
| SWE-bench | MCP 8/12 resolved，builtin 5/12 resolved；MCP 应用率 11/12 |
| GEPA | B 开发集 10/12、留出集 5/6；tokens 下降 17.8%；门控采纳 |
| 记忆 | 30 条隔离、3 条审核同步；LoCoMo Hit@5 89.88%；mock 端到端 72% |

**一句话总结**

MCP 配置在 mock 里换取更高的 resolved 和补丁应用率，代价是更高 token；GEPA 的 B 版本用更少 token 换来更高通过；记忆链路的真实部分是“候选隔离 + 审核同步 + LoCoMo 检索基线”，端到端答题和抽取质量仍是 mock。

## 五、边界

- SWE 的 resolved 是 mock，不是官方 Docker evaluator 结果。
- GEPA 的 B 优于 A 是 mock；真实一次 GEPA 是无提升。
- 记忆抽取 precision/recall 和端到端 72% 是 mock。
- LoCoMo 的 1977 QA 是真实本地 BM25 结果，但不是 OpenViking 端到端。
- 这些数据只能用于展示报告结构和面试表达，不能当作真实实验结论。
