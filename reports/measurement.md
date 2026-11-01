# Measurement v2

## Outcome 分布

| outcome | count |
|---|---|
| BudgetBlocked | 1 |
| FastPass | 5 |
| Refused | 2 |
| SecurityBlocked | 11 |
| SlowPass | 3 |

- valid runs: 22/22（ProviderBlocked 排除）
- benign pass: 8/8 = 1.00
- FastPass / SlowPass: 5 / 3
- attacks: SecurityBlocked 11, Refused 2, SecurityBypass 0
- ASR: 0/13 = 0.00

## Over-block（benign）

- blocked tool calls: 2/29 = 6.9%
- tasks with blocked calls: 2/7（均仍 pass）

## Attribution 一致性（人工标注，样本小）

- agreement: 22/22 = 1.00

> 标注为作者人工标注；样本小，仅作 smoke check，不是统计显著结论。
